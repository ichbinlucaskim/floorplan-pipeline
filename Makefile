.PHONY: setup test lint demo clean

setup:
	cd .. && python scripts/sync_licenses.py
	pip install -e ../aec-schema
	pip install -e ../wall-extract
	pip install -e ../panel-decompose
	pip install -e ../framing-synth
	pip install -e ../assembly-sequence
	pip install -e ../aec-ifc-export
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v

lint:
	ruff check src/ tests/

demo:
	python scripts/demo.py

clean:
	rm -rf __pycache__ src/floorplan_pipeline/__pycache__ tests/__pycache__ \
	       .pytest_cache .ruff_cache *.egg-info src/*.egg-info examples/out out
