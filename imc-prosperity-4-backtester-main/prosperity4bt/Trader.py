import json
from typing import Any

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )

        # We truncate state.traderData, trader_data, and self.logs to the same max. length to fit the log limit
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])

        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]

        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )

        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])

        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        lo, hi = 0, min(len(value), max_length)
        out = ""

        while lo <= hi:
            mid = (lo + hi) // 2

            candidate = value[:mid]
            if len(candidate) < len(value):
                candidate += "..."

            encoded_candidate = json.dumps(candidate)

            if len(encoded_candidate) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1

        return out

logger = Logger()
class Emerald:
    def __init__(self):
        self.mean_price = 10000
        self.max_pos = 80
    def computeOrders(self,product,order_depth,current_pos, price_history=[]):
        orders = []

        for price, amount in order_depth.sell_orders.items():
            if price < self.mean_price and current_pos < self.max_pos:
                buy_qty = min(-amount, self.max_pos - current_pos)
                orders.append(Order(product, price, buy_qty))
                current_pos += buy_qty
        for price, amount in order_depth.buy_orders.items():
            if price > self.mean_price and current_pos > -self.max_pos:
                sell_qty = max(-amount, -self.max_pos - current_pos)
                orders.append(Order(product, price, sell_qty))
                current_pos += sell_qty
        
        room_to_buy = self.max_pos - current_pos
        room_to_sell = -self.max_pos - current_pos
        if room_to_buy > 0:
            orders.append(Order(product, self.mean_price - 7, room_to_buy))
        
        if room_to_sell < 0:
            orders.append(Order(product, self.mean_price + 7, room_to_sell))
        return orders

class Tomato:
    def __init__(self):
        self.max_pos = 80
        self.window_size = 20
        self.alpha = 0.3

    def computeOrders(self, product, order_depth, current_pos, history):
        orders = []
        if not order_depth.sell_orders or not order_depth.buy_orders:
            return orders
        
        best_ask = min(order_depth.sell_orders.keys())
        best_bid = max(order_depth.buy_orders.keys())
        current_mid = (best_ask + best_bid) / 2
        current_spread = best_ask - best_bid
        if len(history) < 2:
            price_ema = current_mid
            spread_ema = current_spread
        else:
            price_ema = (self.alpha * current_mid) + (1 - self.alpha) * history[0]
            spread_ema = (self.alpha * current_spread) + (1 - self.alpha) * history[1]

        offset = max(3, (spread_ema / 2) - 3)

        for price, amount in order_depth.sell_orders.items():
            if price < price_ema - (offset + 1) and current_pos < self.max_pos:
                qty = min(-amount, self.max_pos - current_pos)
                orders.append(Order(product, price, qty))
                current_pos += qty

        for price, amount in order_depth.buy_orders.items():
            if price > price_ema + (offset + 1) and current_pos > -self.max_pos:
                qty = max(-amount, -self.max_pos - current_pos)
                orders.append(Order(product, price, qty))
                current_pos += qty
        
        if current_pos < self.max_pos:
            bid_price = int(price_ema - offset)
            bid_price = min(bid_price, best_bid + 1)
            orders.append(Order(product, bid_price, self.max_pos - current_pos))

        if current_pos > -self.max_pos:
            ask_price = int(price_ema + offset)
            ask_price = max(ask_price, best_ask - 1)
            orders.append(Order(product, ask_price, -self.max_pos - current_pos))
        history[:] = [price_ema, spread_ema]
        return orders


class Trader:
    def __init__(self):
        self.strategies = {
            "EMERALDS" : Emerald(),
            "TOMATOES" : Tomato(),
        }
        self.history = {"TOMATOES": [], "EMERALDS": []}

    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        result = {}
        conversions = 0
        trader_data = ""

        for product in state.order_depths:
            order_depth = state.order_depths[product]
            current_pos = state.position.get(product, 0)
            
            strategy = self.strategies[product]
            result[product] = strategy.computeOrders(product, order_depth, current_pos, self.history[product])


        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data