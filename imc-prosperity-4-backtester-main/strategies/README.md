# Strategies

This folder contains standalone strategy files for the Prosperity 4 backtester and Prosperity submissions.

## Round 3 Files

### `round_3_basic.py`

This is the first dedicated round 3 strategy.

It trades:

- `HYDROGEL_PACK`
- `VELVETFRUIT_EXTRACT`
- all `VEV_*` vouchers

Core ideas:

- EMA-based fair values for `HYDROGEL_PACK` and `VELVETFRUIT_EXTRACT`
- Black-Scholes call pricing for vouchers
- implied volatility estimated from `VEV_5100`, `VEV_5200`, and `VEV_5300`
- inventory-aware quoting

This version is useful as the clean base implementation for round 3 logic.

Submission note:

- standalone file
- imports only `datamodel` plus Python standard library
- does not depend on any other file in `strategies/`

### `round_3_max.py`

This is the tuned round 3 experiment file.

Main changes:

- disables the voucher delta hedge
- only trades the voucher strikes that were adding PnL in backtests:
  - `VEV_4000`
  - `VEV_4500`
  - `VEV_5100`
  - `VEV_5200`
- retunes `VELVETFRUIT_EXTRACT` quoting
- replaces the base Hydrogel logic with a stronger overlay using a tighter max position

Submission note:

- standalone file
- imports only `datamodel` plus Python standard library
- does not import `round3_trader.py`

### `round_3_air.py`

This is a less tuned round 3 variant intended to keep the stronger structural ideas
while avoiding the hardcoded strike whitelist and late-session option exits.

Main changes:

- keeps the `HYDROGEL_PACK` overlay from the stronger experiments
- keeps the more aggressive `VELVETFRUIT_EXTRACT` quoting
- prices vouchers from the central implied-vol anchors
- trades vouchers using a general premium/confidence filter instead of naming specific strikes
- flattens option inventory when the market is close to fair instead of warehousing both sides

Submission note:

- standalone file
- imports only `datamodel` plus Python standard library
- does not depend on any other file in `strategies/`

### `round_3_air_dev.py`

This is the editable multi-file entrypoint for `round_3_air.py`.

It imports the round 3 implementation from the shared `strategies/common/` library,
which is intended for code that should be reusable across strategies instead of living
inside one strategy-specific source folder.

### `round_3_robust_dev.py`

This is a new round 3 variant aimed at behaving more sensibly outside the bundled
backtests rather than maximizing local sample PnL.

Main changes:

- keeps the linear-product quoting simple and inventory-aware
- trades only the liquid middle voucher strikes:
  - `VEV_5000`
  - `VEV_5100`
  - `VEV_5200`
  - `VEV_5300`
  - `VEV_5400`
  - `VEV_5500`
- learns a small per-strike IV surface offset during the session instead of assuming
  every voucher should sit on one flat implied-vol anchor
- avoids broad two-sided option warehousing and cuts option risk late in the session
- uses only a partial delta hedge in `VELVETFRUIT_EXTRACT`

### `round_3_robust_v2_dev.py`

This is the more aggressive follow-up to `round_3_robust_dev.py`.

Main changes:

- increases `HYDROGEL_PACK` risk limits and keeps them higher later into the day
- makes `VELVETFRUIT_EXTRACT` quote larger and take tighter edges
- increases the partial hedge ratio against voucher delta so the strategy can carry
  more option risk without leaning entirely on unhedged directional exposure
- slightly loosens voucher caps and taker sizes, while keeping the same strike filter
  and closeout structure

### `round_3_robust_v3_dev.py`

This is the warmup-gated follow-up to `round_3_robust_v2_dev.py`.

Main changes:

- keeps the stronger `HYDROGEL_PACK` posture from `v2`
- keeps `VELVETFRUIT_EXTRACT` more active than the base robust variant, but less
  aggressive than `v2`
- reverts the voucher sleeve closer to the base robust risk caps
- waits for linear and option-surface observation counts to build up before trading,
  so early-session noise does not trigger decisions from unstable fair values

### `round_3_linear_dev.py`

This is a simpler round 3 delta-only strategy intended for live robustness rather than
voucher optimization on the bundled sample.

Main changes:

- trades only `HYDROGEL_PACK` and `VELVETFRUIT_EXTRACT`
- ignores all `VEV_*` vouchers
- blends fast/slow fair values with top-of-book imbalance
- uses lower self-imposed risk caps and more aggressive inventory flattening

### `round_3_basic_dev.py`, `round_3_max_dev.py`, `round_3_surface_dev.py`

These are editable multi-file entrypoints for the existing round 3 standalone files.

They import shared round 3 modules from `strategies/common/round3/` so new variants can
reuse pricing, state handling, quoting, and voucher utilities instead of copying the same
helper code into each standalone file.

## How To Run

