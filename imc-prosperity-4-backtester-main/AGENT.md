# AGENT.md

## Goal

Use this repository to do two things:

1. Set up and run the Prosperity 4 backtester locally.
2. Implement or iterate on a trading algorithm that exposes a `Trader` class.

This file is for an agent working inside this repo. Prefer small, testable changes and keep the algorithm isolated from backtester internals.

## Repository Facts

- Entry point: `python -m prosperity4bt`
- CLI implementation: `prosperity4bt/__main__.py`
- Backtest orchestration: `prosperity4bt/back_tester.py`
- Per-timestamp simulation: `prosperity4bt/test_runner.py`
- Shared competition data model: `prosperity4bt/datamodel.py`
- Product position limits: `prosperity4bt/constants.py`
- Example strategy file: `prosperity4bt/Trader.py`
- Bundled historical data: `prosperity4bt/resources/round0` through `round3`

Do not change `prosperity4bt/datamodel.py` unless the user explicitly asks for compatibility-breaking work.

## Environment Setup

This repo is configured for `uv` and requires Python `>=3.13` in `pyproject.toml`.

Recommended setup:

```bash
uv sync
```

Run commands through the managed environment:

```bash
uv run python -m prosperity4bt --help
```

If `uv` is not available but Python 3.13 is, the fallback is:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m prosperity4bt --help
```

## How To Run The Backtester

Run a strategy against all days in a round:

```bash
uv run python -m prosperity4bt path/to/strategy.py 0
```

Run a strategy against a single day:

```bash
uv run python -m prosperity4bt path/to/strategy.py 0--2
```

The CLI parser actually expects a single argument in the form `<round>-<day>`. For negative days that means:

```bash
uv run python -m prosperity4bt path/to/strategy.py 0--2
uv run python -m prosperity4bt path/to/strategy.py 1--1
uv run python -m prosperity4bt path/to/strategy.py 2-0
```

Useful options:

```bash
uv run python -m prosperity4bt path/to/strategy.py 0 --print
uv run python -m prosperity4bt path/to/strategy.py 0 --no-vis
uv run python -m prosperity4bt path/to/strategy.py 0 --no-progress
uv run python -m prosperity4bt path/to/strategy.py 0 --out backtests/manual.log
uv run python -m prosperity4bt path/to/strategy.py 0 --match-trades server_like
```

Notes:

- Default output file: `backtests/<timestamp>.log`
- `--no-out` disables log file creation.
- `--data <dir>` lets you point at an alternate data directory.

## Strategy Contract

The algorithm module must expose a class named `Trader`.

The backtester imports the module, instantiates `Trader()`, and repeatedly calls:

```python
orders, conversions, trader_data = trader.run(state)
```

Expected behavior:

- `state` is a `TradingState` from `prosperity4bt/datamodel.py`
- `orders` is `dict[str, list[Order]]`
- `conversions` is an `int`
- `trader_data` is a `str`

Relevant `TradingState` fields:

- `state.timestamp`
- `state.order_depths`
- `state.position`
- `state.own_trades`
- `state.market_trades`
- `state.observations`
- `state.traderData`

Use `state.traderData` to persist compact strategy state across timestamps.

## Where To Put The Algorithm

Preferred approach:

- Create or edit a standalone strategy file outside the backtester package, for example `strategies/my_trader.py`.
- Keep the backtester code unchanged unless the user asks for framework changes.

Minimal template:

```python
from datamodel import Order, TradingState


class Trader:
    def run(self, state: TradingState):
        orders = {}
        conversions = 0
        trader_data = state.traderData

        for product, depth in state.order_depths.items():
            product_orders = []

            if depth.sell_orders:
                best_ask = min(depth.sell_orders)
                product_orders.append(Order(product, best_ask, 1))

            if product_orders:
                orders[product] = product_orders

        return orders, conversions, trader_data
```

If the strategy imports `datamodel` directly and Python cannot find it, run with:

```bash
PYTHONPATH=prosperity4bt uv run python -m prosperity4bt path/to/strategy.py 0
```

## Strategy Development Rules

When writing or modifying the algorithm:

- Respect the position limits in `prosperity4bt/constants.py`.
- Keep all order prices and quantities as integers.
- Return no orders for products you are not trading.
- Defensively handle empty books.
- Use `state.position.get(product, 0)` instead of assuming the key exists.
- Keep `trader_data` small; the logger truncates long values.
- Do not rely on backtester-only internals from inside the strategy if the goal is Prosperity compatibility.

## Recommended Workflow

1. Create a new strategy file.
2. Start with one product and a minimal signal.
3. Run one day only.
4. Inspect the output log and PnL.
5. Expand to more days, then more products.
6. Only after that, add stateful logic and cross-product behavior.

Example loop:

```bash
mkdir -p strategies
uv run python -m prosperity4bt strategies/my_trader.py 0--2 --no-vis --no-progress --print
uv run python -m prosperity4bt strategies/my_trader.py 0 --no-vis
uv run python -m prosperity4bt strategies/my_trader.py 1 2 3 --no-vis
```

## Debugging Notes

- If the CLI says the algorithm file does not expose a `Trader` class, check the class name and module import errors.
- If you hit `No module named 'datamodel'`, set `PYTHONPATH=prosperity4bt`.
- If orders exceed product limits, `test_runner.py` drops that product's orders and records a sandbox warning.
- `print()` output from the strategy is captured into the lambda log; `--print` mirrors it to stdout during execution.

## What To Change And What Not To Change

Usually safe to change:

- a strategy file you created
- `README.md` or docs
- tests or helper scripts added for strategy iteration

Avoid changing unless required:

- `prosperity4bt/datamodel.py`
- order-matching logic
- input parsing and bundled historical data

If the user asks to "write the algorithm", implement it in a dedicated strategy file and validate it with at least one backtest command.
