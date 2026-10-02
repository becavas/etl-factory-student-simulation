.PHONY: env env-update install doctor format format-check lint test wheel inspect quality

env:
	conda env create -f environment.yml

env-update:
	conda env update -f environment.yml --prune

install:
	python -m pip install --no-deps --editable .

doctor:
	@bash scripts/doctor.sh

format:
	ruff format .

format-check:
	ruff format --check .

lint:
	ruff check .

test:
	python -m pytest

wheel:
	python -m build --wheel

inspect:
	python scripts/inspect_wheel.py dist/*.whl

quality: format-check lint test wheel inspect
