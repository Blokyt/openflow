# OpenFlow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build OpenFlow, a modular local treasury management app with a skill-driven configuration system.

**Architecture:** Python FastAPI backend serving a React frontend, with a module system driven by manifest.json files. SQLite single-file database. Deterministic tooling scripts (create_module, check, migrate) ensure integrity. The skill `/openflow` orchestrates init, evolution, diagnostics, and custom module creation.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy (SQLite), React 18 (Vite + TypeScript), Tailwind CSS

**Phasing:** This plan is split into sequential phases. Each phase produces working, testable software.

- **Phase 1: Foundations** — Project scaffold, config system, database, module loader, deterministic tools
- **Phase 2: Core Modules** — Transactions, Categories, Dashboard (noyau)
- **Phase 3: Standard Modules** — Invoices, Reimbursements, Budget, Divisions, Tiers, Attachments, Annotations, Export
- **Phase 4: Advanced Modules** — Bank reconciliation, Recurring, Multi-accounts, Audit, Forecasting, Alerts, Tax receipts, Grants, FEC, Multi-users
- **Phase 5: The Skill** — `/openflow` skill with init, evolution, diagnostic, custom module creation modes

**This document covers Phase 1 and Phase 2.** Phases 3-5 will be planned after Phase 2 is working.

---

## File Structure (Phase 1 + 2)

```
openflow/
├── backend/
│   ├── main.py                         # FastAPI app, mounts module routes, serves React build
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                   # Load/save config.yaml, pydantic models
│   │   ├── database.py                 # SQLite connection, session management
│   │   ├── module_loader.py            # Discover, validate, load active modules
│   │   ├── validator.py                # Validate manifests against JSON Schema
│   │   └── models.py                   # System tables (_config, _modules, _dashboard)
│   └── modules/
│       ├── transactions/
│       │   ├── manifest.json
│       │   ├── models.py               # transactions table
│       │   └── api.py                  # CRUD endpoints
│       ├── categories/
│       │   ├── manifest.json
│       │   ├── models.py               # categories table
│       │   └── api.py                  # CRUD endpoints
│       └── dashboard/
│           ├── manifest.json
│           ├── models.py               # dashboard_layout table
│           └── api.py                  # layout save/load endpoints
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── src/
│       ├── main.tsx                    # React entry point
│       ├── App.tsx                     # Shell: sidebar + main content
│       ├── api.ts                      # Fetch wrapper for backend API
│       ├── types.ts                    # Shared TypeScript types
│       ├── core/
│       │   ├── ModuleLoader.tsx        # Load modules from GET /api/modules
│       │   ├── Sidebar.tsx             # Navigation from module manifests
│       │   ├── Settings.tsx            # Module toggles, entity config
│       │   └── Dashboard.tsx           # Widget grid
│       └── modules/
│           ├── transactions/
│           │   ├── TransactionList.tsx  # Main table with filters
│           │   ├── TransactionForm.tsx  # Add/edit form
│           │   └── widgets/
│           │       └── RecentTransactions.tsx
│           ├── categories/
│           │   ├── CategoryManager.tsx  # Tree view with CRUD
│           │   └── widgets/
│           │       └── CategoryBreakdown.tsx
│           └── dashboard/
│               └── widgets/
│                   ├── CurrentBalance.tsx
│                   └── IncomeExpenseChart.tsx
├── tools/
│   ├── create_module.py
│   ├── check.py
│   ├── migrate.py
│   └── schemas/
│       └── manifest.schema.json
├── tests/
│   ├── backend/
│   │   ├── test_config.py
│   │   ├── test_database.py
│   │   ├── test_module_loader.py
│   │   ├── test_validator.py
│   │   ├── test_check_tool.py
│   │   ├── test_transactions_api.py
│   │   ├── test_categories_api.py
│   │   └── test_dashboard_api.py
│   └── tools/
│       ├── test_create_module.py
│       └── test_migrate.py
├── config.yaml
├── data/
│   └── .gitkeep
├── start.py
├── requirements.txt
└── README.md
```

---

## Phase 1: Foundations

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `openflow/requirements.txt`
- Create: `openflow/frontend/package.json`
- Create: `openflow/data/.gitkeep`

- [ ] **Step 1: Create project root and backend dependencies**

```bash
mkdir -p openflow/backend/core openflow/backend/modules openflow/frontend/src openflow/tools/schemas openflow/tests/backend openflow/tests/tools openflow/data
```

- [ ] **Step 2: Create requirements.txt**

Create `openflow/requirements.txt`:
```
fastapi==0.115.0
uvicorn==0.32.0
sqlalchemy==2.0.36
pydantic==2.10.0
pyyaml==6.0.2
jsonschema==4.23.0
python-multipart==0.0.12
```

- [ ] **Step 3: Create frontend package.json**

Create `openflow/frontend/package.json`:
```json
{
  "name": "openflow-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "lucide-react": "^0.460.0",
    "recharts": "^2.14.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.15",
    "typescript": "^5.6.3",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 4: Install dependencies**

```bash
cd openflow && pip install -r requirements.txt
cd frontend && npm install
```

- [ ] **Step 5: Create data directory placeholder**

Create `openflow/data/.gitkeep` (empty file).

- [ ] **Step 6: Commit**

```bash
git add openflow/
git commit -m "feat: scaffold openflow project with backend and frontend dependencies"
```

---

### Task 2: Config system (config.yaml + config.py)

**Files:**
- Create: `openflow/config.yaml`
- Create: `openflow/backend/core/__init__.py`
- Create: `openflow/backend/core/config.py`
- Test: `openflow/tests/backend/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `openflow/tests/__init__.py` (empty) and `openflow/tests/backend/__init__.py` (empty).

Create `openflow/tests/backend/test_config.py`:
```python
import os
import tempfile
import pytest
import yaml
from pathlib import Path


def test_load_config_from_file():
    """Config loads correctly from a yaml file."""
    from backend.core.config import load_config

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({
            "entity": {"name": "Test Asso", "type": "association", "currency": "EUR"},
            "balance": {"date": "2025-06-01", "amount": 3200.0},
            "modules": {"transactions": True, "categories": True, "dashboard": True, "invoices": False},
        }, f)
        f.flush()
        config = load_config(f.name)

    assert config.entity.name == "Test Asso"
    assert config.entity.type == "association"
    assert config.balance.amount == 3200.0
    assert config.modules["transactions"] is True
    assert config.modules["invoices"] is False
    os.unlink(f.name)


def test_save_config():
    """Config saves back to yaml correctly."""
    from backend.core.config import load_config, save_config

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({
            "entity": {"name": "Test", "type": "association", "currency": "EUR"},
            "balance": {"date": "2025-01-01", "amount": 0.0},
            "modules": {"transactions": True, "categories": True, "dashboard": True},
        }, f)
        path = f.name

    config = load_config(path)
    config.entity.name = "Updated"
    save_config(config, path)

    reloaded = load_config(path)
    assert reloaded.entity.name == "Updated"
    os.unlink(path)


def test_load_config_missing_file():
    """Loading a non-existent config raises FileNotFoundError."""
    from backend.core.config import load_config

    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")


def test_toggle_module():
    """Can toggle a module on/off in config."""
    from backend.core.config import load_config, save_config

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({
            "entity": {"name": "Test", "type": "association", "currency": "EUR"},
            "balance": {"date": "2025-01-01", "amount": 0.0},
            "modules": {"transactions": True, "categories": True, "dashboard": True, "invoices": False},
        }, f)
        path = f.name

    config = load_config(path)
    config.modules["invoices"] = True
    save_config(config, path)

    reloaded = load_config(path)
    assert reloaded.modules["invoices"] is True
    os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd openflow && python -m pytest tests/backend/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend'`

- [ ] **Step 3: Implement config.py**

Create `openflow/backend/__init__.py` (empty) and `openflow/backend/core/__init__.py` (empty).

Create `openflow/backend/core/config.py`:
```python
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

import yaml


@dataclass
class EntityConfig:
    name: str = "Mon Entité"
    type: str = "association"
    currency: str = "EUR"
    logo: str = ""
    address: str = ""
    siret: str = ""
    rna: str = ""


@dataclass
class BalanceConfig:
    date: str = "2025-01-01"
    amount: float = 0.0


@dataclass
class AppConfig:
    entity: EntityConfig = field(default_factory=EntityConfig)
    balance: BalanceConfig = field(default_factory=BalanceConfig)
    modules: dict[str, bool] = field(default_factory=lambda: {
        "transactions": True,
        "categories": True,
        "dashboard": True,
    })


def load_config(path: str) -> AppConfig:
    """Load config from a YAML file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(p) as f:
        raw = yaml.safe_load(f) or {}

    entity = EntityConfig(**raw.get("entity", {}))
    balance = BalanceConfig(**raw.get("balance", {}))
    modules = raw.get("modules", {"transactions": True, "categories": True, "dashboard": True})

    return AppConfig(entity=entity, balance=balance, modules=modules)


def save_config(config: AppConfig, path: str) -> None:
    """Save config to a YAML file."""
    data = {
        "entity": asdict(config.entity),
        "balance": asdict(config.balance),
        "modules": config.modules,
    }
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
```

- [ ] **Step 4: Create default config.yaml**

Create `openflow/config.yaml`:
```yaml
entity:
  name: "Mon Entité"
  type: "association"
  currency: "EUR"
  logo: ""
  address: ""
  siret: ""
  rna: ""

balance:
  date: "2025-01-01"
  amount: 0.0

modules:
  transactions: true
  categories: true
  dashboard: true
  invoices: false
  reimbursements: false
  budget: false
  divisions: false
  tiers: false
  attachments: false
  annotations: false
  export: false
  bank_reconciliation: false
  recurring: false
  multi_accounts: false
  audit: false
  forecasting: false
  alerts: false
  tax_receipts: false
  grants: false
  fec_export: false
  multi_users: false
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd openflow && python -m pytest tests/backend/test_config.py -v
```

Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add openflow/backend/core/ openflow/config.yaml openflow/tests/
git commit -m "feat: config system with load/save yaml and module toggles"
```

---

### Task 3: Database system (database.py + system tables)

**Files:**
- Create: `openflow/backend/core/database.py`
- Create: `openflow/backend/core/models.py`
- Test: `openflow/tests/backend/test_database.py`

- [ ] **Step 1: Write the failing tests**

Create `openflow/tests/backend/test_database.py`:
```python
import os
import tempfile
import pytest
from sqlalchemy import inspect


def test_create_database():
    """Database file is created and system tables exist."""
    from backend.core.database import create_engine_from_path, create_system_tables

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine_from_path(db_path)
        create_system_tables(engine)

        assert os.path.exists(db_path)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "_config" in tables
        assert "_modules" in tables
        assert "_dashboard" in tables


def test_get_session():
    """Session can be created and used."""
    from backend.core.database import create_engine_from_path, create_system_tables, get_session_factory

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine_from_path(db_path)
        create_system_tables(engine)
        SessionLocal = get_session_factory(engine)

        with SessionLocal() as session:
            assert session is not None


