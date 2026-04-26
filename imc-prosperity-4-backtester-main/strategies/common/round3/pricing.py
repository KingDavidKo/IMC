import math
from typing import Dict, Iterable, List, Optional, Tuple

from datamodel import OrderDepth, Symbol, TradingState

from common.round3.config import ANCHOR_VOUCHERS, MAX_IV, MIN_IV, OPTION_TTE_YEARS


BACKTEST_ROUND_META_KEY = "__bt_round_num"
BACKTEST_DAY_META_KEY = "__bt_day_num"


def voucher_symbols(
    order_depths: Dict[Symbol, OrderDepth],
    active_vouchers: Optional[Iterable[str]] = None,
) -> List[str]:
    if active_vouchers is not None:
        return [symbol for symbol in active_vouchers if symbol in order_depths]
    symbols = [symbol for symbol in order_depths if symbol.startswith("VEV_")]
    return sorted(symbols, key=strike_from_symbol)


def strike_from_symbol(symbol: str) -> int:
    return int(symbol.split("_", 1)[1])


def book_stats(order_depth: Optional[OrderDepth]) -> Optional[Tuple[int, int, float, float]]:
    if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
        return None
    best_bid = max(order_depth.buy_orders)
    best_ask = min(order_depth.sell_orders)
    return best_bid, best_ask, (best_bid + best_ask) / 2.0, float(best_ask - best_bid)


def ema(previous: Optional[float], value: float, alpha: float) -> float:
    if previous is None:
        return value
    return alpha * value + (1.0 - alpha) * previous


def black_scholes_call(spot: float, strike: int, time_to_expiry: float, volatility: float) -> float:
    intrinsic = max(spot - strike, 0.0)
    if time_to_expiry <= 0.0 or volatility <= 0.0 or spot <= 0.0:
        return intrinsic

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + 0.5 * volatility * volatility * time_to_expiry) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    return spot * normal_cdf(d1) - strike * normal_cdf(d2)


def black_scholes_delta(spot: float, strike: int, time_to_expiry: float, volatility: float) -> float:
    if time_to_expiry <= 0.0 or volatility <= 0.0 or spot <= 0.0:
        return 1.0 if spot > strike else 0.0

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + 0.5 * volatility * volatility * time_to_expiry) / (volatility * sqrt_t)
    return normal_cdf(d1)


def implied_volatility(
    spot: float,
    strike: int,
    time_to_expiry: float,
    option_price: float,
) -> Optional[float]:
    intrinsic = max(spot - strike, 0.0)
    target_price = max(option_price, intrinsic)
    low = MIN_IV
    high = MAX_IV
    low_price = black_scholes_call(spot, strike, time_to_expiry, low)
    high_price = black_scholes_call(spot, strike, time_to_expiry, high)

    if target_price <= low_price:
        return low
    if target_price >= high_price:
        return high

    for _ in range(50):
        mid = (low + high) / 2.0
        mid_price = black_scholes_call(spot, strike, time_to_expiry, mid)
        if mid_price < target_price:
            low = mid
        else:
            high = mid

    return (low + high) / 2.0


def option_tte_years_for_state(state: TradingState) -> float:
    observations = getattr(state, "observations", None)
    plain_observations = getattr(observations, "plainValueObservations", None)
    if not isinstance(plain_observations, dict):
        return OPTION_TTE_YEARS

    round_num = plain_observations.get(BACKTEST_ROUND_META_KEY)
    day_num = plain_observations.get(BACKTEST_DAY_META_KEY)

    # Prosperity rounds are typically 3 days. TTE should decrease accordingly.
    # We'll use a base of 3 days if metadata is present, otherwise fallback to config.
    if isinstance(round_num, (int, float)) and int(round_num) == 3 and isinstance(day_num, (int, float)):
        # If we are in the backtester for round 3, use a 3-day countdown.
        # Ensure we don't hit 0 TTE which causes div by zero in BS.
        days_left = max(0.5, 3.0 - float(day_num))
        return days_left / 365.0

    return OPTION_TTE_YEARS


def collect_anchor_ivs(order_depths: Dict[Symbol, OrderDepth], spot: float, time_to_expiry: float) -> List[float]:
    anchor_ivs: List[float] = []
    for symbol in ANCHOR_VOUCHERS:
        stats = book_stats(order_depths.get(symbol))
        if stats is None:
            continue
        implied_vol = implied_volatility(spot, strike_from_symbol(symbol), time_to_expiry, stats[2])
        if implied_vol is not None:
            anchor_ivs.append(implied_vol)
    return anchor_ivs


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
