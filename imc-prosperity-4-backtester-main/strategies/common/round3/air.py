import math
from typing import Dict, List, Tuple

from datamodel import Order, OrderDepth, Symbol, TradingState

from common.round3.config import DEFAULT_IV, HYDROGEL_PACK, LinearConfig, MAX_IV, MIN_IV, VELVETFRUIT_EXTRACT
from common.round3.pricing import black_scholes_call, book_stats, collect_anchor_ivs, ema, option_tte_years_for_state, strike_from_symbol, voucher_symbols
from common.round3.quoting import compute_hydrogel_orders, quote_product
from common.round3.state import dump_state, load_state


HYDROGEL_MAX_POS = 40
OPTION_LIMIT = 300
OPTION_MIN_PREMIUM = 80.0
OPTION_SOFT_CAP_LOW = 80
OPTION_SOFT_CAP_HIGH = 160
OPTION_PASSIVE_SIZE_LOW = 8
OPTION_PASSIVE_SIZE_HIGH = 14
OPTION_TAKER_CAP_LOW = 10
OPTION_TAKER_CAP_HIGH = 18
OPTION_INVENTORY_SKEW_TICKS = 4.0

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

        underlying_fair = fair_values.get(VELVETFRUIT_EXTRACT)
        if underlying_fair is not None:
            iv_ema = trader_state["iv_ema"]
            anchor_ivs = collect_anchor_ivs(state.order_depths, underlying_fair, option_tte_years)
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

        if underlying_fair is not None:
            for symbol in voucher_symbols(state.order_depths):
                order_depth = state.order_depths.get(symbol)
                if order_depth is None:
                    continue
                strike = strike_from_symbol(symbol)
                fair_value = black_scholes_call(underlying_fair, strike, option_tte_years, trader_state["iv_ema"])
                if fair_value < OPTION_MIN_PREMIUM:
                    continue
                option_orders = self._quote_option(
                    product=symbol,
                    order_depth=order_depth,
                    fair_value=fair_value,
                    current_position=state.position.get(symbol, 0),
                )
                if option_orders:
                    result[symbol] = option_orders

        return result, 0, dump_state(trader_state)

    def _quote_option(
        self,
        product: str,
        order_depth: OrderDepth,
        fair_value: float,
        current_position: int,
    ) -> List[Order]:
        stats = book_stats(order_depth)
        if stats is None:
            return []

        best_bid, best_ask, mid_price, spread = stats
        soft_cap = OPTION_SOFT_CAP_HIGH if fair_value >= 180.0 else OPTION_SOFT_CAP_LOW
        passive_size = OPTION_PASSIVE_SIZE_HIGH if fair_value >= 180.0 else OPTION_PASSIVE_SIZE_LOW
        taker_cap = OPTION_TAKER_CAP_HIGH if fair_value >= 180.0 else OPTION_TAKER_CAP_LOW

        reservation_price = fair_value - (OPTION_INVENTORY_SKEW_TICKS * current_position / max(soft_cap, 1))
        half_width = max(2, int(round(spread / 2.0)))
        take_edge = max(3.0, spread)
        signal_edge = max(4.0, spread * 1.25)

        buy_cap = max(0, min(OPTION_LIMIT - current_position, soft_cap - current_position))
        sell_cap = max(0, min(OPTION_LIMIT + current_position, soft_cap + current_position))
        if buy_cap <= 0 and sell_cap <= 0:
            return []

        orders: List[Order] = []
        remaining_taker_buy = min(taker_cap, buy_cap)
        for ask_price, ask_volume in sorted(order_depth.sell_orders.items()):
            if ask_price > reservation_price - take_edge or remaining_taker_buy <= 0:
                break
            quantity = min(-ask_volume, remaining_taker_buy)
            if quantity > 0:
                orders.append(Order(product, ask_price, quantity))
                current_position += quantity
                remaining_taker_buy -= quantity
                buy_cap -= quantity

        remaining_taker_sell = min(taker_cap, sell_cap)
        for bid_price, bid_volume in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid_price < reservation_price + take_edge or remaining_taker_sell <= 0:
                break
            quantity = min(bid_volume, remaining_taker_sell)
            if quantity > 0:
                orders.append(Order(product, bid_price, -quantity))
                current_position -= quantity
                remaining_taker_sell -= quantity
                sell_cap -= quantity

        residual = mid_price - reservation_price
        if residual <= -signal_edge and buy_cap > 0:
            bid_price = min(int(math.floor(reservation_price - half_width)), best_ask - 1)
            bid_price = max(0, bid_price)
            quantity = min(passive_size, buy_cap)
            if quantity > 0:
                orders.append(Order(product, bid_price, quantity))
        elif residual >= signal_edge and sell_cap > 0:
            ask_price = max(int(math.ceil(reservation_price + half_width)), best_bid + 1)
            quantity = min(passive_size, sell_cap)
            if quantity > 0:
                orders.append(Order(product, ask_price, -quantity))
        else:
            if current_position > 0 and sell_cap > 0:
                ask_price = max(best_bid + 1, int(math.ceil(reservation_price + half_width)))
                quantity = min(passive_size, sell_cap, current_position)
                if quantity > 0:
                    orders.append(Order(product, ask_price, -quantity))
            elif current_position < 0 and buy_cap > 0:
                bid_price = min(best_ask - 1, int(math.floor(reservation_price - half_width)))
                bid_price = max(0, bid_price)
                quantity = min(passive_size, buy_cap, -current_position)
                if quantity > 0:
                    orders.append(Order(product, bid_price, quantity))

        return orders
