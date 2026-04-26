import math
from typing import Dict, List, Tuple

from datamodel import Order, OrderDepth, Symbol, TradingState

from common.round3.config import DEFAULT_IV, HYDROGEL_PACK, LinearConfig, MAX_IV, MIN_IV, VELVETFRUIT_EXTRACT
from common.round3.pricing import (
    black_scholes_call,
    black_scholes_delta,
    book_stats,
    collect_anchor_ivs,
    ema,
    implied_volatility,
    option_tte_years_for_state,
    strike_from_symbol,
)
from common.round3.quoting import compute_hydrogel_orders, quote_product
from common.round3.state import dump_state, load_state


HYDROGEL_BASE_LIMIT = 40
VE_PARTIAL_HEDGE_LIMIT = 80
LIQUID_VOUCHERS = ("VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500")

LINEAR_CONFIGS: Dict[str, LinearConfig] = {
    HYDROGEL_PACK: LinearConfig(HYDROGEL_BASE_LIMIT, 0.30, 4.0, HYDROGEL_BASE_LIMIT, HYDROGEL_BASE_LIMIT, 3.0, 3),
    VELVETFRUIT_EXTRACT: LinearConfig(200, 0.18, 2.5, 16, 24, 2.0, 2),
}

LATE_SESSION_TS = 850_000
CLOSEOUT_TS = 950_000

OPTION_LIMIT = 300
OPTION_BASE_SOFT_CAP = 70
OPTION_LATE_SOFT_CAP = 45
OPTION_CLOSEOUT_SOFT_CAP = 25
OPTION_BASE_PASSIVE_SIZE = 6
OPTION_BASE_TAKER_CAP = 10
OPTION_MIN_FAIR_VALUE = 3.0
OPTION_SURFACE_ALPHA = 0.10
OPTION_OFFSET_CLAMP = 0.03


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def hydrogel_limit_for_time(timestamp: int) -> int:
    if timestamp >= CLOSEOUT_TS:
        return 15
    if timestamp >= LATE_SESSION_TS:
        return 25
    return HYDROGEL_BASE_LIMIT


def option_soft_cap_for_time(timestamp: int) -> int:
    if timestamp >= CLOSEOUT_TS:
        return OPTION_CLOSEOUT_SOFT_CAP
    if timestamp >= LATE_SESSION_TS:
        return OPTION_LATE_SOFT_CAP
    return OPTION_BASE_SOFT_CAP


