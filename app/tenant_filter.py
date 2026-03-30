"""
OpenClaw Enterprise - 多租户数据隔离模块
提供租户过滤工具函数，确保非 admin 用户只能访问自己租户的数据
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from models import User, Device


def get_tenant_filter(current_user: User) -> Optional[int]:
    """
    返回租户过滤条件：admin 看全部，其他用户只看自己租户
    
    Returns:
        None: admin 用户，不过滤
        int: 非 admin 用户的 tenant_id
    """
    if current_user.role == 'admin':
        return None  # 不过滤
    return current_user.tenant_id


def get_tenant_device_ids(db: Session, current_user: User, tenant_id: Optional[int] = None) -> Optional[List[int]]:
    """
    获取租户关联的设备 ID 列表，用于过滤通过 device_id 关联的表（如 audit_logs, alerts）
    
    Returns:
        None: admin 用户且未指定 tenant_id，不过滤
        List[int]: 需要过滤的设备 ID 列表
    """
    if current_user.role == 'admin' and not tenant_id:
        return None  # admin 看全部
    
    filter_tenant_id = tenant_id if current_user.role == 'admin' else current_user.tenant_id
    if not filter_tenant_id:
        return []
    
    devices = db.query(Device.id).filter(Device.tenant_id == filter_tenant_id).all()
    return [d.id for d in devices]