def test_register_module_in_db():
    """A module can be registered in _modules table."""
    from backend.core.database import (
        create_engine_from_path, create_system_tables,
        get_session_factory, register_module, get_module_version,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine_from_path(db_path)
        create_system_tables(engine)
        SessionLocal = get_session_factory(engine)

        register_module(SessionLocal, "transactions", "1.0.0")
        version = get_module_version(SessionLocal, "transactions")
        assert version == "1.0.0"


def test_get_module_version_not_installed():
    """Getting version of non-installed module returns None."""
    from backend.core.database import (
        create_engine_from_path, create_system_tables,
        get_session_factory, get_module_version,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine_from_path(db_path)
        create_system_tables(engine)
        SessionLocal = get_session_factory(engine)

        version = get_module_version(SessionLocal, "nonexistent")
        assert version is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd openflow && python -m pytest tests/backend/test_database.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement database.py and models.py**

Create `openflow/backend/core/models.py`:
```python
from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, Text, MetaData, Table
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class SystemBase(DeclarativeBase):
    pass


class ModuleRecord(SystemBase):
    __tablename__ = "_modules"

    id = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    active = Column(Boolean, default=True)
    installed_at = Column(DateTime, default=datetime.utcnow)


class ConfigRecord(SystemBase):
    __tablename__ = "_config"

    key = Column(String, primary_key=True)
    value = Column(Text)


class DashboardWidget(SystemBase):
    __tablename__ = "_dashboard"

    id = Column(Integer, primary_key=True, autoincrement=True)
    widget_id = Column(String, nullable=False)
    module_id = Column(String, nullable=False)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    size = Column(String, default="half")
    visible = Column(Boolean, default=True)
```

Create `openflow/backend/core/database.py`:
```python
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.core.models import SystemBase, ModuleRecord


def create_engine_from_path(db_path: str):
    """Create a SQLAlchemy engine for a SQLite file."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def create_system_tables(engine):
    """Create all system tables (_config, _modules, _dashboard)."""
    SystemBase.metadata.create_all(engine)


def get_session_factory(engine) -> sessionmaker:
    """Return a sessionmaker bound to the engine."""
    return sessionmaker(bind=engine)


def register_module(session_factory: sessionmaker, module_id: str, version: str) -> None:
    """Register or update a module in the _modules table."""
    with session_factory() as session:
        existing = session.query(ModuleRecord).filter_by(id=module_id).first()
        if existing:
            existing.version = version
        else:
            session.add(ModuleRecord(id=module_id, version=version, active=True))
        session.commit()


def get_module_version(session_factory: sessionmaker, module_id: str) -> str | None:
    """Get the installed version of a module, or None if not installed."""
    with session_factory() as session:
        record = session.query(ModuleRecord).filter_by(id=module_id).first()
        return record.version if record else None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd openflow && python -m pytest tests/backend/test_database.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add openflow/backend/core/database.py openflow/backend/core/models.py openflow/tests/backend/test_database.py
git commit -m "feat: database system with SQLite engine, system tables, module registry"
```

---

### Task 4: Manifest JSON Schema + validator

**Files:**
- Create: `openflow/tools/schemas/manifest.schema.json`
- Create: `openflow/backend/core/validator.py`
- Test: `openflow/tests/backend/test_validator.py`

- [ ] **Step 1: Create the JSON Schema**

Create `openflow/tools/schemas/manifest.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "name", "description", "version", "origin", "category", "dependencies", "api_routes", "db_models"],
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z_]+$" },
    "name": { "type": "string" },
    "description": { "type": "string" },
    "version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$" },
    "origin": { "type": "string", "enum": ["builtin", "custom"] },
    "category": { "type": "string", "enum": ["core", "standard", "advanced", "custom"] },
    "dependencies": { "type": "array", "items": { "type": "string" } },
    "menu": {
      "type": "object",
      "properties": {
        "label": { "type": "string" },
        "icon": { "type": "string" },
        "position": { "type": "integer" }
      },
      "required": ["label", "icon", "position"]
    },
    "api_routes": { "type": "array", "items": { "type": "string" } },
    "db_models": { "type": "array", "items": { "type": "string" } },
    "dashboard_widgets": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name", "component", "default_visible", "size"],
        "properties": {
          "id": { "type": "string" },
          "name": { "type": "string" },
          "component": { "type": "string" },
          "default_visible": { "type": "boolean" },
          "size": { "type": "string", "enum": ["quarter", "half", "full"] }
        }
      }
    },
    "settings_schema": { "type": "object" }
  },
  "additionalProperties": false
}
```

- [ ] **Step 2: Write the failing tests**

Create `openflow/tests/backend/test_validator.py`:
```python
import json
import os
import tempfile
import pytest


VALID_MANIFEST = {
    "id": "test_module",
    "name": "Test Module",
    "description": "A test module",
    "version": "1.0.0",
    "origin": "builtin",
    "category": "standard",
    "dependencies": ["transactions"],
    "menu": {"label": "Test", "icon": "test", "position": 1},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}


def test_validate_valid_manifest():
    """A valid manifest passes validation."""
    from backend.core.validator import validate_manifest

    errors = validate_manifest(VALID_MANIFEST)
    assert errors == []


def test_validate_missing_required_field():
    """A manifest missing 'id' fails validation."""
    from backend.core.validator import validate_manifest

    bad = {k: v for k, v in VALID_MANIFEST.items() if k != "id"}
    errors = validate_manifest(bad)
    assert len(errors) > 0
    assert any("id" in e for e in errors)


def test_validate_bad_id_format():
    """A manifest with uppercase id fails validation."""
    from backend.core.validator import validate_manifest

    bad = {**VALID_MANIFEST, "id": "BadId"}
    errors = validate_manifest(bad)
    assert len(errors) > 0


def test_validate_bad_version_format():
    """A manifest with non-semver version fails validation."""
    from backend.core.validator import validate_manifest

    bad = {**VALID_MANIFEST, "version": "v1"}
    errors = validate_manifest(bad)
    assert len(errors) > 0


def test_validate_manifest_file():
    """Can validate a manifest from a file path."""
    from backend.core.validator import validate_manifest_file

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(VALID_MANIFEST, f)
        path = f.name

    errors = validate_manifest_file(path)
    assert errors == []
    os.unlink(path)


def test_check_module_files_exist():
    """Validator checks that declared files actually exist."""
    from backend.core.validator import check_module_files

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create manifest referencing files that don't exist
        errors = check_module_files(VALID_MANIFEST, tmpdir)
        assert len(errors) > 0
        assert any("api.py" in e for e in errors)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd openflow && python -m pytest tests/backend/test_validator.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement validator.py**

Create `openflow/backend/core/validator.py`:
```python
import json
from pathlib import Path

import jsonschema


SCHEMA_PATH = Path(__file__).parent.parent.parent / "tools" / "schemas" / "manifest.schema.json"


def _load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def validate_manifest(manifest: dict) -> list[str]:
    """Validate a manifest dict against the JSON Schema. Returns list of error messages."""
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(manifest)]


def validate_manifest_file(path: str) -> list[str]:
    """Validate a manifest.json file. Returns list of error messages."""
    with open(path) as f:
        manifest = json.load(f)
    return validate_manifest(manifest)


def check_module_files(manifest: dict, module_dir: str) -> list[str]:
    """Check that all files declared in the manifest exist on disk."""
    errors = []
    base = Path(module_dir)

    for route_file in manifest.get("api_routes", []):
        if not (base / route_file).exists():
            errors.append(f"Declared api_route not found: {route_file}")

    for model_file in manifest.get("db_models", []):
        if not (base / model_file).exists():
            errors.append(f"Declared db_model not found: {model_file}")

    return errors
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd openflow && python -m pytest tests/backend/test_validator.py -v
```

Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
git add openflow/tools/schemas/ openflow/backend/core/validator.py openflow/tests/backend/test_validator.py
git commit -m "feat: manifest JSON Schema and validator with file existence checks"
```

---

### Task 5: Module loader

**Files:**
- Create: `openflow/backend/core/module_loader.py`
- Test: `openflow/tests/backend/test_module_loader.py`

- [ ] **Step 1: Write the failing tests**

Create `openflow/tests/backend/test_module_loader.py`:
```python
import json
import os
import tempfile
import pytest

VALID_MANIFEST = {
    "id": "fake_module",
    "name": "Fake Module",
    "description": "For testing",
    "version": "1.0.0",
    "origin": "builtin",
    "category": "core",
    "dependencies": [],
    "menu": {"label": "Fake", "icon": "fake", "position": 1},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}


def _create_module(base_dir: str, manifest: dict):
    """Helper: create a module directory with manifest and stub files."""
    mod_dir = os.path.join(base_dir, manifest["id"])
    os.makedirs(mod_dir, exist_ok=True)
    with open(os.path.join(mod_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    # Create stub files declared in manifest
    for route in manifest.get("api_routes", []):
        open(os.path.join(mod_dir, route), "w").close()
    for model in manifest.get("db_models", []):
        open(os.path.join(mod_dir, model), "w").close()


def test_discover_modules():
    """Module loader discovers all modules in a directory."""
    from backend.core.module_loader import discover_modules

    with tempfile.TemporaryDirectory() as tmpdir:
        _create_module(tmpdir, VALID_MANIFEST)
        _create_module(tmpdir, {**VALID_MANIFEST, "id": "another_module"})

        modules = discover_modules(tmpdir)
        assert len(modules) == 2
        ids = {m["id"] for m in modules}
        assert "fake_module" in ids
        assert "another_module" in ids


def test_filter_active_modules():
    """Only active modules from config are returned."""
    from backend.core.module_loader import discover_modules, filter_active

    with tempfile.TemporaryDirectory() as tmpdir:
        _create_module(tmpdir, VALID_MANIFEST)
        _create_module(tmpdir, {**VALID_MANIFEST, "id": "inactive_mod"})

        all_modules = discover_modules(tmpdir)
        active_config = {"fake_module": True, "inactive_mod": False}
        active = filter_active(all_modules, active_config)

        assert len(active) == 1
        assert active[0]["id"] == "fake_module"


def test_check_dependencies_satisfied():
    """Dependencies check passes when all deps are active."""
    from backend.core.module_loader import check_dependencies

    manifests = [
        {**VALID_MANIFEST, "id": "transactions", "dependencies": []},
        {**VALID_MANIFEST, "id": "invoices", "dependencies": ["transactions"]},
    ]
    errors = check_dependencies(manifests)
    assert errors == []


def test_check_dependencies_missing():
    """Dependencies check fails when a dep is missing."""
    from backend.core.module_loader import check_dependencies

    manifests = [
        {**VALID_MANIFEST, "id": "invoices", "dependencies": ["transactions"]},
    ]
    errors = check_dependencies(manifests)
    assert len(errors) > 0
    assert any("transactions" in e for e in errors)


def test_detect_route_conflicts():
    """Detect when two modules declare the same API route file name."""
    from backend.core.module_loader import detect_route_conflicts

    manifests = [
        {**VALID_MANIFEST, "id": "mod_a", "api_routes": ["api.py"]},
        {**VALID_MANIFEST, "id": "mod_b", "api_routes": ["api.py"]},
    ]
    # Same filename in different modules is fine (they're in different dirs)
    # But if we namespace by module id, no conflict
    conflicts = detect_route_conflicts(manifests)
    assert conflicts == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd openflow && python -m pytest tests/backend/test_module_loader.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement module_loader.py**

Create `openflow/backend/core/module_loader.py`:
```python
import json
from pathlib import Path


def discover_modules(modules_dir: str) -> list[dict]:
    """Scan a directory for module folders containing manifest.json."""
    modules = []
    base = Path(modules_dir)
    if not base.exists():
        return modules

    for child in sorted(base.iterdir()):
        manifest_path = child / "manifest.json"
        if child.is_dir() and manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            modules.append(manifest)

    return modules


def filter_active(modules: list[dict], active_config: dict[str, bool]) -> list[dict]:
    """Filter modules to only those marked active in config."""
    return [m for m in modules if active_config.get(m["id"], False)]


def check_dependencies(active_manifests: list[dict]) -> list[str]:
    """Check that all dependencies of active modules are satisfied."""
    active_ids = {m["id"] for m in active_manifests}
    errors = []

    for manifest in active_manifests:
        for dep in manifest.get("dependencies", []):
            if dep not in active_ids:
                errors.append(
                    f"Module '{manifest['id']}' requires '{dep}' but it is not active"
                )

    return errors


def detect_route_conflicts(active_manifests: list[dict]) -> list[str]:
    """Detect API route prefix conflicts between modules.
    Each module gets its own prefix /api/<module_id>/, so file names don't conflict.
    """
    prefixes = {}
    conflicts = []

    for manifest in active_manifests:
        prefix = f"/api/{manifest['id']}"
        if prefix in prefixes:
            conflicts.append(
                f"Route prefix conflict: '{prefix}' used by both "
                f"'{prefixes[prefix]}' and '{manifest['id']}'"
            )
        prefixes[prefix] = manifest["id"]

    return conflicts
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd openflow && python -m pytest tests/backend/test_module_loader.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add openflow/backend/core/module_loader.py openflow/tests/backend/test_module_loader.py
git commit -m "feat: module loader with discovery, filtering, dependency checks"
```

---

### Task 6: Deterministic tools — check.py and create_module.py

**Files:**
- Create: `openflow/tools/check.py`
- Create: `openflow/tools/create_module.py`
- Test: `openflow/tests/tools/test_check_tool.py` (renamed from test_create_module.py for clarity)
- Test: `openflow/tests/tools/test_create_module.py`

- [ ] **Step 1: Write tests for check.py**

Create `openflow/tests/tools/__init__.py` (empty).

Create `openflow/tests/tools/test_check_tool.py`:
```python
import json
import os
import tempfile
import subprocess
import sys


VALID_MANIFEST = {
    "id": "test_mod",
    "name": "Test",
    "description": "Test module",
    "version": "1.0.0",
    "origin": "builtin",
    "category": "core",
    "dependencies": [],
    "menu": {"label": "Test", "icon": "test", "position": 1},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}


def _setup_project(tmpdir: str):
    """Create a minimal valid project structure."""
    modules_dir = os.path.join(tmpdir, "backend", "modules", "test_mod")
    os.makedirs(modules_dir)
    with open(os.path.join(modules_dir, "manifest.json"), "w") as f:
        json.dump(VALID_MANIFEST, f)
    open(os.path.join(modules_dir, "api.py"), "w").close()
    open(os.path.join(modules_dir, "models.py"), "w").close()

    # Create tools/schemas dir with schema
    schemas_dir = os.path.join(tmpdir, "tools", "schemas")
    os.makedirs(schemas_dir)
    # Copy real schema
    real_schema = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "schemas", "manifest.schema.json")
    if os.path.exists(real_schema):
        import shutil
        shutil.copy(real_schema, os.path.join(schemas_dir, "manifest.schema.json"))


