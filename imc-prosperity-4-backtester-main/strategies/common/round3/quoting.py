import math
from typing import List, Optional

from datamodel import Order, OrderDepth

from common.round3.pricing import book_stats


def compute_hydrogel_orders(
    product: str,
    max_position: int,
    order_depth: OrderDepth,
    price_ema: float,
    spread_ema: float,
    current_position: int,
) -> List[Order]:
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return []

    best_bid = max(order_depth.buy_orders)
    best_ask = min(order_depth.sell_orders)
    offset = max(3.0, (spread_ema / 2.0) - 3.0)
    orders: List[Order] = []

    for ask_price, ask_volume in sorted(order_depth.sell_orders.items()):
        if ask_price < price_ema - (offset + 1.0) and current_position < max_position:
            quantity = min(-ask_volume, max_position - current_position)
            if quantity > 0:
                orders.append(Order(product, ask_price, quantity))
                current_position += quantity

    for bid_price, bid_volume in sorted(order_depth.buy_orders.items(), reverse=True):
        if bid_price > price_ema + (offset + 1.0) and current_position > -max_position:
            quantity = min(bid_volume, max_position + current_position)
            if quantity > 0:
                orders.append(Order(product, bid_price, -quantity))
                current_position -= quantity

    room_to_buy = max_position - current_position
    if room_to_buy > 0:
        orders.append(Order(product, min(int(price_ema - offset), best_bid + 1), room_to_buy))

    room_to_sell = max_position + current_position
    if room_to_sell > 0:
        orders.append(Order(product, max(int(price_ema + offset), best_ask - 1), -room_to_sell))

    return orders


def quote_product(
    product: str,
    order_depth: OrderDepth,
    reservation_price: float,
    limit: int,
    current_position: int,
    passive_size: int,
    taker_cap: int,
    take_edge: float,
    half_width: int,
    passive_long_limit: Optional[int] = None,
    passive_short_limit: Optional[int] = None,
) -> List[Order]:
    stats = book_stats(order_depth)
    if stats is None:
        return []

    best_bid, best_ask = stats[0], stats[1]
    orders: List[Order] = []
    buy_capacity = max(0, limit - current_position)
    sell_capacity = max(0, limit + current_position)
    used_buy = 0
    used_sell = 0

    remaining_taker_buy = min(taker_cap, buy_capacity)
    for ask_price, ask_volume in sorted(order_depth.sell_orders.items()):
        if ask_price > reservation_price - take_edge or remaining_taker_buy <= 0:
            break
        quantity = min(-ask_volume, remaining_taker_buy)
        if quantity > 0:
            orders.append(Order(product, ask_price, quantity))
            used_buy += quantity
            remaining_taker_buy -= quantity

    remaining_taker_sell = min(taker_cap, sell_capacity)
    for bid_price, bid_volume in sorted(order_depth.buy_orders.items(), reverse=True):
        if bid_price < reservation_price + take_edge or remaining_taker_sell <= 0:
            break
        quantity = min(bid_volume, remaining_taker_sell)
        if quantity > 0:
            orders.append(Order(product, bid_price, -quantity))
            used_sell += quantity
            remaining_taker_sell -= quantity

    remaining_buy = max(0, buy_capacity - used_buy)
    remaining_sell = max(0, sell_capacity - used_sell)
    position_after_takers = current_position + used_buy - used_sell

    if passive_long_limit is None:
        passive_long_limit = limit
    if passive_short_limit is None:
        passive_short_limit = limit

    if position_after_takers < passive_long_limit and remaining_buy > 0:
        bid_price = min(int(math.floor(reservation_price - half_width)), best_ask - 1)
        bid_price = max(0, bid_price)
        bid_quantity = min(passive_size, remaining_buy, passive_long_limit - position_after_takers)
        if bid_quantity > 0:
            orders.append(Order(product, bid_price, bid_quantity))

    if position_after_takers > -passive_short_limit and remaining_sell > 0:
        ask_price = max(int(math.ceil(reservation_price + half_width)), best_bid + 1)
        ask_quantity = min(passive_size, remaining_sell, passive_short_limit + position_after_takers)
        if ask_quantity > 0:
            orders.append(Order(product, ask_price, -ask_quantity))

    return orders
