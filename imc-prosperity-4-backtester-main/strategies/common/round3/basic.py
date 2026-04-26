from typing import Dict, List, Tuple

from datamodel import Order, Symbol, TradingState

from common.round3.config import DEFAULT_IV, HYDROGEL_PACK, LinearConfig, MAX_IV, MIN_IV, VELVETFRUIT_EXTRACT
from common.round3.pricing import (
    black_scholes_call,
    black_scholes_delta,
    book_stats,
    collect_anchor_ivs,
    ema,
    option_tte_years_for_state,
    strike_from_symbol,
    voucher_symbols,
)
from common.round3.quoting import quote_product
from common.round3.state import dump_state, load_state


LINEAR_CONFIGS: Dict[str, LinearConfig] = {
    HYDROGEL_PACK: LinearConfig(200, 0.15, 4.0, 20, 40, 3.0, 4),
    VELVETFRUIT_EXTRACT: LinearConfig(200, 0.20, 3.0, 20, 40, 2.0, 2),
}

OPTION_LIMIT = 300
OPTION_SOFT_CAP = 150
OPTION_PASSIVE_SIZE = 10
OPTION_TAKER_CAP = 15
OPTION_TAKE_EDGE = 2.0
OPTION_MIN_HALF_WIDTH = 1
OPTION_INVENTORY_SKEW_TICKS = 2.0
HEDGE_POSITION_LIMIT = 100


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        trader_state = load_state(state.traderData, DEFAULT_IV)
        result: Dict[Symbol, List[Order]] = {}
        option_tte_years = option_tte_years_for_state(state)

        linear_fair_values: Dict[str, float] = {}
        for product, config in LINEAR_CONFIGS.items():
            stats = book_stats(state.order_depths.get(product))
            prev_mid = trader_state["mid_ema"].get(product)
            prev_spread = trader_state["spread_ema"].get(product)
            if stats is None:
                if prev_mid is None:
                    continue
                fair_value = prev_mid
                spread_ema = prev_spread if prev_spread is not None else float(config.min_half_width * 2)
            else:
                fair_value = ema(prev_mid, stats[2], config.ema_alpha)
                spread_ema = ema(prev_spread, stats[3], config.ema_alpha)
            trader_state["mid_ema"][product] = fair_value
            trader_state["spread_ema"][product] = spread_ema
            linear_fair_values[product] = fair_value

        underlying_stats = book_stats(state.order_depths.get(VELVETFRUIT_EXTRACT))
        underlying_mid = underlying_stats[2] if underlying_stats is not None else linear_fair_values.get(VELVETFRUIT_EXTRACT)

        iv_ema = trader_state["iv_ema"]
        if underlying_mid is not None:
            anchor_ivs = collect_anchor_ivs(state.order_depths, underlying_mid, option_tte_years)
            if anchor_ivs:
                iv_ema = ema(iv_ema, sum(anchor_ivs) / len(anchor_ivs), 0.20)
            trader_state["iv_ema"] = min(MAX_IV, max(MIN_IV, iv_ema))

        option_metrics: Dict[str, Tuple[float, float]] = {}
        if underlying_mid is not None:
            for symbol in voucher_symbols(state.order_depths):
                strike = strike_from_symbol(symbol)
                fair_value = black_scholes_call(underlying_mid, strike, option_tte_years, trader_state["iv_ema"])
                delta = black_scholes_delta(underlying_mid, strike, option_tte_years, trader_state["iv_ema"])
                option_metrics[symbol] = (fair_value, delta)

        net_voucher_delta = 0.0
        for symbol, (_, delta) in option_metrics.items():
            net_voucher_delta += state.position.get(symbol, 0) * delta

        hedge_target = int(round(-net_voucher_delta))
        hedge_target = max(-HEDGE_POSITION_LIMIT, min(HEDGE_POSITION_LIMIT, hedge_target))

        for product, config in LINEAR_CONFIGS.items():
            order_depth = state.order_depths.get(product)
            if order_depth is None:
                continue

            fair_value = linear_fair_values.get(product)
            if fair_value is None:
                continue

            current_position = state.position.get(product, 0)
            target_position = hedge_target if product == VELVETFRUIT_EXTRACT else 0
            inventory_error = current_position - target_position
            reservation_price = fair_value - (config.inventory_skew_ticks * inventory_error / config.limit)
            spread_ema = trader_state["spread_ema"].get(product, float(config.min_half_width * 2))
            orders = quote_product(
                product,
                order_depth,
                reservation_price,
                config.limit,
                current_position,
                config.passive_size,
                config.taker_cap,
                config.take_edge,
                max(config.min_half_width, int(round(spread_ema / 2.0))),
            )
            if orders:
                result[product] = orders

        for symbol, (fair_value, _) in option_metrics.items():
            order_depth = state.order_depths.get(symbol)
            if order_depth is None:
                continue

            current_position = state.position.get(symbol, 0)
            reservation_price = fair_value - (OPTION_INVENTORY_SKEW_TICKS * current_position / OPTION_LIMIT)
            half_width = OPTION_MIN_HALF_WIDTH
            stats = book_stats(order_depth)
            if stats is not None:
                half_width = max(OPTION_MIN_HALF_WIDTH, int(round(stats[3] / 2.0)))

            orders = quote_product(
                symbol,
                order_depth,
                reservation_price,
                OPTION_LIMIT,
                current_position,
                OPTION_PASSIVE_SIZE,
                OPTION_TAKER_CAP,
                OPTION_TAKE_EDGE,
                half_width,
                OPTION_SOFT_CAP,
                OPTION_SOFT_CAP,
            )
            if orders:
                result[symbol] = orders

        return result, 0, dump_state(trader_state)
