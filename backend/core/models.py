from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, Text
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