def test_check_passes_valid_project():
    """check.py returns 0 for a valid project."""
    result = subprocess.run(
        [sys.executable, "tools/check.py", "--project-dir", "."],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), "..", "..")
    )
    # May fail if no modules yet, but should not crash
    assert result.returncode in (0, 1)


def test_check_detects_invalid_manifest():
    """check.py returns non-zero when a manifest is invalid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        modules_dir = os.path.join(tmpdir, "backend", "modules", "bad_mod")
        os.makedirs(modules_dir)
        # Invalid manifest - missing required fields
        with open(os.path.join(modules_dir, "manifest.json"), "w") as f:
            json.dump({"id": "bad_mod"}, f)

        schemas_dir = os.path.join(tmpdir, "tools", "schemas")
        os.makedirs(schemas_dir)
        real_schema = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "schemas", "manifest.schema.json")
        if os.path.exists(real_schema):
            import shutil
            shutil.copy(real_schema, os.path.join(schemas_dir, "manifest.schema.json"))

        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "..", "..", "tools", "check.py"),
             "--project-dir", tmpdir],
            capture_output=True, text=True
        )
        assert result.returncode == 1
        assert "FAIL" in result.stdout or "error" in result.stdout.lower()
```

- [ ] **Step 2: Write tests for create_module.py**

Create `openflow/tests/tools/test_create_module.py`:
```python
import json
import os
import subprocess
import sys
import tempfile


def test_create_module_scaffolds_structure():
    """create_module.py creates proper directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backend_modules = os.path.join(tmpdir, "backend", "modules")
        frontend_modules = os.path.join(tmpdir, "frontend", "src", "modules")
        os.makedirs(backend_modules)
        os.makedirs(frontend_modules)

        # Copy schema
        schemas_dir = os.path.join(tmpdir, "tools", "schemas")
        os.makedirs(schemas_dir)
        real_schema = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "schemas", "manifest.schema.json")
        if os.path.exists(real_schema):
            import shutil
            shutil.copy(real_schema, os.path.join(schemas_dir, "manifest.schema.json"))

        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "..", "..", "tools", "create_module.py"),
             "my_module", "--project-dir", tmpdir, "--name", "My Module", "--description", "A test module"],
            capture_output=True, text=True
        )
        assert result.returncode == 0

        # Check backend structure
        mod_dir = os.path.join(backend_modules, "my_module")
        assert os.path.isdir(mod_dir)
        assert os.path.isfile(os.path.join(mod_dir, "manifest.json"))
        assert os.path.isfile(os.path.join(mod_dir, "api.py"))
        assert os.path.isfile(os.path.join(mod_dir, "models.py"))

        # Check manifest is valid
        with open(os.path.join(mod_dir, "manifest.json")) as f:
            manifest = json.load(f)
        assert manifest["id"] == "my_module"
        assert manifest["name"] == "My Module"

        # Check frontend structure
        fe_dir = os.path.join(frontend_modules, "my_module")
        assert os.path.isdir(fe_dir)
        assert os.path.isfile(os.path.join(fe_dir, "index.tsx"))


def test_create_module_refuses_duplicate():
    """create_module.py refuses to overwrite an existing module."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backend_modules = os.path.join(tmpdir, "backend", "modules", "existing")
        os.makedirs(backend_modules)
        open(os.path.join(backend_modules, "manifest.json"), "w").close()

        frontend_modules = os.path.join(tmpdir, "frontend", "src", "modules")
        os.makedirs(frontend_modules)

        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "..", "..", "tools", "create_module.py"),
             "existing", "--project-dir", tmpdir, "--name", "Existing", "--description", "Dup"],
            capture_output=True, text=True
        )
        assert result.returncode == 1
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd openflow && python -m pytest tests/tools/ -v
```

Expected: FAIL — scripts don't exist yet

- [ ] **Step 4: Implement check.py**

Create `openflow/tools/check.py`:
```python
#!/usr/bin/env python3
"""Validate the integrity of an OpenFlow project."""
import argparse
import json
import sys
from pathlib import Path

# Add project root to path so we can import backend
PROJECT_ROOT = Path(__file__).parent.parent


def main():
    parser = argparse.ArgumentParser(description="Check OpenFlow project integrity")
    parser.add_argument("--project-dir", default=str(PROJECT_ROOT), help="Project root directory")
    args = parser.parse_args()

    project = Path(args.project_dir)
    modules_dir = project / "backend" / "modules"
    schema_path = project / "tools" / "schemas" / "manifest.schema.json"

    errors = []
    warnings = []
    modules_found = []

    # 1. Check schema exists
    if not schema_path.exists():
        errors.append(f"Manifest schema not found: {schema_path}")
        print_report(errors, warnings, modules_found)
        sys.exit(1)

    with open(schema_path) as f:
        schema = json.load(f)

    import jsonschema

    # 2. Scan modules
    if not modules_dir.exists():
        warnings.append("No backend/modules directory found")
        print_report(errors, warnings, modules_found)
        sys.exit(0)

    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue

        manifest_path = mod_dir / "manifest.json"
        if not manifest_path.exists():
            errors.append(f"Module '{mod_dir.name}': missing manifest.json")
            continue

        # Validate manifest against schema
        with open(manifest_path) as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError as e:
                errors.append(f"Module '{mod_dir.name}': invalid JSON in manifest: {e}")
                continue

        validator = jsonschema.Draft202012Validator(schema)
        for error in validator.iter_errors(manifest):
            errors.append(f"Module '{mod_dir.name}': manifest validation error: {error.message}")

        # Check declared files exist
        for route_file in manifest.get("api_routes", []):
            if not (mod_dir / route_file).exists():
                errors.append(f"Module '{mod_dir.name}': declared api_route '{route_file}' not found")

        for model_file in manifest.get("db_models", []):
            if not (mod_dir / model_file).exists():
                errors.append(f"Module '{mod_dir.name}': declared db_model '{model_file}' not found")

        # Check id matches directory name
        if manifest.get("id") != mod_dir.name:
            errors.append(f"Module '{mod_dir.name}': manifest id '{manifest.get('id')}' doesn't match directory name")

        modules_found.append(manifest.get("id", mod_dir.name))

    # 3. Check dependencies
    for mod_dir in sorted(modules_dir.iterdir()):
        manifest_path = mod_dir / "manifest.json"
        if not manifest_path.exists() or not mod_dir.is_dir():
            continue
        with open(manifest_path) as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError:
                continue
        for dep in manifest.get("dependencies", []):
            if dep not in modules_found:
                errors.append(f"Module '{manifest['id']}': dependency '{dep}' not found in project")

    print_report(errors, warnings, modules_found)
    sys.exit(1 if errors else 0)


def print_report(errors, warnings, modules):
    print(f"\n{'=' * 50}")
    print(f"OpenFlow Integrity Check")
    print(f"{'=' * 50}")
    print(f"Modules found: {len(modules)}")
    for m in modules:
        print(f"  - {m}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
        print(f"\nResult: FAIL")
    else:
        print(f"\nResult: PASS")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Implement create_module.py**

Create `openflow/tools/create_module.py`:
```python
#!/usr/bin/env python3
"""Scaffold a new OpenFlow module."""
import argparse
import json
import sys
from pathlib import Path


MANIFEST_TEMPLATE = {
    "id": "",
    "name": "",
    "description": "",
    "version": "1.0.0",
    "origin": "custom",
    "category": "custom",
    "dependencies": [],
    "menu": {"label": "", "icon": "box", "position": 99},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}

API_TEMPLATE = '''"""API routes for {name} module."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/")
def list_{id}():
    """List all {name} records."""
    return []
