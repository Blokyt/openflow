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
    vat_enabled: bool = False


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
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    entity = EntityConfig(**raw.get("entity", {}))
    balance = BalanceConfig(**raw.get("balance", {}))
    modules = raw.get("modules", {"transactions": True, "categories": True, "dashboard": True})
    return AppConfig(entity=entity, balance=balance, modules=modules)


def save_config(config: AppConfig, path: str) -> None:
    data = {
        "entity": asdict(config.entity),
        "balance": asdict(config.balance),
        "modules": config.modules,
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
