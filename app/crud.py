"""
OpenClaw Enterprise - 完整 CRUD API
包含增删改查、分页、搜索、批量操作
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.main import get_db, Device, Alert, Tenant, User, AuditLog, SecurityPolicy
from pydantic import BaseModel, ConfigDict

router = APIRouter()

# ==================== Pydantic 模型 ====================

class DeviceBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    hostname: str
    version: str
    tenant_id: Optional[int] = None
    user_id: Optional[int] = None

class DeviceCreate(DeviceBase):
    pass

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    hostname: Optional[str] = None
    version: Optional[str] = None
    tenant_id: Optional[int] = None
    user_id: Optional[int] = None
    status: Optional[str] = None
    risk_level: Optional[str] = None
    risk_score: Optional[int] = None

class DeviceResponse(DeviceBase):
    id: int
    status: str
    risk_level: str
    risk_score: int
    last_active: Optional[datetime]
    created_at: datetime

class DeviceListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[DeviceResponse]

# ==================== 设备管理 ====================

@router.get("/api/devices", response_model=DeviceListResponse)
async def get_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取设备列表（分页 + 搜索 + 筛选）"""
    query = db.query(Device)
    
    # 搜索
    if search:
        query = query.filter(
            (Device.name.contains(search)) |
            (Device.hostname.contains(search))
        )
    
    # 筛选
    if status:
        query = query.filter(Device.status == status)
    if risk_level:
        query = query.filter(Device.risk_level == risk_level)
    if tenant_id:
        query = query.filter(Device.tenant_id == tenant_id)
    
    # 总数
    total = query.count()
    
    # 分页
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    
    return DeviceListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )

