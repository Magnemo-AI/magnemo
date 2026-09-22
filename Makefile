# Magnemo — the few verbs a maintainer runs. Stdlib only; nothing here needs a paid service.
.PHONY: test bench

test:
	python3 -m pytest -q

bench:      ## the in-house bench (P-67): numbers in bench/results/<version>.md, method in bench/run.py
	python3 bench/run.py
