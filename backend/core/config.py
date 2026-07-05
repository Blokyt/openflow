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
class ServerConfig:
    # 127.0.0.1 par défaut (dev) ; passer à 0.0.0.0 pour exposer sur le LAN.
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass
class ExternalBackupConfig:
    # Dossier de destination des sauvegardes quotidiennes (partage réseau,
    # NAS, dossier Drive monté). Vide = sauvegarde externe non configurée.
    destination: str = ""
    retention: int = 14


@dataclass
class AppConfig:
    entity: EntityConfig = field(default_factory=EntityConfig)
    balance: BalanceConfig = field(default_factory=BalanceConfig)
    modules: dict[str, bool] = field(default_factory=lambda: {
        "transactions": True,
        "categories": True,
        "dashboard": True,
    })
    server: ServerConfig = field(default_factory=ServerConfig)
    external_backup: ExternalBackupConfig = field(default_factory=ExternalBackupConfig)


def load_config(path: str) -> AppConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    entity = EntityConfig(**raw.get("entity", {}))
    balance = BalanceConfig(**raw.get("balance", {}))
    modules = raw.get("modules", {"transactions": True, "categories": True, "dashboard": True})
    server = ServerConfig(**raw.get("server", {}))
    external_backup = ExternalBackupConfig(**raw.get("external_backup", {}))
    return AppConfig(entity=entity, balance=balance, modules=modules, server=server,
                      external_backup=external_backup)


def save_config(config: AppConfig, path: str) -> None:
    data = {
        "entity": asdict(config.entity),
        "balance": asdict(config.balance),
        "modules": config.modules,
        "server": asdict(config.server),
        "external_backup": asdict(config.external_backup),
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
