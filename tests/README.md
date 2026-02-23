# Testing Guide

## Overview

This project uses `pytest` as the test framework, with three categories of tests.

## Test Structure

```
tests/
├── conftest.py                          # Shared fixtures (stock data, mock providers)
├── unit/                                # Unit tests (fast, isolated, no I/O)
│   ├── test_exceptions.py               # Exception hierarchy
│   ├── test_data_provider.py            # Data provider validation logic
│   └── test_backtest_components.py      # Backtest validator & analyzer
├── integration/                         # Integration tests (cross-module, mock network)
│   ├── conftest.py                      # Integration-specific fixtures
│   ├── test_data_pipeline.py            # Provider selection -> cache -> normalize
│   └── test_strategy_backtest.py        # Strategy + backtest full cycle
└── web/                                 # E2E tests (Playwright + Streamlit)
    ├── conftest.py                      # Streamlit server fixture & helpers
    ├── test_ai_panel.py                 # AI analyst panel interaction
    └── test_page_navigation.py          # Page load & cross-page navigation
```

## Install Dependencies

```bash
# Core test dependencies
pip install pytest pytest-cov pytest-mock

# E2E test dependencies (web/)
pip install pytest-playwright
playwright install chromium
```

## Running Tests

### By category

```bash
# Unit tests only (fast)
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Web E2E tests only (requires Streamlit server)
pytest tests/web/

# All tests
pytest
```

### By marker

```bash
pytest -m unit          # Unit tests
pytest -m integration   # Integration tests
pytest -m web           # E2E browser tests
pytest -m "not slow"    # Skip slow tests
pytest -m "not network" # Skip network-dependent tests
```

### Specific file or test

```bash
pytest tests/unit/test_exceptions.py
pytest tests/unit/test_exceptions.py::TestExceptionHierarchy::test_base_exception
```

## Coverage

```bash
pytest --cov=quant --cov-report=term-missing
pytest --cov=quant --cov-report=html && open htmlcov/index.html
```

## Coverage Targets

| Layer | Directory | Target |
|-------|-----------|--------|
| Core | `quant/core/` | 80%+ |
| Data | `quant/data/` | 70%+ |
| Strategies | `quant/strategies/` | 60%+ |
| Analysis | `quant/analysis/` | 50%+ |

## Writing Tests

### Naming conventions
- Files: `test_*.py`
- Classes: `Test*`
- Methods: `test_*`

### Pattern
Follow Arrange-Act-Assert. Each test should verify one behavior.

```python
def test_valid_symbol(mock_provider):
    # Arrange — fixture provides mock_provider
    # Act
    mock_provider._validate_symbol('000001.SZ')
    # Assert — no exception raised
```

## Debugging

```bash
pytest -s          # Show print output
pytest -vv         # Verbose error details
pytest -x          # Stop on first failure
pytest --durations=10  # Show slowest tests
```
