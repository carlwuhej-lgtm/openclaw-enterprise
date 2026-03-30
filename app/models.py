"""
OpenClaw Enterprise - 数据库模型
所有 SQLAlchemy 模型集中定义，避免循环导入
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    code = Column(String(50), unique=True)
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    
    devices = relationship("Device", back_populates="tenant")
    users = relationship("User", back_populates="tenant")


class Device(Base):
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True)
    hostname = Column(String(100), unique=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    version = Column(String(20))
    status = Column(String(20), default="offline")
    risk_level = Column(String(10), default="low")
    ip_address = Column(String(50))
    os_info = Column(String(200))
    risk_score = Column(Integer, default=0)
    last_active = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    
    tenant = relationship("Tenant", back_populates="devices")
    user = relationship("User", back_populates="devices")
    audit_logs = relationship("AuditLog", back_populates="device")


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    hashed_password = Column(String(255))
    real_name = Column(String(100))
    email = Column(String(100))
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    role = Column(String(20), default="user")  # admin, manager, user, viewer
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    tenant = relationship("Tenant", back_populates="users")
    devices = relationship("Device", back_populates="user")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    operation_type = Column(String(50))
    operation_detail = Column(Text)
    risk_level = Column(String(10))
    status = Column(String(20))
    timestamp = Column(DateTime, default=datetime.now, index=True)
    
    device = relationship("Device", back_populates="audit_logs")


class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    description = Column(Text)
    level = Column(String(10))
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now, index=True)
    resolved_at = Column(DateTime, nullable=True)


class SecurityPolicy(Base):
    __tablename__ = "security_policies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True)
    description = Column(String(500))
    is_enabled = Column(Boolean, default=True)
    config = Column(Text)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