@router.get("/api/devices/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: int, db: Session = Depends(get_db)):
    """获取设备详情"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    return device

@router.post("/api/devices", response_model=DeviceResponse)
async def create_device(device: DeviceCreate, db: Session = Depends(get_db)):
    """创建设备"""
    db_device = Device(**device.dict(), status="online", risk_level="low", risk_score=0, last_active=datetime.now())
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device

@router.put("/api/devices/{device_id}", response_model=DeviceResponse)
async def update_device(device_id: int, device: DeviceUpdate, db: Session = Depends(get_db)):
    """更新设备"""
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    for key, value in device.dict(exclude_unset=True).items():
        setattr(db_device, key, value)
    
    db.commit()
    db.refresh(db_device)
    return db_device

@router.delete("/api/devices/{device_id}")
async def delete_device(device_id: int, db: Session = Depends(get_db)):
    """删除设备"""
    db_device = db.query(Device).filter(Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    db.delete(db_device)
    db.commit()
    return {"message": "设备已删除", "id": device_id}

@router.post("/api/devices/batch-delete")
async def batch_delete_devices(device_ids: List[int], db: Session = Depends(get_db)):
    """批量删除设备"""
    db.query(Device).filter(Device.id.in_(device_ids)).delete(synchronize_session=False)
    db.commit()
    return {"message": f"已删除 {len(device_ids)} 台设备", "count": len(device_ids)}

# ==================== 告警管理 ====================

class AlertBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str
    description: str
    level: str
    device_id: Optional[int] = None

class AlertCreate(AlertBase):
    pass

class AlertUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    device_id: Optional[int] = None
    is_resolved: Optional[bool] = None

class AlertResponse(AlertBase):
    id: int
    is_resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime]

class AlertListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AlertResponse]

@router.get("/api/alerts", response_model=AlertListResponse)
async def get_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    level: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """获取告警列表（分页 + 搜索 + 筛选）"""
    query = db.query(Alert)
    
    if search:
        query = query.filter(
            (Alert.title.contains(search)) |
            (Alert.description.contains(search))
        )
    
    if level:
        query = query.filter(Alert.level == level)
    if is_resolved is not None:
        query = query.filter(Alert.is_resolved == is_resolved)
    
    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(Alert.created_at.desc()).offset(offset).limit(page_size).all()
    
    return AlertListResponse(total=total, page=page, page_size=page_size, items=items)

@router.get("/api/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """获取告警详情"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    return alert

@router.post("/api/alerts", response_model=AlertResponse)
async def create_alert(alert: AlertCreate, db: Session = Depends(get_db)):
    """创建告警"""
    db_alert = Alert(**alert.dict(), is_resolved=False, created_at=datetime.now())
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

@router.put("/api/alerts/{alert_id}", response_model=AlertResponse)
async def update_alert(alert_id: int, alert: AlertUpdate, db: Session = Depends(get_db)):
    """更新告警"""
    db_alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not db_alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    
    for key, value in alert.dict(exclude_unset=True).items():
        setattr(db_alert, key, value)
    
    if alert.is_resolved and not db_alert.is_resolved:
        db_alert.resolved_at = datetime.now()
    
    db.commit()
    db.refresh(db_alert)
    return db_alert

@router.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """删除告警"""
    db_alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not db_alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    
    db.delete(db_alert)
    db.commit()
    return {"message": "告警已删除", "id": alert_id}

@router.post("/api/alerts/batch-resolve")
async def batch_resolve_alerts(alert_ids: List[int], db: Session = Depends(get_db)):
    """批量解决告警"""
    db.query(Alert).filter(Alert.id.in_(alert_ids)).update({
        "is_resolved": True,
        "resolved_at": datetime.now()
    }, synchronize_session=False)
    db.commit()
    return {"message": f"已解决 {len(alert_ids)} 条告警", "count": len(alert_ids)}

# ==================== 租户管理 ====================

class TenantBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    code: str
    description: Optional[str] = None

class TenantCreate(TenantBase):
    pass

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class TenantResponse(TenantBase):
    id: int
    is_active: bool
    created_at: datetime

class TenantListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[TenantResponse]

@router.get("/api/tenants", response_model=TenantListResponse)
async def get_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取租户列表（分页 + 搜索）"""
    query = db.query(Tenant)
    
    if search:
        query = query.filter(
            (Tenant.name.contains(search)) |
            (Tenant.code.contains(search))
        )
    
    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    
    return TenantListResponse(total=total, page=page, page_size=page_size, items=items)

@router.get("/api/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: int, db: Session = Depends(get_db)):
    """获取租户详情"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    return tenant

@router.post("/api/tenants", response_model=TenantResponse)
async def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """创建租户"""
    # 检查代码是否重复
    existing = db.query(Tenant).filter(Tenant.code == tenant.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="租户代码已存在")
    
    db_tenant = Tenant(**tenant.dict(), is_active=True, created_at=datetime.now())
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@router.put("/api/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(tenant_id: int, tenant: TenantUpdate, db: Session = Depends(get_db)):
    """更新租户"""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    
    for key, value in tenant.dict(exclude_unset=True).items():
        setattr(db_tenant, key, value)
    
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@router.delete("/api/tenants/{tenant_id}")
async def delete_tenant(tenant_id: int, db: Session = Depends(get_db)):
    """删除租户"""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    
    # 检查是否有关联设备
    device_count = db.query(Device).filter(Device.tenant_id == tenant_id).count()
    if device_count > 0:
        raise HTTPException(status_code=400, detail=f"租户下还有 {device_count} 台设备，无法删除")
    
    db.delete(db_tenant)
    db.commit()
    return {"message": "租户已删除", "id": tenant_id}

# ==================== 用户管理 ====================

class UserBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    username: str
    real_name: str
    email: Optional[str] = None
    tenant_id: int
    role: str = "user"

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    email: Optional[str] = None
    tenant_id: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

class UserListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[UserResponse]

@router.get("/api/users", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取用户列表（分页 + 搜索 + 筛选）"""
    query = db.query(User)
    
    if search:
        query = query.filter(
            (User.username.contains(search)) |
            (User.real_name.contains(search))
        )
    
    if tenant_id:
        query = query.filter(User.tenant_id == tenant_id)
    
    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    
    return UserListResponse(total=total, page=page, page_size=page_size, items=[
        UserResponse(
            id=u.id,
            username=u.username,
            real_name=u.real_name,
            email=u.email,
            tenant_id=u.tenant_id,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at
        ) for u in items
    ])

@router.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """获取用户详情"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserResponse(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        email=user.email,
        tenant_id=user.tenant_id,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at
    )

@router.post("/api/users", response_model=UserResponse)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """创建用户"""
    # 检查用户名是否重复
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    db_user = User(**user.dict(), is_active=True, created_at=datetime.now())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        real_name=db_user.real_name,
        email=db_user.email,
        tenant_id=db_user.tenant_id,
        role=db_user.role,
        is_active=db_user.is_active,
        created_at=db_user.created_at
    )

@router.put("/api/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db)):
    """更新用户"""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    for key, value in user.dict(exclude_unset=True).items():
        setattr(db_user, key, value)
    
    db.commit()
    db.refresh(db_user)
    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        real_name=db_user.real_name,
        email=db_user.email,
        tenant_id=db_user.tenant_id,
        role=db_user.role,
        is_active=db_user.is_active,
        created_at=db_user.created_at
    )

@router.delete("/api/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    """删除用户"""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    db.delete(db_user)
    db.commit()
    return {"message": "用户已删除", "id": user_id}

# ==================== 审计日志（只读） ====================

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    user_id: Optional[int]
    operation_type: str
    operation_detail: str
    risk_level: str
    status: str
    timestamp: datetime

class AuditLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AuditLogResponse]

@router.get("/api/audit-logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_id: Optional[int] = None,
    operation_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取审计日志（分页 + 筛选）"""
    query = db.query(AuditLog)
    
    if device_id:
        query = query.filter(AuditLog.device_id == device_id)
    if operation_type:
        query = query.filter(AuditLog.operation_type == operation_type)
    if risk_level:
        query = query.filter(AuditLog.risk_level == risk_level)
    if start_date:
        query = query.filter(AuditLog.timestamp >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(AuditLog.timestamp <= datetime.fromisoformat(end_date))
    
    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(page_size).all()
    
    return AuditLogListResponse(total=total, page=page, page_size=page_size, items=items)

# ==================== 策略管理 ====================

class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    is_enabled: bool
    config: Optional[str]
    updated_at: datetime

class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    config: Optional[str] = None

class PolicyListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[PolicyResponse]

@router.get("/api/policies", response_model=PolicyListResponse)
async def get_policies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取策略列表（分页）"""
    query = db.query(SecurityPolicy)
    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    
    return PolicyListResponse(total=total, page=page, page_size=page_size, items=items)

@router.put("/api/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(policy_id: int, policy: PolicyUpdate, db: Session = Depends(get_db)):
    """更新策略"""
    db_policy = db.query(SecurityPolicy).filter(SecurityPolicy.id == policy_id).first()
    if not db_policy:
        raise HTTPException(status_code=404, detail="策略不存在")
    
    for key, value in policy.dict(exclude_unset=True).items():
        setattr(db_policy, key, value)
    
    db_policy.updated_at = datetime.now()
    db.commit()
    db.refresh(db_policy)
    return db_policy
