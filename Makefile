.PHONY: install format lint test run-auth run-mdg

install:
	python3 -m pip install -e ".[dev]"

format:
	ruff format .

lint:
	ruff check .

test:
	pytest

run-auth:
	python3 -m services.auth_service.app.main

run-mdg:
	python3 -m services.market_data_gateway.app.main