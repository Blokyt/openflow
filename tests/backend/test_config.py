import os
import tempfile
import pytest
import yaml
from pathlib import Path


def test_load_config_from_file():
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
    from backend.core.config import load_config
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")


def test_toggle_module():
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
