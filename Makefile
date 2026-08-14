.PHONY: test test-security evaluate benchmark verify

test:
	pytest

test-security:
	bandit -r services/api sdk/memoryops-sdk/memoryops_sdk

evaluate:
	python evals/runner.py

benchmark:
	python evals/benchmark.py

verify:
	black --check services/api tests
	flake8 services/api tests --count --max-line-length=127 --statistics
	mypy services/api tests --ignore-missing-imports
	bandit -r services/api sdk/memoryops-sdk/memoryops_sdk
	pytest
	python evals/runner.py
