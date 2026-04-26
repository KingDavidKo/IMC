from typing import Dict, List, Tuple

from datamodel import Order, Symbol, TradingState

from common.round3.air import HYDROGEL_MAX_POS
from common.round3.config import DEFAULT_IV, HYDROGEL_PACK, LinearConfig, MAX_IV, MIN_IV, VELVETFRUIT_EXTRACT
from common.round3.pricing import black_scholes_call, book_stats, collect_anchor_ivs, ema, option_tte_years_for_state, strike_from_symbol, voucher_symbols
from common.round3.quoting import compute_hydrogel_orders, quote_product
from common.round3.state import dump_state, load_state


ACTIVE_VOUCHERS = ("VEV_4000", "VEV_4500", "VEV_5100", "VEV_5200")
OPTION_LIMIT = 300
OPTION_SOFT_CAP = 200
OPTION_PASSIVE_SIZE = 20
OPTION_TAKER_CAP = 25
OPTION_TAKE_EDGE = 2.0
OPTION_MIN_HALF_WIDTH = 1
OPTION_INVENTORY_SKEW_TICKS = 2.0

LINEAR_CONFIGS: Dict[str, LinearConfig] = {
    HYDROGEL_PACK: LinearConfig(HYDROGEL_MAX_POS, 0.30, 4.0, HYDROGEL_MAX_POS, HYDROGEL_MAX_POS, 3.0, 3),
    VELVETFRUIT_EXTRACT: LinearConfig(200, 0.20, 3.0, 20, 40, 2.0, 2),
}


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        trader_state = load_state(state.traderData, DEFAULT_IV)
        result: Dict[Symbol, List[Order]] = {}
        option_tte_years = option_tte_years_for_state(state)

        fair_values: Dict[str, float] = {}
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
            fair_values[product] = fair_value

        underlying_stats = book_stats(state.order_depths.get(VELVETFRUIT_EXTRACT))
        underlying_mid = underlying_stats[2] if underlying_stats is not None else fair_values.get(VELVETFRUIT_EXTRACT)

        if underlying_mid is not None:
            iv_ema = trader_state["iv_ema"]
            anchor_ivs = collect_anchor_ivs(state.order_depths, underlying_mid, option_tte_years)
            if anchor_ivs:
                iv_ema = ema(iv_ema, sum(anchor_ivs) / len(anchor_ivs), 0.20)
            trader_state["iv_ema"] = min(MAX_IV, max(MIN_IV, iv_ema))

        hydrogel_depth = state.order_depths.get(HYDROGEL_PACK)
        hydrogel_fair = fair_values.get(HYDROGEL_PACK)
        hydrogel_spread = trader_state["spread_ema"].get(HYDROGEL_PACK)
        if hydrogel_depth is not None and hydrogel_fair is not None and hydrogel_spread is not None:
            hydrogel_orders = compute_hydrogel_orders(
                HYDROGEL_PACK,
                HYDROGEL_MAX_POS,
                hydrogel_depth,
                hydrogel_fair,
                hydrogel_spread,
                state.position.get(HYDROGEL_PACK, 0),
            )
            if hydrogel_orders:
                result[HYDROGEL_PACK] = hydrogel_orders

        ve_depth = state.order_depths.get(VELVETFRUIT_EXTRACT)
        ve_fair = fair_values.get(VELVETFRUIT_EXTRACT)
        if ve_depth is not None and ve_fair is not None:
            config = LINEAR_CONFIGS[VELVETFRUIT_EXTRACT]
            half_width = max(
                config.min_half_width,
                int(round(trader_state["spread_ema"].get(VELVETFRUIT_EXTRACT, float(config.min_half_width * 2)) / 2.0)),
            )
            ve_orders = quote_product(
                VELVETFRUIT_EXTRACT,
                ve_depth,
                ve_fair,
                config.limit,
                state.position.get(VELVETFRUIT_EXTRACT, 0),
                config.passive_size,
                config.taker_cap,
                config.take_edge,
                half_width,
            )
            if ve_orders:
                result[VELVETFRUIT_EXTRACT] = ve_orders

        if underlying_mid is not None:
            for symbol in voucher_symbols(state.order_depths, ACTIVE_VOUCHERS):
                order_depth = state.order_depths.get(symbol)
                if order_depth is None:
                    continue
                strike = strike_from_symbol(symbol)
                fair_value = black_scholes_call(underlying_mid, strike, option_tte_years, trader_state["iv_ema"])
                reservation_price = fair_value - (OPTION_INVENTORY_SKEW_TICKS * state.position.get(symbol, 0) / OPTION_LIMIT)
                stats = book_stats(order_depth)
                half_width = OPTION_MIN_HALF_WIDTH if stats is None else max(OPTION_MIN_HALF_WIDTH, int(round(stats[3] / 2.0)))
                orders = quote_product(
                    symbol,
                    order_depth,
                    reservation_price,
                    OPTION_LIMIT,
                    state.position.get(symbol, 0),
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
