# Contributing to Smart Litter Detection System

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone git@github.com:DilyorbekAbdujabborov/smart-linter.git
cd smart-linter

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings
```

## Code Style

### Python

- **PEP 8** enforced
- **Type hints** on all function signatures and class attributes
- **`from __future__ import annotations`** at the top of every module
- **Docstrings** on every module, class, and public method
- **No `print()`** — use `get_logger(__name__)` from `logging_utils.py`
- **No `os.getenv()`** — use `from config import settings`

### Logging

```python
from logging_utils import get_logger
logger = get_logger(__name__)

logger.debug("Detailed diagnostic info")
logger.info("Normal operational messages")
logger.warning("Unexpected but recoverable")
logger.error("Operation failed")
```

### Configuration

```python
from config import settings

threshold = settings.conf_threshold
model = settings.yolo_model
# NEVER: os.getenv("CONF_THRESHOLD")
```

## Making Changes

### Adding a New Object Class

1. Add enum value to `ObjectClass` in `detector/types.py`
2. Update `is_trash` property if it is a trash class
3. Add COCO mapping(s) in `detector/detector.py` (`_COCO_TO_CLASS`)
4. No other files need changes

### Adding a New Detection Rule

1. Add the rule check in `detector/rule_engine.py`
2. Update the `_Phase` state machine if needed
3. Add any new thresholds to `config.py` and `.env.example`

### Adding a New API Endpoint

1. Add the route in `api/routes.py` inside `create_app()`
2. Add/update Pydantic schemas in `api/schemas.py`
3. Add corresponding database helper in `database/database.py` if needed

### Adding a New Database Field

1. Update the ORM model in `database/models.py`
2. Update `database.py` CRUD functions
3. Update `api/schemas.py` response models

## Testing

No test suite exists yet (MVP). When adding tests, use pytest:

```bash
pip install pytest
pytest
pytest --cov=. --cov-report=term-missing
```

### Recommended Test Structure

```
tests/
  test_rule_engine.py    # Unit tests for the state machine
  test_detector.py       # Detector with mock YOLO
  test_recorder.py       # Clip recording logic
  test_database.py       # CRUD operations
  test_api.py            # API endpoint tests
  conftest.py            # Shared fixtures
```

## Git Workflow

```bash
git checkout -b feature/my-feature
git add .
git commit -m "feat: add description of change"
git push origin feature/my-feature
```

### Commit Message Convention

```
type(scope): description

Types:
  feat     New feature
  fix      Bug fix
  docs     Documentation only
  style    Code style (no logic change)
  refactor Code restructuring (no feature change)
  test     Adding or updating tests
  chore    Build, CI, tooling
```

## Architecture Rules

1. **Never import heavy libraries** in `detector/types.py` — it is the shared domain types module
2. **Always use context managers** for database sessions (`session_scope()`)
3. **One component per class** — keep components isolated behind clean interfaces
4. **Configuration through settings** — never hardcode values or use `os.getenv()`
5. **Log, do not print** — every module uses `get_logger(__name__)`
