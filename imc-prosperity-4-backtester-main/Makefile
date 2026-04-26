.PHONY: submissions round3-basic round3-max round3-surface round3-air round3-robust round3-robust-v2 round3-robust-v3 round3-linear backtest clean-submit

STRATEGY ?= round_3_air
ROUND ?= 3
BACKTEST_FLAGS ?= --no-vis --no-progress --no-out

submissions: round3-basic round3-max round3-surface round3-air round3-robust round3-robust-v2 round3-robust-v3 round3-linear

round3-basic:
	python scripts/build_strategy.py strategies/round_3_basic_dev.py

round3-max:
	python scripts/build_strategy.py strategies/round_3_max_dev.py

round3-surface:
	python scripts/build_strategy.py strategies/round_3_surface_dev.py

round3-air:
	python scripts/build_strategy.py strategies/round_3_air_dev.py

round3-robust:
	python scripts/build_strategy.py strategies/round_3_robust_dev.py

round3-robust-v2:
	python scripts/build_strategy.py strategies/round_3_robust_v2_dev.py

round3-robust-v3:
	python scripts/build_strategy.py strategies/round_3_robust_v3_dev.py

round3-linear:
	python scripts/build_strategy.py strategies/round_3_linear_dev.py

backtest:
	PYTHONPATH=prosperity4bt python -m prosperity4bt submit/$(STRATEGY).py $(ROUND) $(BACKTEST_FLAGS)

clean-submit:
	rm -f submit/round_3_basic.py submit/round_3_max.py submit/round_3_surface.py submit/round_3_air.py submit/round_3_robust.py submit/round_3_robust_v2.py submit/round_3_robust_v3.py submit/round_3_linear.py
