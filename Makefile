.PHONY: install run

install:
	uv pip install -e .

run:
	uv run python main.py
