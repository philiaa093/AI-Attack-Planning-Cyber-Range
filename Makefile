PYTHON ?= python
validate:
	$(PYTHON) -B scripts/validation/validate_scaffold.py
test:
	$(PYTHON) -B -m unittest discover -s tests -p "test_*.py" -v
compile:
	$(PYTHON) -B -m compileall -q scripts tests