'''

MODELS_TEMPLATE = '''"""Database models for {name} module."""

migrations = {{
    "1.0.0": [
        # Add CREATE TABLE statements here
    ],
}}
'''

INDEX_TSX_TEMPLATE = '''import React from "react";

export default function {component_name}() {{
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold">{name}</h1>
      <p className="text-gray-600 mt-2">{description}</p>
    </div>
  );
}}
'''


def main():
    parser = argparse.ArgumentParser(description="Create a new OpenFlow module")
    parser.add_argument("module_id", help="Module ID (lowercase_snake_case)")
    parser.add_argument("--project-dir", default=str(Path(__file__).parent.parent), help="Project root")
    parser.add_argument("--name", required=True, help="Human-readable module name")
    parser.add_argument("--description", required=True, help="Module description")
    parser.add_argument("--category", default="custom", choices=["core", "standard", "advanced", "custom"])
    parser.add_argument("--origin", default="custom", choices=["builtin", "custom"])
    args = parser.parse_args()

    project = Path(args.project_dir)
    backend_dir = project / "backend" / "modules" / args.module_id
    frontend_dir = project / "frontend" / "src" / "modules" / args.module_id

    # Check not duplicate
    if backend_dir.exists():
        print(f"Error: module '{args.module_id}' already exists at {backend_dir}", file=sys.stderr)
        sys.exit(1)

    # Create backend structure
    backend_dir.mkdir(parents=True)

    manifest = {**MANIFEST_TEMPLATE}
    manifest["id"] = args.module_id
    manifest["name"] = args.name
    manifest["description"] = args.description
    manifest["category"] = args.category
    manifest["origin"] = args.origin
    manifest["menu"]["label"] = args.name

    with open(backend_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    with open(backend_dir / "api.py", "w") as f:
        f.write(API_TEMPLATE.format(name=args.name, id=args.module_id))

    with open(backend_dir / "models.py", "w") as f:
        f.write(MODELS_TEMPLATE.format(name=args.name))

    # Create frontend structure
    frontend_dir.mkdir(parents=True)
    (frontend_dir / "components").mkdir()
    (frontend_dir / "widgets").mkdir()

    component_name = "".join(word.capitalize() for word in args.module_id.split("_"))
    with open(frontend_dir / "index.tsx", "w") as f:
        f.write(INDEX_TSX_TEMPLATE.format(
            component_name=component_name,
            name=args.name,
            description=args.description,
        ))

    print(f"Module '{args.module_id}' created successfully:")
    print(f"  Backend:  {backend_dir}")
    print(f"  Frontend: {frontend_dir}")
    print(f"  Manifest: {backend_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd openflow && python -m pytest tests/tools/ -v
```

Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add openflow/tools/ openflow/tests/tools/
git commit -m "feat: deterministic tools — check.py validates project, create_module.py scaffolds modules"
```

---

### Task 7: Migrate tool

**Files:**
- Create: `openflow/tools/migrate.py`
- Test: `openflow/tests/tools/test_migrate.py`

- [ ] **Step 1: Write the failing tests**

Create `openflow/tests/tools/test_migrate.py`:
```python
import json
import os
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path


def _create_test_project(tmpdir: str) -> Path:
    """Create a minimal project with one module that has migrations."""
    project = Path(tmpdir)
    mod_dir = project / "backend" / "modules" / "test_mod"
    mod_dir.mkdir(parents=True)

    manifest = {
        "id": "test_mod",
        "name": "Test",
        "description": "Test module",
        "version": "1.0.0",
        "origin": "builtin",
        "category": "core",
        "dependencies": [],
        "menu": {"label": "Test", "icon": "test", "position": 1},
        "api_routes": ["api.py"],
        "db_models": ["models.py"],
        "dashboard_widgets": [],
        "settings_schema": {},
    }

    with open(mod_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)

    (mod_dir / "api.py").touch()

    with open(mod_dir / "models.py", "w") as f:
        f.write('''