From the repo root, use `PYTHONPATH=prosperity4bt` so local backtests can resolve `datamodel`:

```bash
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_basic.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_max.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_basic_dev.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_max_dev.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_surface_dev.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_air_dev.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_robust_dev.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_robust_v2_dev.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_robust_v3_dev.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_linear_dev.py 3 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_air.py 3 --no-vis --no-progress
```

Single day runs:

```bash
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_max.py 3-0 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_max.py 3-1 --no-vis --no-progress
PYTHONPATH=prosperity4bt python -m prosperity4bt strategies/round_3_max.py 3-2 --no-vis --no-progress
```

## Current Backtest Snapshot

Using the bundled round 3 sample data in this repository:

- `round_3_basic.py`: about `19,687`
- `round_3_max.py`: about `48,859`
- `round_3_air.py`: about `42,870`
- `round_3_robust_dev.py`: about `31,572`

Those numbers are from local backtests in this repo, not the official Prosperity site.

## Notes

- These files are intentionally separate so experiments do not overwrite the cleaner base round 3 implementation.
- The tuned file is optimized against the local backtester and bundled historical data. It should be treated as an experiment, not as a guaranteed live-optimal submission.
- The robust file is still based on the bundled local data, but it avoids the most explicit local tuning choices from `round_3_max.py`.

## Multi-File Workflow

For longer strategies, the intended pattern is:

- put reusable code in `strategies/common/`
- keep a small editable entrypoint such as `strategies/round_3_air_dev.py`
- build the final standalone submission file with `scripts/build_strategy.py`
- treat files under `submit/` as the generated submission artifacts

Current shared modules for round 3 live in:

- `strategies/common/round3/basic.py`
- `strategies/common/round3/max.py`
- `strategies/common/round3/surface.py`
- `strategies/common/round3/air.py`
- `strategies/common/round3/robust.py`
- `strategies/common/round3/robust_v2.py`
- `strategies/common/round3/robust_v3.py`
- `strategies/common/round3/linear.py`
- `strategies/common/round3/config.py`
- `strategies/common/round3/pricing.py`
- `strategies/common/round3/quoting.py`
- `strategies/common/round3/state.py`
- `strategies/common/single_file_builder.py`

Build standalone submission files into `submit/`:

```bash
python scripts/build_strategy.py strategies/round_3_basic_dev.py
python scripts/build_strategy.py strategies/round_3_max_dev.py
python scripts/build_strategy.py strategies/round_3_surface_dev.py
python scripts/build_strategy.py strategies/round_3_air_dev.py
python scripts/build_strategy.py strategies/round_3_robust_dev.py
python scripts/build_strategy.py strategies/round_3_robust_v2_dev.py
python scripts/build_strategy.py strategies/round_3_robust_v3_dev.py
python scripts/build_strategy.py strategies/round_3_linear_dev.py
```

That writes:

- `submit/round_3_basic.py`
- `submit/round_3_max.py`
- `submit/round_3_surface.py`
- `submit/round_3_air.py`
- `submit/round_3_robust.py`
- `submit/round_3_robust_v2.py`
- `submit/round_3_robust_v3.py`
- `submit/round_3_linear.py`

You can still override the output path explicitly:

```bash
python scripts/build_strategy.py strategies/round_3_air_dev.py /tmp/round_3_air.py
```

Or rebuild everything with `make submissions`.

Backtest a generated submission from `submit/`:

```bash
make backtest
make backtest STRATEGY=round_3_max ROUND=3-1
make backtest STRATEGY=round_3_surface ROUND=3 BACKTEST_FLAGS="--no-vis --no-progress"
```

`make backtest` defaults to:

- `STRATEGY=round_3_air`
- `ROUND=3`
- `BACKTEST_FLAGS=--no-vis --no-progress --no-out`

Recommended loop:

1. Edit the shared modules or a `*_dev.py` entrypoint.
2. Run `make submissions`.
3. Run `make backtest` or override `STRATEGY` / `ROUND` as needed.
4. Submit the generated file from `submit/`.

The generated files in `submit/` are the submission files.

## Parsing Prosperity Runs

The repository includes a reusable parser for Prosperity website JSON exports:

- script: `scripts/parse_imc_run.py`

It reads the raw website export and extracts:

- activity log rows
- graph log rows
- ending positions
- a compact summary with per-product PnL ranges and graph drawdown stats

Basic usage:

```bash
python scripts/parse_imc_run.py strategies/psp_surface/449947.json
```

Export normalized files for later analysis:

```bash
python scripts/parse_imc_run.py \
  strategies/psp_surface/449947.json \
  --out-dir strategies/psp_surface/449947_parsed
```

The export directory contains:

- `activities.csv`
- `graph.csv`
- `summary.json`

This is the recommended way to inspect live Prosperity runs before comparing them against local backtests.