def option_size_for_time(timestamp: int) -> Tuple[int, int]:
    if timestamp >= CLOSEOUT_TS:
        return 4, 6
    if timestamp >= LATE_SESSION_TS:
        return 6, 8
    return OPTION_BASE_PASSIVE_SIZE, OPTION_BASE_TAKER_CAP


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        trader_state = load_state(state.traderData, DEFAULT_IV)
        result: Dict[Symbol, List[Order]] = {}
        timestamp = int(state.timestamp)
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

        underlying_fair = linear_fair_values.get(VELVETFRUIT_EXTRACT)
        if underlying_fair is not None:
            iv_ema = trader_state["iv_ema"]
            anchor_ivs = collect_anchor_ivs(state.order_depths, underlying_fair, option_tte_years)
            if anchor_ivs:
                iv_ema = ema(iv_ema, sum(anchor_ivs) / len(anchor_ivs), 0.15)
            trader_state["iv_ema"] = clamp(iv_ema, MIN_IV, MAX_IV)
            self._update_surface_offsets(state, trader_state, underlying_fair, option_tte_years)

        option_metrics: Dict[str, Tuple[float, float]] = {}
        if underlying_fair is not None:
            for symbol in LIQUID_VOUCHERS:
                if symbol not in state.order_depths:
                    continue
                strike = strike_from_symbol(symbol)
                offset = clamp(trader_state["iv_offset_ema"].get(symbol, 0.0), -OPTION_OFFSET_CLAMP, OPTION_OFFSET_CLAMP)
                fair_iv = clamp(trader_state["iv_ema"] + offset, MIN_IV, MAX_IV)
                fair_value = black_scholes_call(underlying_fair, strike, option_tte_years, fair_iv)
                delta = black_scholes_delta(underlying_fair, strike, option_tte_years, fair_iv)
                option_metrics[symbol] = (fair_value, delta)

        net_option_delta = 0.0
        for symbol, (_, delta) in option_metrics.items():
            net_option_delta += state.position.get(symbol, 0) * delta

        ve_target = int(round(-0.35 * net_option_delta))
        ve_target = int(clamp(float(ve_target), -VE_PARTIAL_HEDGE_LIMIT, VE_PARTIAL_HEDGE_LIMIT))
        if timestamp >= CLOSEOUT_TS:
            ve_target = int(clamp(float(ve_target), -40.0, 40.0))

        hydrogel_depth = state.order_depths.get(HYDROGEL_PACK)
        hydrogel_fair = linear_fair_values.get(HYDROGEL_PACK)
        hydrogel_spread = trader_state["spread_ema"].get(HYDROGEL_PACK)
        if hydrogel_depth is not None and hydrogel_fair is not None and hydrogel_spread is not None:
            hydrogel_orders = compute_hydrogel_orders(
                HYDROGEL_PACK,
                hydrogel_limit_for_time(timestamp),
                hydrogel_depth,
                hydrogel_fair,
                hydrogel_spread,
                state.position.get(HYDROGEL_PACK, 0),
            )
            if hydrogel_orders:
                result[HYDROGEL_PACK] = hydrogel_orders

        ve_depth = state.order_depths.get(VELVETFRUIT_EXTRACT)
        ve_fair = linear_fair_values.get(VELVETFRUIT_EXTRACT)
        if ve_depth is not None and ve_fair is not None:
            config = LINEAR_CONFIGS[VELVETFRUIT_EXTRACT]
            spread_ema = trader_state["spread_ema"].get(VELVETFRUIT_EXTRACT, float(config.min_half_width * 2))
            half_width = max(config.min_half_width, int(round(spread_ema / 2.0)))
            passive_size = config.passive_size if timestamp < LATE_SESSION_TS else max(8, config.passive_size - 4)
            taker_cap = config.taker_cap if timestamp < LATE_SESSION_TS else max(12, config.taker_cap - 6)
            inventory_error = state.position.get(VELVETFRUIT_EXTRACT, 0) - ve_target
            reservation_price = ve_fair - (config.inventory_skew_ticks * inventory_error / max(config.limit, 1))
            ve_orders = quote_product(
                VELVETFRUIT_EXTRACT,
                ve_depth,
                reservation_price,
                config.limit,
                state.position.get(VELVETFRUIT_EXTRACT, 0),
                passive_size,
                taker_cap,
                config.take_edge,
                half_width,
            )
            if ve_orders:
                result[VELVETFRUIT_EXTRACT] = ve_orders

        for symbol, (fair_value, _) in option_metrics.items():
            order_depth = state.order_depths.get(symbol)
            if order_depth is None or fair_value < OPTION_MIN_FAIR_VALUE:
                continue
            option_orders = self._quote_option(
                product=symbol,
                order_depth=order_depth,
                fair_value=fair_value,
                current_position=state.position.get(symbol, 0),
                timestamp=timestamp,
            )
            if option_orders:
                result[symbol] = option_orders

        return result, 0, dump_state(trader_state)

    def _update_surface_offsets(
        self,
        state: TradingState,
        trader_state: Dict[str, object],
        underlying_fair: float,
        option_tte_years: float,
    ) -> None:
        iv_anchor = float(trader_state["iv_ema"])
        iv_offset_ema = trader_state["iv_offset_ema"]
        for symbol in LIQUID_VOUCHERS:
            stats = book_stats(state.order_depths.get(symbol))
            if stats is None:
                continue
            market_iv = implied_volatility(underlying_fair, strike_from_symbol(symbol), option_tte_years, stats[2])
            if market_iv is None:
                continue
            observed_offset = clamp(market_iv - iv_anchor, -0.05, 0.05)
            previous = iv_offset_ema.get(symbol)
            smoothed = ema(previous, observed_offset, OPTION_SURFACE_ALPHA)
            iv_offset_ema[symbol] = clamp(smoothed, -OPTION_OFFSET_CLAMP, OPTION_OFFSET_CLAMP)

    def _quote_option(
        self,
        product: str,
        order_depth: OrderDepth,
        fair_value: float,
        current_position: int,
        timestamp: int,
    ) -> List[Order]:
        stats = book_stats(order_depth)
        if stats is None:
            return []

        best_bid, best_ask, mid_price, spread = stats
        soft_cap = option_soft_cap_for_time(timestamp)
        passive_size, taker_cap = option_size_for_time(timestamp)
        entry_edge = max(1.5, spread * 0.6, fair_value * 0.012)
        passive_edge = max(1.0, spread * 0.4, fair_value * 0.008)
        flatten_edge = max(1.0, spread * 0.5)

        orders: List[Order] = []
        buy_cap = max(0, min(OPTION_LIMIT - current_position, soft_cap - current_position))
        sell_cap = max(0, min(OPTION_LIMIT + current_position, soft_cap + current_position))

        remaining_taker_buy = min(taker_cap, buy_cap)
        for ask_price, ask_volume in sorted(order_depth.sell_orders.items()):
            if ask_price > fair_value - entry_edge or remaining_taker_buy <= 0:
                break
            quantity = min(-ask_volume, remaining_taker_buy)
            if quantity > 0:
                orders.append(Order(product, ask_price, quantity))
                current_position += quantity
                remaining_taker_buy -= quantity
                buy_cap -= quantity

        remaining_taker_sell = min(taker_cap, sell_cap)
        for bid_price, bid_volume in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid_price < fair_value + entry_edge or remaining_taker_sell <= 0:
                break
            quantity = min(bid_volume, remaining_taker_sell)
            if quantity > 0:
                orders.append(Order(product, bid_price, -quantity))
                current_position -= quantity
                remaining_taker_sell -= quantity
                sell_cap -= quantity

        if timestamp >= CLOSEOUT_TS:
            flatten_orders = self._inventory_reduction_orders(
                product,
                best_bid,
                best_ask,
                fair_value,
                current_position,
                buy_cap,
                sell_cap,
                min(passive_size, max(6, abs(current_position))),
                flatten_edge,
            )
            orders.extend(flatten_orders)
            return orders

        residual = mid_price - fair_value
        if residual <= -passive_edge and buy_cap > 0:
            bid_price = min(best_ask - 1, int(math.floor(fair_value - flatten_edge)))
            bid_price = max(0, bid_price)
            quantity = min(passive_size, buy_cap)
            if quantity > 0:
                orders.append(Order(product, bid_price, quantity))
        elif residual >= passive_edge and sell_cap > 0:
            ask_price = max(best_bid + 1, int(math.ceil(fair_value + flatten_edge)))
            quantity = min(passive_size, sell_cap)
            if quantity > 0:
                orders.append(Order(product, ask_price, -quantity))
        else:
            flatten_orders = self._inventory_reduction_orders(
                product,
                best_bid,
                best_ask,
                fair_value,
                current_position,
                buy_cap,
                sell_cap,
                passive_size,
                flatten_edge,
            )
            orders.extend(flatten_orders)

        return orders

    def _inventory_reduction_orders(
        self,
        product: str,
        best_bid: int,
        best_ask: int,
        fair_value: float,
        current_position: int,
        buy_cap: int,
        sell_cap: int,
        passive_size: int,
        flatten_edge: float,
    ) -> List[Order]:
        if current_position > 0 and sell_cap > 0:
            ask_price = max(best_bid + 1, int(math.ceil(fair_value + flatten_edge)))
            quantity = min(passive_size, sell_cap, current_position)
            if quantity > 0:
                return [Order(product, ask_price, -quantity)]
        if current_position < 0 and buy_cap > 0:
            bid_price = min(best_ask - 1, int(math.floor(fair_value - flatten_edge)))
            bid_price = max(0, bid_price)
            quantity = min(passive_size, buy_cap, -current_position)
            if quantity > 0:
                return [Order(product, bid_price, quantity)]
        return []