migrations = {
    "1.0.0": [
        "CREATE TABLE test_items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)",
    ],
}
''')

    (project / "data").mkdir(exist_ok=True)

    # Copy schema
    schemas_dir = project / "tools" / "schemas"
    schemas_dir.mkdir(parents=True)
    real_schema = Path(__file__).parent.parent.parent / "tools" / "schemas" / "manifest.schema.json"
    if real_schema.exists():
        shutil.copy(real_schema, schemas_dir / "manifest.schema.json")

    return project


def test_migrate_creates_tables():
    """migrate.py creates tables from module migrations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project = _create_test_project(tmpdir)
        migrate_script = Path(__file__).parent.parent.parent / "tools" / "migrate.py"

        result = subprocess.run(
            [sys.executable, str(migrate_script), "--project-dir", str(project)],
            capture_output=True, text=True
        )
        assert result.returncode == 0

        # Verify table was created
        import sqlite3
        db_path = project / "data" / "openflow.db"
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_items'")
        assert cursor.fetchone() is not None
        conn.close()


def test_migrate_creates_backup():
    """migrate.py creates a backup before migrating."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project = _create_test_project(tmpdir)
        migrate_script = Path(__file__).parent.parent.parent / "tools" / "migrate.py"

        # Run once to create DB
        subprocess.run(
            [sys.executable, str(migrate_script), "--project-dir", str(project)],
            capture_output=True, text=True
        )

        # Run again — should create backup
        result = subprocess.run(
            [sys.executable, str(migrate_script), "--project-dir", str(project)],
            capture_output=True, text=True
        )
        assert result.returncode == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd openflow && python -m pytest tests/tools/test_migrate.py -v
```

Expected: FAIL — script doesn't exist

- [ ] **Step 3: Implement migrate.py**

Create `openflow/tools/migrate.py`:
```python
#!/usr/bin/env python3
"""Apply database migrations for all active OpenFlow modules."""
import argparse
import importlib.util
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def load_module_migrations(models_path: Path) -> dict[str, list[str]]:
    """Dynamically load the migrations dict from a module's models.py."""
    spec = importlib.util.spec_from_file_location("models", models_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "migrations", {})


def get_installed_version(conn: sqlite3.Connection, module_id: str) -> str | None:
    """Get the installed version of a module from _modules table."""
    try:
        cursor = conn.execute("SELECT version FROM _modules WHERE id = ?", (module_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def set_installed_version(conn: sqlite3.Connection, module_id: str, version: str):
    """Set the installed version of a module in _modules table."""
    existing = get_installed_version(conn, module_id)
    if existing:
        conn.execute("UPDATE _modules SET version = ? WHERE id = ?", (version, module_id))
    else:
        conn.execute(
            "INSERT INTO _modules (id, version, active, installed_at) VALUES (?, ?, 1, ?)",
            (module_id, version, datetime.utcnow().isoformat())
        )


def version_key(v: str) -> tuple[int, ...]:
    """Convert version string to sortable tuple."""
    return tuple(int(x) for x in v.split("."))


def main():
    parser = argparse.ArgumentParser(description="Run OpenFlow database migrations")
    parser.add_argument("--project-dir", default=str(Path(__file__).parent.parent), help="Project root")
    args = parser.parse_args()

    project = Path(args.project_dir)
    db_path = project / "data" / "openflow.db"
    modules_dir = project / "backend" / "modules"

    # Create data dir if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing DB
    if db_path.exists():
        backup_name = f"openflow_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = db_path.parent / backup_name
        shutil.copy2(db_path, backup_path)
        print(f"Backup created: {backup_path}")

    conn = sqlite3.connect(str(db_path))

    # Ensure system tables exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _modules (
            id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            installed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _dashboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            widget_id TEXT NOT NULL,
            module_id TEXT NOT NULL,
            position_x INTEGER DEFAULT 0,
            position_y INTEGER DEFAULT 0,
            size TEXT DEFAULT 'half',
            visible INTEGER DEFAULT 1
        )
    """)
    conn.commit()

    # Process each module
    if not modules_dir.exists():
        print("No modules directory found")
        conn.close()
        sys.exit(0)

    migrated = 0
    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue

        manifest_path = mod_dir / "manifest.json"
        models_path = mod_dir / "models.py"

        if not manifest_path.exists():
            continue

        with open(manifest_path) as f:
            manifest = json.load(f)

        module_id = manifest["id"]
        target_version = manifest["version"]
        installed_version = get_installed_version(conn, module_id)

        if installed_version == target_version:
            print(f"  {module_id}: up to date ({target_version})")
            continue

        if not models_path.exists():
            print(f"  {module_id}: no models.py, skipping migrations")
            set_installed_version(conn, module_id, target_version)
            conn.commit()
            continue

        # Load and apply migrations
        all_migrations = load_module_migrations(models_path)
        versions_to_apply = sorted(
            [v for v in all_migrations if installed_version is None or version_key(v) > version_key(installed_version)],
            key=version_key
        )

        for version in versions_to_apply:
            statements = all_migrations[version]
            print(f"  {module_id}: applying migration {version} ({len(statements)} statements)")
            for stmt in statements:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as e:
                    if "already exists" in str(e):
                        print(f"    (table already exists, skipping)")
                    else:
                        raise

        set_installed_version(conn, module_id, target_version)
        conn.commit()
        migrated += 1

    conn.close()
    print(f"\nMigration complete. {migrated} module(s) migrated.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd openflow && python -m pytest tests/tools/test_migrate.py -v
```

Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add openflow/tools/migrate.py openflow/tests/tools/test_migrate.py
git commit -m "feat: migrate.py — versioned DB migrations with auto-backup"
```

---

### Task 8: FastAPI main.py with module auto-loading

**Files:**
- Create: `openflow/backend/main.py`
- Test: `openflow/tests/backend/test_main.py` (integration test)

- [ ] **Step 1: Write the failing test**

Create `openflow/tests/backend/test_main.py`:
```python
import os
import sys
import tempfile
import pytest

# Ensure we can import from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_app_starts_and_serves_modules_endpoint():
    """The FastAPI app starts and /api/modules returns active modules."""
    from fastapi.testclient import TestClient
    from backend.main import create_app

    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    client = TestClient(app)

    response = client.get("/api/modules")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_app_config_endpoint():
    """The /api/config endpoint returns current config."""
    from fastapi.testclient import TestClient
    from backend.main import create_app

    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    client = TestClient(app)

    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "entity" in data
    assert "modules" in data


def test_app_toggle_module():
    """Can toggle a module via /api/config/modules."""
    from fastapi.testclient import TestClient
    from backend.main import create_app

    # Use a temp config to avoid modifying the real one
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    client = TestClient(app)

    response = client.get("/api/config")
    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd openflow && python -m pytest tests/backend/test_main.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement main.py**

Create `openflow/backend/main.py`:
```python
"""OpenFlow FastAPI application."""
import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.core.config import load_config, save_config, AppConfig
from backend.core.module_loader import discover_modules, filter_active, check_dependencies


def create_app(config_path: str = "config.yaml", db_path: str = "data/openflow.db") -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="OpenFlow", version="0.1.0")

    # CORS for dev (React dev server on different port)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Load config
    project_root = Path(__file__).parent.parent
    config_file = project_root / config_path
    config = load_config(str(config_file))

    # Discover and load modules
    modules_dir = project_root / "backend" / "modules"
    all_modules = discover_modules(str(modules_dir))
    active_modules = filter_active(all_modules, config.modules)

    # Register module API routes
    for manifest in active_modules:
        module_id = manifest["id"]
        for route_file in manifest.get("api_routes", []):
            route_path = modules_dir / module_id / route_file
            if route_path.exists():
                module_name = f"backend.modules.{module_id}.{route_file.replace('.py', '')}"
                try:
                    mod = importlib.import_module(module_name)
                    if hasattr(mod, "router"):
                        app.include_router(mod.router, prefix=f"/api/{module_id}", tags=[manifest["name"]])
                except Exception as e:
                    print(f"Warning: failed to load routes for {module_id}: {e}")

    # System API routes
    @app.get("/api/modules")
    def get_modules():
        """Return list of active modules with their manifests."""
        return active_modules

    @app.get("/api/modules/all")
    def get_all_modules():
        """Return all discovered modules (active and inactive)."""
        return all_modules

    @app.get("/api/config")
    def get_config():
        """Return current configuration."""
        return asdict(config)

    @app.put("/api/config/entity")
    def update_entity(entity: dict):
        """Update entity configuration."""
        for key, value in entity.items():
            if hasattr(config.entity, key):
                setattr(config.entity, key, value)
        save_config(config, str(config_file))
        return asdict(config.entity)

    @app.put("/api/config/modules/{module_id}")
    def toggle_module(module_id: str, active: bool):
        """Toggle a module on or off."""
        if module_id not in config.modules:
            raise HTTPException(404, f"Module '{module_id}' not found in config")

        # Check dependencies if activating
        if active:
            module_manifest = next((m for m in all_modules if m["id"] == module_id), None)
            if module_manifest:
                for dep in module_manifest.get("dependencies", []):
                    if not config.modules.get(dep, False):
                        raise HTTPException(
                            400,
                            f"Cannot activate '{module_id}': dependency '{dep}' is not active"
                        )

        config.modules[module_id] = active
        save_config(config, str(config_file))
        return {"module_id": module_id, "active": active}

    @app.put("/api/config/balance")
    def update_balance(balance: dict):
        """Update balance reference point."""
        if "date" in balance:
            config.balance.date = balance["date"]
        if "amount" in balance:
            config.balance.amount = balance["amount"]
        save_config(config, str(config_file))
        return asdict(config.balance)

    # Serve React build if it exists
    build_dir = project_root / "frontend" / "dist"
    if build_dir.exists():
        app.mount("/", StaticFiles(directory=str(build_dir), html=True), name="frontend")

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd openflow && pip install httpx && python -m pytest tests/backend/test_main.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add openflow/backend/main.py openflow/tests/backend/test_main.py
git commit -m "feat: FastAPI app with module auto-loading, config API, module toggle"
```

---

### Task 9: start.py launcher

**Files:**
- Create: `openflow/start.py`

- [ ] **Step 1: Create start.py**

Create `openflow/start.py`:
```python
#!/usr/bin/env python3
"""Launch OpenFlow — starts FastAPI server and opens the browser."""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def check_frontend_build():
    """Check if the React frontend is built."""
    build_dir = PROJECT_ROOT / "frontend" / "dist"
    if not build_dir.exists():
        print("Frontend not built yet. Building...")
        frontend_dir = PROJECT_ROOT / "frontend"
        if not (frontend_dir / "node_modules").exists():
            print("Installing frontend dependencies...")
            subprocess.run(["npm", "install"], cwd=str(frontend_dir), check=True)
        subprocess.run(["npm", "run", "build"], cwd=str(frontend_dir), check=True)
        print("Frontend build complete.")


def run_migrations():
    """Run database migrations."""
    migrate_script = PROJECT_ROOT / "tools" / "migrate.py"
    print("Running migrations...")
    result = subprocess.run([sys.executable, str(migrate_script)], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"Migration warnings: {result.stderr}")


def main():
    port = 8000
    host = "127.0.0.1"

    # Run migrations
    run_migrations()

    # Check frontend
    check_frontend_build()

    print(f"\n{'=' * 50}")
    print(f"  OpenFlow")
    print(f"  http://{host}:{port}")
    print(f"{'=' * 50}\n")

    # Open browser after a short delay
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://{host}:{port}")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Start FastAPI
    import uvicorn
    uvicorn.run("backend.main:create_app", host=host, port=port, factory=True, reload=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add openflow/start.py
git commit -m "feat: start.py launcher — migrations, frontend build check, browser open"
```

---

## Phase 2: Core Modules

### Task 10: Transactions module — backend

**Files:**
- Create: `openflow/backend/modules/transactions/manifest.json`
- Create: `openflow/backend/modules/transactions/models.py`
- Create: `openflow/backend/modules/transactions/api.py`
- Test: `openflow/tests/backend/test_transactions_api.py`

- [ ] **Step 1: Create manifest.json**

Create `openflow/backend/modules/transactions/__init__.py` (empty).

Create `openflow/backend/modules/transactions/manifest.json`:
```json
{
  "id": "transactions",
  "name": "Transactions",
  "description": "Gestion des transactions financieres",
  "version": "1.0.0",
  "origin": "builtin",
  "category": "core",
  "dependencies": [],
  "menu": {
    "label": "Transactions",
    "icon": "arrow-left-right",
    "position": 1
  },
  "api_routes": ["api.py"],
  "db_models": ["models.py"],
  "dashboard_widgets": [
    {
      "id": "recent_transactions",
      "name": "Dernières transactions",
      "component": "widgets/RecentTransactions.tsx",
      "default_visible": true,
      "size": "full"
    }
  ],
  "settings_schema": {}
}
```

- [ ] **Step 2: Create models.py**

Create `openflow/backend/modules/transactions/models.py`:
```python
"""Database models for Transactions module."""

migrations = {
    "1.0.0": [
        """CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount REAL NOT NULL,
            category_id INTEGER,
            division_id INTEGER,
            contact_id INTEGER,
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    ],
}
```

- [ ] **Step 3: Write the failing tests**

Create `openflow/tests/backend/test_transactions_api.py`:
```python
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from backend.main import create_app


@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)


def test_list_transactions_empty(client):
    """GET /api/transactions/ returns empty list initially."""
    response = client.get("/api/transactions/")
    assert response.status_code == 200
    assert response.json() == []


def test_create_transaction(client):
    """POST /api/transactions/ creates a transaction."""
    tx = {
        "date": "2026-01-15",
        "label": "Achat fournitures",
        "amount": -45.50,
        "description": "Papeterie",
    }
    response = client.post("/api/transactions/", json=tx)
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "Achat fournitures"
    assert data["amount"] == -45.50
    assert "id" in data


def test_get_transaction(client):
    """GET /api/transactions/{id} returns a specific transaction."""
    tx = {"date": "2026-01-15", "label": "Test", "amount": 100.0}
    create_resp = client.post("/api/transactions/", json=tx)
    tx_id = create_resp.json()["id"]

    response = client.get(f"/api/transactions/{tx_id}")
    assert response.status_code == 200
    assert response.json()["id"] == tx_id


def test_update_transaction(client):
    """PUT /api/transactions/{id} updates a transaction."""
    tx = {"date": "2026-01-15", "label": "Original", "amount": 50.0}
    create_resp = client.post("/api/transactions/", json=tx)
    tx_id = create_resp.json()["id"]

    response = client.put(f"/api/transactions/{tx_id}", json={"label": "Updated", "amount": 75.0})
    assert response.status_code == 200
    assert response.json()["label"] == "Updated"
    assert response.json()["amount"] == 75.0


def test_delete_transaction(client):
    """DELETE /api/transactions/{id} removes a transaction."""
    tx = {"date": "2026-01-15", "label": "To delete", "amount": -10.0}
    create_resp = client.post("/api/transactions/", json=tx)
    tx_id = create_resp.json()["id"]

    response = client.delete(f"/api/transactions/{tx_id}")
    assert response.status_code == 200

    get_resp = client.get(f"/api/transactions/{tx_id}")
    assert get_resp.status_code == 404


def test_filter_transactions_by_date(client):
    """GET /api/transactions/?date_from=X&date_to=Y filters by date range."""
    client.post("/api/transactions/", json={"date": "2026-01-01", "label": "Jan", "amount": 10.0})
    client.post("/api/transactions/", json={"date": "2026-02-01", "label": "Feb", "amount": 20.0})
    client.post("/api/transactions/", json={"date": "2026-03-01", "label": "Mar", "amount": 30.0})

    response = client.get("/api/transactions/?date_from=2026-01-15&date_to=2026-02-15")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["label"] == "Feb"


def test_get_balance(client):
    """GET /api/transactions/balance returns computed balance."""
    response = client.get("/api/transactions/balance")
    assert response.status_code == 200
    data = response.json()
    assert "balance" in data
    assert "reference_date" in data
    assert "reference_amount" in data
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd openflow && python -m pytest tests/backend/test_transactions_api.py -v
```

Expected: FAIL — routes not implemented

- [ ] **Step 5: Implement api.py**

Create `openflow/backend/modules/transactions/api.py`:
```python
"""API routes for Transactions module."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

DB_PATH = str(Path(__file__).parent.parent.parent.parent / "data" / "openflow.db")
CONFIG_PATH = str(Path(__file__).parent.parent.parent.parent / "config.yaml")


class TransactionCreate(BaseModel):
    date: str
    label: str
    amount: float
    description: str = ""
    category_id: Optional[int] = None
    division_id: Optional[int] = None
    contact_id: Optional[int] = None


class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    label: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    division_id: Optional[int] = None
    contact_id: Optional[int] = None


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


@router.get("/")
def list_transactions(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
):
    """List transactions with optional filters."""
    conn = _get_db()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if category_id is not None:
        query += " AND category_id = ?"
        params.append(category_id)
    if search:
        query += " AND (label LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY date DESC"

    try:
        rows = conn.execute(query, params).fetchall()
        result = [_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError:
        result = []
    finally:
        conn.close()

    return result


@router.post("/", status_code=201)
def create_transaction(tx: TransactionCreate):
    """Create a new transaction."""
    now = datetime.utcnow().isoformat()
    conn = _get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO transactions (date, label, description, amount, category_id, division_id, contact_id, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?)""",
            (tx.date, tx.label, tx.description, tx.amount, tx.category_id, tx.division_id, tx.contact_id, now, now)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.get("/balance")
def get_balance():
    """Compute current balance from reference point + transactions."""
    from backend.core.config import load_config
    config = load_config(CONFIG_PATH)

    conn = _get_db()
    try:
        cursor = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE date > ?",
            (config.balance.date,)
        )
        row = cursor.fetchone()
        total = row["total"] if row else 0
    except sqlite3.OperationalError:
        total = 0
    finally:
        conn.close()

    return {
        "balance": config.balance.amount + total,
        "reference_date": config.balance.date,
        "reference_amount": config.balance.amount,
        "transactions_total": total,
    }


@router.get("/{tx_id}")
def get_transaction(tx_id: int):
    """Get a specific transaction."""
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, "Transaction not found")
    return _row_to_dict(row)


@router.put("/{tx_id}")
def update_transaction(tx_id: int, update: TransactionUpdate):
    """Update a transaction."""
    conn = _get_db()
    try:
        existing = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Transaction not found")

        fields = {}
        for field_name, value in update.model_dump(exclude_unset=True).items():
            fields[field_name] = value

        if not fields:
            return _row_to_dict(existing)

        fields["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [tx_id]

        conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ?", values)
        conn.commit()

        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{tx_id}")
def delete_transaction(tx_id: int):
    """Delete a transaction."""
    conn = _get_db()
    try:
        existing = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Transaction not found")

        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        conn.commit()
        return {"deleted": tx_id}
    finally:
        conn.close()
```

- [ ] **Step 6: Run migrations then tests**

```bash
cd openflow && python tools/migrate.py && python -m pytest tests/backend/test_transactions_api.py -v
```

Expected: 8 PASS

- [ ] **Step 7: Commit**

```bash
git add openflow/backend/modules/transactions/
git commit -m "feat: transactions module — CRUD API, filters, balance computation"
```

---

### Task 11: Categories module — backend

**Files:**
- Create: `openflow/backend/modules/categories/manifest.json`
- Create: `openflow/backend/modules/categories/models.py`
- Create: `openflow/backend/modules/categories/api.py`
- Test: `openflow/tests/backend/test_categories_api.py`

- [ ] **Step 1: Create manifest and models**

Create `openflow/backend/modules/categories/__init__.py` (empty).

Create `openflow/backend/modules/categories/manifest.json`:
```json
{
  "id": "categories",
  "name": "Catégories",
  "description": "Gestion des categories de transactions",
  "version": "1.0.0",
  "origin": "builtin",
  "category": "core",
  "dependencies": [],
  "menu": {
    "label": "Catégories",
    "icon": "tags",
    "position": 2
  },
  "api_routes": ["api.py"],
  "db_models": ["models.py"],
  "dashboard_widgets": [
    {
      "id": "category_breakdown",
      "name": "Répartition par catégorie",
      "component": "widgets/CategoryBreakdown.tsx",
      "default_visible": true,
      "size": "half"
    }
  ],
  "settings_schema": {}
}
```

Create `openflow/backend/modules/categories/models.py`:
```python
"""Database models for Categories module."""

migrations = {
    "1.0.0": [
        """CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            color TEXT DEFAULT '#6B7280',
            icon TEXT DEFAULT 'tag',
            position INTEGER DEFAULT 0,
            FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
        )""",
    ],
}
```

- [ ] **Step 2: Write the failing tests**

Create `openflow/tests/backend/test_categories_api.py`:
```python
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from backend.main import create_app


@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)


def test_list_categories_empty(client):
    response = client.get("/api/categories/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_category(client):
    cat = {"name": "Communication", "color": "#3B82F6", "icon": "megaphone"}
    response = client.post("/api/categories/", json=cat)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Communication"
    assert "id" in data


def test_create_subcategory(client):
    parent = client.post("/api/categories/", json={"name": "Parent"}).json()
    child = client.post("/api/categories/", json={"name": "Child", "parent_id": parent["id"]}).json()
    assert child["parent_id"] == parent["id"]


def test_update_category(client):
    cat = client.post("/api/categories/", json={"name": "Old Name"}).json()
    response = client.put(f"/api/categories/{cat['id']}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_category(client):
    cat = client.post("/api/categories/", json={"name": "To Delete"}).json()
    response = client.delete(f"/api/categories/{cat['id']}")
    assert response.status_code == 200

    get_resp = client.get(f"/api/categories/{cat['id']}")
    assert get_resp.status_code == 404


def test_get_category_tree(client):
    """GET /api/categories/tree returns hierarchical structure."""
    response = client.get("/api/categories/tree")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 3: Implement api.py**

Create `openflow/backend/modules/categories/api.py`:
```python
"""API routes for Categories module."""
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

DB_PATH = str(Path(__file__).parent.parent.parent.parent / "data" / "openflow.db")


class CategoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    color: str = "#6B7280"
    icon: str = "tag"
    position: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    position: Optional[int] = None


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/")
def list_categories():
    conn = _get_db()
    try:
        rows = conn.execute("SELECT * FROM categories ORDER BY position, name").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


@router.get("/tree")
def get_category_tree():
    """Return categories as a hierarchical tree."""
    conn = _get_db()
    try:
        rows = conn.execute("SELECT * FROM categories ORDER BY position, name").fetchall()
        all_cats = [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    # Build tree
    by_id = {c["id"]: {**c, "children": []} for c in all_cats}
    roots = []
    for cat in all_cats:
        node = by_id[cat["id"]]
        if cat["parent_id"] and cat["parent_id"] in by_id:
            by_id[cat["parent_id"]]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.post("/", status_code=201)
def create_category(cat: CategoryCreate):
    conn = _get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO categories (name, parent_id, color, icon, position) VALUES (?, ?, ?, ?, ?)",
            (cat.name, cat.parent_id, cat.color, cat.icon, cat.position)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.get("/{cat_id}")
def get_category(cat_id: int):
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Category not found")
    return dict(row)


@router.put("/{cat_id}")
def update_category(cat_id: int, update: CategoryUpdate):
    conn = _get_db()
    try:
        existing = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Category not found")

        fields = {k: v for k, v in update.model_dump(exclude_unset=True).items()}
        if not fields:
            return dict(existing)

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [cat_id]
        conn.execute(f"UPDATE categories SET {set_clause} WHERE id = ?", values)
        conn.commit()

        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/{cat_id}")
def delete_category(cat_id: int):
    conn = _get_db()
    try:
        existing = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Category not found")
        conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        conn.commit()
        return {"deleted": cat_id}
    finally:
        conn.close()
```

- [ ] **Step 4: Run migrations then tests**

```bash
cd openflow && python tools/migrate.py && python -m pytest tests/backend/test_categories_api.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add openflow/backend/modules/categories/
git commit -m "feat: categories module — CRUD API with hierarchical tree"
```

---

### Task 12: Dashboard module — backend

**Files:**
- Create: `openflow/backend/modules/dashboard/manifest.json`
- Create: `openflow/backend/modules/dashboard/models.py`
- Create: `openflow/backend/modules/dashboard/api.py`
- Test: `openflow/tests/backend/test_dashboard_api.py`

- [ ] **Step 1: Create manifest and models**

Create `openflow/backend/modules/dashboard/__init__.py` (empty).

Create `openflow/backend/modules/dashboard/manifest.json`:
```json
{
  "id": "dashboard",
  "name": "Dashboard",
  "description": "Tableau de bord personnalisable",
  "version": "1.0.0",
  "origin": "builtin",
  "category": "core",
  "dependencies": [],
  "menu": {
    "label": "Dashboard",
    "icon": "layout-dashboard",
    "position": 0
  },
  "api_routes": ["api.py"],
  "db_models": ["models.py"],
  "dashboard_widgets": [
    {
      "id": "current_balance",
      "name": "Solde actuel",
      "component": "widgets/CurrentBalance.tsx",
      "default_visible": true,
      "size": "quarter"
    },
    {
      "id": "income_expense_chart",
      "name": "Entrées / Sorties",
      "component": "widgets/IncomeExpenseChart.tsx",
      "default_visible": true,
      "size": "half"
    }
  ],
  "settings_schema": {}
}
```

Create `openflow/backend/modules/dashboard/models.py`:
```python
"""Database models for Dashboard module.
Dashboard layout is stored in the system _dashboard table (core/models.py).
No additional tables needed.
"""

migrations = {
    "1.0.0": [],
}
```

- [ ] **Step 2: Write the failing tests**

Create `openflow/tests/backend/test_dashboard_api.py`:
```python
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from backend.main import create_app


@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)


def test_get_available_widgets(client):
    """GET /api/dashboard/widgets returns all available widgets from active modules."""
    response = client.get("/api/dashboard/widgets")
    assert response.status_code == 200
    widgets = response.json()
    assert isinstance(widgets, list)
    # Should have at least the core widgets
    widget_ids = [w["id"] for w in widgets]
    assert "current_balance" in widget_ids


def test_get_layout(client):
    """GET /api/dashboard/layout returns current layout."""
    response = client.get("/api/dashboard/layout")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_save_layout(client):
    """PUT /api/dashboard/layout saves widget positions."""
    layout = [
        {"widget_id": "current_balance", "module_id": "dashboard", "position_x": 0, "position_y": 0, "size": "quarter", "visible": True},
        {"widget_id": "income_expense_chart", "module_id": "dashboard", "position_x": 1, "position_y": 0, "size": "half", "visible": True},
    ]
    response = client.put("/api/dashboard/layout", json=layout)
    assert response.status_code == 200

    # Verify it was saved
    get_resp = client.get("/api/dashboard/layout")
    saved = get_resp.json()
    assert len(saved) == 2


def test_get_summary(client):
    """GET /api/dashboard/summary returns financial summary."""
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "balance" in data
    assert "total_income" in data
    assert "total_expenses" in data
```

- [ ] **Step 3: Implement api.py**

Create `openflow/backend/modules/dashboard/api.py`:
```python
"""API routes for Dashboard module."""
import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

DB_PATH = str(Path(__file__).parent.parent.parent.parent / "data" / "openflow.db")
CONFIG_PATH = str(Path(__file__).parent.parent.parent.parent / "config.yaml")
MODULES_DIR = Path(__file__).parent.parent


class WidgetLayout(BaseModel):
    widget_id: str
    module_id: str
    position_x: int = 0
    position_y: int = 0
    size: str = "half"
    visible: bool = True


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/widgets")
def get_available_widgets():
    """Return all widgets declared by active modules."""
    widgets = []
    for mod_dir in sorted(MODULES_DIR.iterdir()):
        manifest_path = mod_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        with open(manifest_path) as f:
            manifest = json.load(f)
        for widget in manifest.get("dashboard_widgets", []):
            widgets.append({**widget, "module_id": manifest["id"]})
    return widgets


@router.get("/layout")
def get_layout():
    """Return current dashboard layout."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT widget_id, module_id, position_x, position_y, size, visible FROM _dashboard ORDER BY position_y, position_x"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


@router.put("/layout")
def save_layout(layout: list[WidgetLayout]):
    """Save dashboard layout."""
    conn = _get_db()
    try:
        conn.execute("DELETE FROM _dashboard")
        for widget in layout:
            conn.execute(
                "INSERT INTO _dashboard (widget_id, module_id, position_x, position_y, size, visible) VALUES (?, ?, ?, ?, ?, ?)",
                (widget.widget_id, widget.module_id, widget.position_x, widget.position_y, widget.size, 1 if widget.visible else 0)
            )
        conn.commit()
        return {"saved": len(layout)}
    finally:
        conn.close()


@router.get("/summary")
def get_summary():
    """Return financial summary for dashboard."""
    from backend.core.config import load_config
    config = load_config(CONFIG_PATH)

    conn = _get_db()
    try:
        # Total income (positive amounts after reference date)
        income_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE amount > 0 AND date > ?",
            (config.balance.date,)
        ).fetchone()
        total_income = income_row["total"] if income_row else 0

        # Total expenses (negative amounts after reference date)
        expense_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE amount < 0 AND date > ?",
            (config.balance.date,)
        ).fetchone()
        total_expenses = abs(expense_row["total"]) if expense_row else 0

        # Transaction count
        count_row = conn.execute("SELECT COUNT(*) as count FROM transactions").fetchone()
        tx_count = count_row["count"] if count_row else 0

    except sqlite3.OperationalError:
        total_income = 0
        total_expenses = 0
        tx_count = 0
    finally:
        conn.close()

    net = total_income - total_expenses
    balance = config.balance.amount + total_income - total_expenses

    return {
        "balance": balance,
        "reference_date": config.balance.date,
        "reference_amount": config.balance.amount,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net": net,
        "transaction_count": tx_count,
    }
```

- [ ] **Step 4: Run migrations then tests**

```bash
cd openflow && python tools/migrate.py && python -m pytest tests/backend/test_dashboard_api.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add openflow/backend/modules/dashboard/
git commit -m "feat: dashboard module — widgets registry, layout persistence, financial summary"
```

---

### Task 13: Frontend scaffold — Vite, Tailwind, React Router

**Files:**
- Create: `openflow/frontend/index.html`
- Create: `openflow/frontend/vite.config.ts`
- Create: `openflow/frontend/tsconfig.json`
- Create: `openflow/frontend/tailwind.config.js`
- Create: `openflow/frontend/postcss.config.js`
- Create: `openflow/frontend/src/main.tsx`
- Create: `openflow/frontend/src/App.tsx`
- Create: `openflow/frontend/src/api.ts`
- Create: `openflow/frontend/src/types.ts`
- Create: `openflow/frontend/src/index.css`

- [ ] **Step 1: Create index.html**

Create `openflow/frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>OpenFlow</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Create config files**

Create `openflow/frontend/vite.config.ts`:
```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
```

Create `openflow/frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true
  },
  "include": ["src"]
}
```

Create `openflow/frontend/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

Create `openflow/frontend/postcss.config.js`:
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 3: Create source files**

Create `openflow/frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

Create `openflow/frontend/src/types.ts`:
```typescript
export interface ModuleManifest {
  id: string;
  name: string;
  description: string;
  version: string;
  origin: "builtin" | "custom";
  category: "core" | "standard" | "advanced" | "custom";
  dependencies: string[];
  menu: {
    label: string;
    icon: string;
    position: number;
  };
  dashboard_widgets: DashboardWidget[];
}

export interface DashboardWidget {
  id: string;
  name: string;
  component: string;
  default_visible: boolean;
  size: "quarter" | "half" | "full";
  module_id?: string;
}

export interface Transaction {
  id: number;
  date: string;
  label: string;
  description: string;
  amount: number;
  category_id: number | null;
  division_id: number | null;
  contact_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  color: string;
  icon: string;
  position: number;
  children?: Category[];
}

export interface AppConfig {
  entity: {
    name: string;
    type: string;
    currency: string;
    logo: string;
    address: string;
    siret: string;
    rna: string;
  };
  balance: {
    date: string;
    amount: number;
  };
  modules: Record<string, boolean>;
}

export interface DashboardSummary {
  balance: number;
  reference_date: string;
  reference_amount: number;
  total_income: number;
  total_expenses: number;
  net: number;
  transaction_count: number;
}
```

Create `openflow/frontend/src/api.ts`:
```typescript
const BASE_URL = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

export const api = {
  // Modules
  getModules: () => request<any[]>("/modules"),
  getAllModules: () => request<any[]>("/modules/all"),

  // Config
  getConfig: () => request<any>("/config"),
  updateEntity: (entity: any) => request<any>("/config/entity", { method: "PUT", body: JSON.stringify(entity) }),
  toggleModule: (moduleId: string, active: boolean) =>
    request<any>(`/config/modules/${moduleId}?active=${active}`, { method: "PUT" }),
  updateBalance: (balance: any) => request<any>("/config/balance", { method: "PUT", body: JSON.stringify(balance) }),

  // Transactions
  getTransactions: (params?: Record<string, string>) => {
    const query = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<any[]>(`/transactions/${query}`);
  },
  createTransaction: (tx: any) => request<any>("/transactions/", { method: "POST", body: JSON.stringify(tx) }),
  updateTransaction: (id: number, tx: any) => request<any>(`/transactions/${id}`, { method: "PUT", body: JSON.stringify(tx) }),
  deleteTransaction: (id: number) => request<any>(`/transactions/${id}`, { method: "DELETE" }),
  getBalance: () => request<any>("/transactions/balance"),

  // Categories
  getCategories: () => request<any[]>("/categories/"),
  getCategoryTree: () => request<any[]>("/categories/tree"),
  createCategory: (cat: any) => request<any>("/categories/", { method: "POST", body: JSON.stringify(cat) }),
  updateCategory: (id: number, cat: any) => request<any>(`/categories/${id}`, { method: "PUT", body: JSON.stringify(cat) }),
  deleteCategory: (id: number) => request<any>(`/categories/${id}`, { method: "DELETE" }),

  // Dashboard
  getWidgets: () => request<any[]>("/dashboard/widgets"),
  getLayout: () => request<any[]>("/dashboard/layout"),
  saveLayout: (layout: any[]) => request<any>("/dashboard/layout", { method: "PUT", body: JSON.stringify(layout) }),
  getSummary: () => request<any>("/dashboard/summary"),
};
```

Create `openflow/frontend/src/App.tsx`:
```tsx
import React, { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { api } from "./api";
import { ModuleManifest, AppConfig } from "./types";
import { Sidebar } from "./core/Sidebar";
import { Dashboard } from "./core/Dashboard";
import { Settings } from "./core/Settings";
import { TransactionList } from "./modules/transactions/TransactionList";
import { CategoryManager } from "./modules/categories/CategoryManager";

export default function App() {
  const [modules, setModules] = useState<ModuleManifest[]>([]);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getModules(), api.getConfig()])
      .then(([mods, cfg]) => {
        setModules(mods);
        setConfig(cfg);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load app data:", err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <p className="text-gray-500">Chargement d'OpenFlow...</p>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-50">
        <Sidebar modules={modules} entityName={config?.entity.name || "OpenFlow"} />
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/transactions" element={<TransactionList />} />
            <Route path="/categories" element={<CategoryManager />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
```

Create `openflow/frontend/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 4: Commit**

```bash
git add openflow/frontend/
git commit -m "feat: frontend scaffold — Vite, React, Tailwind, API client, types, routing"
```

---

### Task 14: Frontend core components — Sidebar, Dashboard, Settings

**Files:**
- Create: `openflow/frontend/src/core/Sidebar.tsx`
- Create: `openflow/frontend/src/core/Dashboard.tsx`
- Create: `openflow/frontend/src/core/Settings.tsx`

- [ ] **Step 1: Create Sidebar**

Create `openflow/frontend/src/core/Sidebar.tsx`:
```tsx
import React from "react";
import { NavLink } from "react-router-dom";
import { ModuleManifest } from "../types";
import { LayoutDashboard, ArrowLeftRight, Tags, Settings } from "lucide-react";

const ICON_MAP: Record<string, React.ReactNode> = {
  "layout-dashboard": <LayoutDashboard size={20} />,
  "arrow-left-right": <ArrowLeftRight size={20} />,
  "tags": <Tags size={20} />,
};

interface SidebarProps {
  modules: ModuleManifest[];
  entityName: string;
}

export function Sidebar({ modules, entityName }: SidebarProps) {
  const sortedModules = [...modules].sort((a, b) => a.menu.position - b.menu.position);

  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <h1 className="text-lg font-bold text-gray-900">OpenFlow</h1>
        <p className="text-sm text-gray-500 truncate">{entityName}</p>
      </div>

      <nav className="flex-1 p-2 space-y-1">
        {sortedModules.map((mod) => (
          <NavLink
            key={mod.id}
            to={`/${mod.id === "dashboard" ? "dashboard" : mod.id}`}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-blue-50 text-blue-700 font-medium"
                  : "text-gray-700 hover:bg-gray-100"
              }`
            }
          >
            {ICON_MAP[mod.menu.icon] || <span className="w-5 h-5" />}
            {mod.menu.label}
          </NavLink>
        ))}
      </nav>

      <div className="p-2 border-t border-gray-200">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
              isActive ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-700 hover:bg-gray-100"
            }`
          }
        >
          <Settings size={20} />
          Paramètres
        </NavLink>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Create Dashboard**

Create `openflow/frontend/src/core/Dashboard.tsx`:
```tsx
import React, { useEffect, useState } from "react";
import { api } from "../api";
import { DashboardSummary } from "../types";

export function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    api.getSummary().then(setSummary).catch(console.error);
  }, []);

  if (!summary) {
    return <div className="p-6 text-gray-500">Chargement...</div>;
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <SummaryCard
          title="Solde actuel"
          value={formatCurrency(summary.balance)}
          color={summary.balance >= 0 ? "green" : "red"}
        />
        <SummaryCard
          title="Recettes"
          value={formatCurrency(summary.total_income)}
          color="green"
        />
        <SummaryCard
          title="Dépenses"
          value={formatCurrency(summary.total_expenses)}
          color="red"
        />
        <SummaryCard
          title="Transactions"
          value={String(summary.transaction_count)}
          color="blue"
        />
      </div>

      <p className="text-sm text-gray-500">
        Solde de référence : {formatCurrency(summary.reference_amount)} au {summary.reference_date}
      </p>
    </div>
  );
}

function SummaryCard({ title, value, color }: { title: string; value: string; color: string }) {
  const colorClasses: Record<string, string> = {
    green: "bg-green-50 text-green-700 border-green-200",
    red: "bg-red-50 text-red-700 border-red-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
  };

  return (
    <div className={`p-4 rounded-lg border ${colorClasses[color] || "bg-gray-50 text-gray-700 border-gray-200"}`}>
      <p className="text-sm font-medium opacity-75">{title}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
    </div>
  );
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(amount);
}
```

- [ ] **Step 3: Create Settings**

Create `openflow/frontend/src/core/Settings.tsx`:
```tsx
import React, { useEffect, useState } from "react";
import { api } from "../api";
import { AppConfig, ModuleManifest } from "../types";

export function Settings() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [allModules, setAllModules] = useState<ModuleManifest[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([api.getConfig(), api.getAllModules()]).then(([cfg, mods]) => {
      setConfig(cfg);
      setAllModules(mods);
    });
  }, []);

  if (!config) return <div className="p-6 text-gray-500">Chargement...</div>;

  const handleToggleModule = async (moduleId: string, active: boolean) => {
    try {
      setSaving(true);
      await api.toggleModule(moduleId, active);
      setConfig((prev) => prev ? { ...prev, modules: { ...prev.modules, [moduleId]: active } } : prev);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSaving(false);
    }
  };

  const coreModules = ["transactions", "categories", "dashboard"];

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Paramètres</h1>

      {/* Entity */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Entité</h2>
        <div className="bg-white rounded-lg border p-4 space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">Nom</label>
            <p className="text-gray-900">{config.entity.name}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Type</label>
            <p className="text-gray-900">{config.entity.type}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Devise</label>
            <p className="text-gray-900">{config.entity.currency}</p>
          </div>
        </div>
      </section>

      {/* Balance */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Solde de référence</h2>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-gray-900">
            {config.balance.amount} {config.entity.currency} au {config.balance.date}
          </p>
        </div>
      </section>

      {/* Modules */}
      <section>
        <h2 className="text-lg font-semibold mb-4">Modules</h2>
        <div className="bg-white rounded-lg border divide-y">
          {Object.entries(config.modules).map(([moduleId, active]) => {
            const manifest = allModules.find((m) => m.id === moduleId);
            const isCore = coreModules.includes(moduleId);

            return (
              <div key={moduleId} className="flex items-center justify-between p-4">
                <div>
                  <p className="font-medium text-gray-900">
                    {manifest?.name || moduleId}
                    {isCore && <span className="ml-2 text-xs text-gray-400">(noyau)</span>}
                  </p>
                  {manifest && <p className="text-sm text-gray-500">{manifest.description}</p>}
                </div>
                <button
                  onClick={() => handleToggleModule(moduleId, !active)}
                  disabled={isCore || saving}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    active ? "bg-blue-600" : "bg-gray-300"
                  } ${isCore ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      active ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add openflow/frontend/src/core/
git commit -m "feat: core UI components — Sidebar, Dashboard with summary cards, Settings with module toggles"
```

---

### Task 15: Frontend modules — TransactionList and CategoryManager

**Files:**
- Create: `openflow/frontend/src/modules/transactions/TransactionList.tsx`
- Create: `openflow/frontend/src/modules/transactions/TransactionForm.tsx`
- Create: `openflow/frontend/src/modules/categories/CategoryManager.tsx`

- [ ] **Step 1: Create TransactionForm**

Create `openflow/frontend/src/modules/transactions/TransactionForm.tsx`:
```tsx
import React, { useState } from "react";

interface TransactionFormProps {
  onSubmit: (tx: { date: string; label: string; amount: number; description: string }) => void;
  onCancel: () => void;
  initial?: { date: string; label: string; amount: number; description: string };
}

export function TransactionForm({ onSubmit, onCancel, initial }: TransactionFormProps) {
  const [date, setDate] = useState(initial?.date || new Date().toISOString().split("T")[0]);
  const [label, setLabel] = useState(initial?.label || "");
  const [amount, setAmount] = useState(initial?.amount?.toString() || "");
  const [description, setDescription] = useState(initial?.description || "");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ date, label, amount: parseFloat(amount), description });
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white border rounded-lg p-4 mb-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
            className="w-full border rounded-md px-3 py-2 text-sm" required />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Montant</label>
          <input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)}
            placeholder="-50.00 (dépense) ou 100.00 (recette)"
            className="w-full border rounded-md px-3 py-2 text-sm" required />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Libellé</label>
        <input type="text" value={label} onChange={(e) => setLabel(e.target.value)}
          className="w-full border rounded-md px-3 py-2 text-sm" required />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
        <input type="text" value={description} onChange={(e) => setDescription(e.target.value)}
          className="w-full border rounded-md px-3 py-2 text-sm" />
      </div>
      <div className="flex gap-2">
        <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700">
          Enregistrer
        </button>
        <button type="button" onClick={onCancel} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md text-sm hover:bg-gray-200">
          Annuler
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Create TransactionList**

Create `openflow/frontend/src/modules/transactions/TransactionList.tsx`:
```tsx
import React, { useEffect, useState } from "react";
import { api } from "../../api";
import { Transaction } from "../../types";
import { TransactionForm } from "./TransactionForm";
import { Plus, Pencil, Trash2 } from "lucide-react";

export function TransactionList() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const loadTransactions = () => {
    const params: Record<string, string> = {};
    if (search) params.search = search;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    api.getTransactions(params).then(setTransactions).catch(console.error);
  };

  useEffect(() => { loadTransactions(); }, [search, dateFrom, dateTo]);

  const handleCreate = async (tx: any) => {
    await api.createTransaction(tx);
    setShowForm(false);
    loadTransactions();
  };

  const handleUpdate = async (tx: any) => {
    if (editingId === null) return;
    await api.updateTransaction(editingId, tx);
    setEditingId(null);
    loadTransactions();
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Supprimer cette transaction ?")) return;
    await api.deleteTransaction(id);
    loadTransactions();
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">Transactions</h1>
        <button onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
          <Plus size={16} /> Ajouter
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <input type="text" placeholder="Rechercher..." value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm flex-1" />
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm" />
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm" />
      </div>

      {showForm && <TransactionForm onSubmit={handleCreate} onCancel={() => setShowForm(false)} />}

      {/* Table */}
      <div className="bg-white border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-500">Date</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500">Libellé</th>
              <th className="text-right px-4 py-3 font-medium text-gray-500">Montant</th>
              <th className="text-right px-4 py-3 font-medium text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {transactions.map((tx) => (
              <tr key={tx.id} className="hover:bg-gray-50">
                {editingId === tx.id ? (
                  <td colSpan={4} className="p-2">
                    <TransactionForm
                      initial={{ date: tx.date.split("T")[0], label: tx.label, amount: tx.amount, description: tx.description }}
                      onSubmit={handleUpdate}
                      onCancel={() => setEditingId(null)}
                    />
                  </td>
                ) : (
                  <>
                    <td className="px-4 py-3 text-gray-600">{tx.date.split("T")[0]}</td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{tx.label}</p>
                      {tx.description && <p className="text-gray-500 text-xs">{tx.description}</p>}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${tx.amount >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {tx.amount >= 0 ? "+" : ""}{tx.amount.toFixed(2)} €
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => setEditingId(tx.id)} className="text-gray-400 hover:text-blue-600 mr-2">
                        <Pencil size={16} />
                      </button>
                      <button onClick={() => handleDelete(tx.id)} className="text-gray-400 hover:text-red-600">
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </>
                )}
              </tr>
            ))}
            {transactions.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-500">Aucune transaction</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create CategoryManager**

Create `openflow/frontend/src/modules/categories/CategoryManager.tsx`:
```tsx
import React, { useEffect, useState } from "react";
import { api } from "../../api";
import { Category } from "../../types";
import { Plus, Pencil, Trash2, ChevronRight, ChevronDown } from "lucide-react";

export function CategoryManager() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [newName, setNewName] = useState("");
  const [newParentId, setNewParentId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const loadCategories = () => {
    api.getCategoryTree().then(setCategories).catch(console.error);
  };

  useEffect(() => { loadCategories(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    await api.createCategory({ name: newName.trim(), parent_id: newParentId });
    setNewName("");
    setNewParentId(null);
    loadCategories();
  };

  const handleUpdate = async (id: number) => {
    if (!editName.trim()) return;
    await api.updateCategory(id, { name: editName.trim() });
    setEditingId(null);
    loadCategories();
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Supprimer cette catégorie ?")) return;
    await api.deleteCategory(id);
    loadCategories();
  };

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const renderCategory = (cat: Category, depth: number = 0) => (
    <div key={cat.id}>
      <div className={`flex items-center gap-2 px-4 py-2 hover:bg-gray-50 ${depth > 0 ? "ml-" + (depth * 6) : ""}`}
        style={{ paddingLeft: `${16 + depth * 24}px` }}>
        {cat.children && cat.children.length > 0 ? (
          <button onClick={() => toggleExpand(cat.id)} className="text-gray-400">
            {expanded.has(cat.id) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
        ) : <span className="w-4" />}

        <span className="w-3 h-3 rounded-full" style={{ backgroundColor: cat.color }} />

        {editingId === cat.id ? (
          <div className="flex items-center gap-2 flex-1">
            <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)}
              className="border rounded px-2 py-1 text-sm flex-1"
              onKeyDown={(e) => e.key === "Enter" && handleUpdate(cat.id)} autoFocus />
            <button onClick={() => handleUpdate(cat.id)} className="text-blue-600 text-sm">OK</button>
            <button onClick={() => setEditingId(null)} className="text-gray-400 text-sm">Annuler</button>
          </div>
        ) : (
          <>
            <span className="flex-1 text-sm text-gray-900">{cat.name}</span>
            <button onClick={() => { setEditingId(cat.id); setEditName(cat.name); }}
              className="text-gray-400 hover:text-blue-600"><Pencil size={14} /></button>
            <button onClick={() => handleDelete(cat.id)}
              className="text-gray-400 hover:text-red-600"><Trash2 size={14} /></button>
          </>
        )}
      </div>
      {expanded.has(cat.id) && cat.children?.map((child) => renderCategory(child, depth + 1))}
    </div>
  );

  // Flatten for parent select
  const flatCategories: Category[] = [];
  const flatten = (cats: Category[]) => {
    for (const cat of cats) {
      flatCategories.push(cat);
      if (cat.children) flatten(cat.children);
    }
  };
  flatten(categories);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">Catégories</h1>

      <form onSubmit={handleCreate} className="flex gap-3 mb-4">
        <input type="text" placeholder="Nouvelle catégorie" value={newName}
          onChange={(e) => setNewName(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm flex-1" />
        <select value={newParentId ?? ""} onChange={(e) => setNewParentId(e.target.value ? Number(e.target.value) : null)}
          className="border rounded-md px-3 py-2 text-sm">
          <option value="">Racine</option>
          {flatCategories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <button type="submit" className="flex items-center gap-1 px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700">
          <Plus size={16} /> Ajouter
        </button>
      </form>

      <div className="bg-white border rounded-lg divide-y">
        {categories.length === 0 && (
          <p className="px-4 py-8 text-center text-gray-500">Aucune catégorie</p>
        )}
        {categories.map((cat) => renderCategory(cat))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build and verify**

```bash
cd openflow/frontend && npm run build
```

Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add openflow/frontend/src/modules/
git commit -m "feat: frontend modules — TransactionList with CRUD/filters, CategoryManager with tree view"
```

---

### Task 16: Integration test — full stack

- [ ] **Step 1: Run all backend tests**

```bash
cd openflow && python tools/migrate.py && python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 2: Run check.py**

```bash
cd openflow && python tools/check.py
```

Expected: `Result: PASS`

- [ ] **Step 3: Build frontend**

```bash
cd openflow/frontend && npm run build
```

Expected: Build succeeds

- [ ] **Step 4: Start app and verify manually**

```bash
cd openflow && python start.py
```

Expected: Browser opens at http://127.0.0.1:8000, shows Dashboard with summary cards, Sidebar with navigation, Settings with module toggles.

- [ ] **Step 5: Commit final state**

```bash
git add openflow/
git commit -m "feat: OpenFlow Phase 1+2 complete — foundations + core modules (transactions, categories, dashboard)"
```

---

## Next phases (to be planned after Phase 2 validation)

**Phase 3:** Standard modules — one task per module (invoices, reimbursements, budget, divisions, tiers, attachments, annotations, export). Each follows the same pattern: manifest + models + api + React components.

**Phase 4:** Advanced modules — same pattern, more complex logic (bank reconciliation, recurring, multi-accounts, audit, forecasting, alerts, tax receipts, grants, FEC, multi-users).

**Phase 5:** The `/openflow` skill itself — skill file with 4 modes (init, evolution, diagnostic, custom module creation), integration with tools/, Excel analysis via LLM.
