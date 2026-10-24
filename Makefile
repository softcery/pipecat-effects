.PHONY: lint test test-lowest audit build

lint:
	uv lock --check
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright

test:
	uv run pytest -q

# the floor of each direct dependency, on the floor of requires-python
test-lowest:
	uv run --isolated --python 3.12 --resolution lowest-direct pytest -q

audit:
	uv audit --locked --preview-features audit-command

build:
	uv build
