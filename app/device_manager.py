"""
OpenClaw Enterprise - 设备（资产）管理增强模块
提供设备注册、发现、详情、编辑/审批、分页等功能
"""
import asyncio
import math
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

# 导入数据库和模型
from database import SessionLocal, get_db
from models import Device, AuditLog

# ==================== APIRouter ====================
router = APIRouter(prefix="/api/devices", tags=["设备管理"])

# ==================== Pydantic 模型 ====================

# --- 通用分页响应 ---
class PaginatedResponse(BaseModel):
    """通用分页响应"""
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


# --- 设备注册 ---
class DeviceRegisterRequest(BaseModel):
    """设备注册请求"""
    name: str = Field(..., min_length=1, max_length=100, description="设备名称")
    hostname: str = Field(..., min_length=1, max_length=200, description="主机名")
    ip_address: str = Field(..., min_length=7, max_length=50, description="IP 地址")
    port: int = Field(default=8000, ge=1, le=65535, description="端口号")
    os_info: Optional[str] = Field(None, max_length=200, description="操作系统信息")
    location: str = Field(
        default="本机",
        description="设备位置: 本机/局域网/云端",
    )
    tags: Optional[str] = Field(None, max_length=500, description="标签，逗号分隔")
    description: Optional[str] = Field(None, max_length=1000, description="设备描述")

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: str) -> str:
        allowed = {"本机", "局域网", "云端"}
        if v not in allowed:
            raise ValueError(f"location 必须是 {allowed} 之一")
        return v


class DeviceRegisterResponse(BaseModel):
    """设备注册响应"""
    id: int
    name: str
    hostname: str
    ip_address: Optional[str]
    port: int
    os_info: Optional[str]
    location: str
    tags: Optional[str]
    description: Optional[str]
    status: str
    risk_level: str
    risk_score: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- 设备发现 ---
class DeviceDiscoverRequest(BaseModel):
    """设备发现请求"""
    subnet: str = Field(..., description="子网段，如 192.168.1.0/24")
    ports: List[int] = Field(default=[8000, 8080, 3000], description="扫描端口列表")
    timeout: float = Field(default=3.0, ge=0.5, le=30.0, description="单个连接超时(秒)")


class DiscoveredDevice(BaseModel):
    """发现的设备"""
    ip: str
    port: int
    hostname: Optional[str] = None
    version: Optional[str] = None
    os_info: Optional[str] = None
    is_openclaw: bool = False
    response_time_ms: Optional[float] = None


class DeviceDiscoverResponse(BaseModel):
    """设备发现响应"""
    subnet: str
    ports: List[int]
    total_scanned: int
    total_found: int
    devices: List[DiscoveredDevice]
    scan_duration_seconds: float


# --- 设备详情 ---
class AuditLogBrief(BaseModel):
    """审计日志简要信息"""
    id: int
    operation_type: str
    operation_detail: str
    risk_level: str
    status: str
    timestamp: datetime

    class Config:
        from_attributes = True


class DeviceDetailResponse(BaseModel):
    """设备详情响应"""
    id: int
    name: str
    hostname: str
    ip_address: Optional[str]
    os_info: Optional[str]
    version: Optional[str]
    status: str
    risk_level: str
    risk_score: int
    last_active: Optional[datetime]
    created_at: datetime
    # 扩展字段（存储在 version 字段中的 JSON 或用独立字段）
    port: Optional[int] = None
    location: Optional[str] = None
    tags: Optional[str] = None
    description: Optional[str] = None
    # 关联数据
    recent_audit_logs: List[AuditLogBrief] = []

    class Config:
        from_attributes = True


# --- 设备更新 ---
class DeviceUpdateRequest(BaseModel):
    """设备更新请求"""
    name: Optional[str] = Field(None, max_length=100)
    hostname: Optional[str] = Field(None, max_length=200)
    ip_address: Optional[str] = Field(None, max_length=50)
    os_info: Optional[str] = Field(None, max_length=200)
    version: Optional[str] = Field(None, max_length=20)
    risk_level: Optional[str] = Field(None, description="low/medium/high")
    tags: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=1000)

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"low", "medium", "high"}:
            raise ValueError("risk_level 必须是 low/medium/high")
        return v


class DeviceActionResponse(BaseModel):
    """设备操作响应"""
    id: int
    name: str
    status: str
    message: str


# --- 设备列表（分页） ---
class DeviceListItem(BaseModel):
    """设备列表项"""
    id: int
    name: str
    hostname: str
    ip_address: Optional[str]
    os_info: Optional[str]
    version: Optional[str]
    status: str
    risk_level: str
    risk_score: int
    last_active: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== 辅助函数 ====================

def _parse_metadata(device: Device) -> dict:
    """
    从 Device 模型中解析扩展元数据。
    由于现有 Device 模型没有 port/location/tags/description 字段，
    我们将这些信息序列化后存储在 version 字段的扩展部分（JSON）。
    为了不破坏现有数据，采用约定：如果 version 字段包含 '|' 分隔符，
    则后面是 JSON 元数据。
    """
    import json
    meta = {"port": 8000, "location": None, "tags": None, "description": None}
    if device.version and "|" in device.version:
        parts = device.version.split("|", 1)
        try:
            meta.update(json.loads(parts[1]))
        except (json.JSONDecodeError, IndexError):
            pass
    return meta


def _encode_version_with_meta(
    version: Optional[str],
    port: int = 8000,
    location: Optional[str] = None,
    tags: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """将版本号和元数据编码到 version 字段"""
    import json
    base_version = version or "unknown"
    meta = {}
    if port != 8000:
        meta["port"] = port
    if location:
        meta["location"] = location
    if tags:
        meta["tags"] = tags
    if description:
        meta["description"] = description
    if meta:
        return f"{base_version}|{json.dumps(meta, ensure_ascii=False)}"
    return base_version


def _get_base_version(device: Device) -> Optional[str]:
    """从可能带元数据的 version 字段中提取纯版本号"""
    if device.version and "|" in device.version:
        return device.version.split("|", 1)[0]
    return device.version


def _paginate(query, page: int, page_size: int) -> dict:
    """通用分页处理"""
    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ==================== 路由 ====================

# ---------- 1. 设备注册 ----------
@router.post("/register", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_device(req: DeviceRegisterRequest, db: Session = Depends(get_db)):
    """
    手动注册设备。注册后状态为 pending，等待审批。
    """
    # 检查 hostname 是否已存在
    existing = db.query(Device).filter(Device.hostname == req.hostname).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"设备 hostname '{req.hostname}' 已存在 (id={existing.id})",
        )

    version_str = _encode_version_with_meta(
        version="unknown",
        port=req.port,
        location=req.location,
        tags=req.tags,
        description=req.description,
    )

    device = Device(
        name=req.name,
        hostname=req.hostname,
        ip_address=req.ip_address,
        os_info=req.os_info,
        version=version_str,
        status="pending",
        risk_level="low",
        risk_score=0,
        created_at=datetime.now(),
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    meta = _parse_metadata(device)
    return DeviceRegisterResponse(
        id=device.id,
        name=device.name,
        hostname=device.hostname,
        ip_address=device.ip_address,
        port=meta.get("port", 8000),
        os_info=device.os_info,
        location=meta.get("location", "本机"),
        tags=meta.get("tags"),
        description=meta.get("description"),
        status=device.status,
        risk_level=device.risk_level,
        risk_score=device.risk_score,
        created_at=device.created_at,
    )


# ---------- 2. 设备发现 ----------
@router.post("/discover", response_model=DeviceDiscoverResponse)
async def discover_devices(req: DeviceDiscoverRequest):
    """
    扫描指定 IP 段发现 OpenClaw 实例。
    通过 HTTP 连接检测 /api/stats 端点判断是否为 OpenClaw。
    """
    import ipaddress
    import time

    start_time = time.monotonic()

    # 解析子网
    try:
        network = ipaddress.ip_network(req.subnet, strict=False)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的子网格式: {e}",
        )

    # 生成扫描目标
    targets = []
    for ip in network.hosts():
        for port in req.ports:
            targets.append((str(ip), port))

    # 限制扫描范围（防止滥用）
    MAX_TARGETS = 10000
    if len(targets) > MAX_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"扫描目标过多 ({len(targets)})，请缩小子网范围（最多 {MAX_TARGETS} 个目标）",
        )

    # 并发扫描
    semaphore = asyncio.Semaphore(50)
    discovered: List[DiscoveredDevice] = []

    async def probe(ip: str, port: int) -> Optional[DiscoveredDevice]:
        async with semaphore:
            url = f"http://{ip}:{port}/api/stats"
            try:
                probe_start = time.monotonic()
                async with httpx.AsyncClient(timeout=req.timeout) as client:
                    resp = await client.get(url)
                response_time = round((time.monotonic() - probe_start) * 1000, 2)

                if resp.status_code == 200:
                    data = resp.json()
                    # 判断是否是 OpenClaw 的 /api/stats 响应
                    is_oc = "total_devices" in data or "online_devices" in data
                    return DiscoveredDevice(
                        ip=ip,
                        port=port,
                        hostname=data.get("hostname"),
                        version=data.get("version"),
                        os_info=data.get("os_info"),
                        is_openclaw=is_oc,
                        response_time_ms=response_time,
                    )
                # 非 200 但有 HTTP 响应 — 可能是其他服务
                return DiscoveredDevice(
                    ip=ip,
                    port=port,
                    is_openclaw=False,
                    response_time_ms=round((time.monotonic() - probe_start) * 1000, 2),
                )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ConnectTimeout):
                return None
            except Exception:
                return None

    tasks = [probe(ip, port) for ip, port in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, DiscoveredDevice):
            discovered.append(r)

    scan_duration = round(time.monotonic() - start_time, 2)

    return DeviceDiscoverResponse(
        subnet=req.subnet,
        ports=req.ports,
        total_scanned=len(targets),
        total_found=len(discovered),
        devices=discovered,
        scan_duration_seconds=scan_duration,
    )


# ---------- 3. 设备详情 ----------
@router.get("/{device_id}/detail", response_model=DeviceDetailResponse)
async def get_device_detail(device_id: int, db: Session = Depends(get_db)):
    """
    获取设备详细信息，包括关联的最近审计日志。
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 最近 20 条审计日志
    recent_logs = (
        db.query(AuditLog)
        .filter(AuditLog.device_id == device_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(20)
        .all()
    )

    meta = _parse_metadata(device)

    return DeviceDetailResponse(
        id=device.id,
        name=device.name,
        hostname=device.hostname,
        ip_address=device.ip_address,
        os_info=device.os_info,
        version=_get_base_version(device),
        status=device.status,
        risk_level=device.risk_level,
        risk_score=device.risk_score,
        last_active=device.last_active,
        created_at=device.created_at,
        port=meta.get("port", 8000),
        location=meta.get("location"),
        tags=meta.get("tags"),
        description=meta.get("description"),
        recent_audit_logs=[
            AuditLogBrief(
                id=log.id,
                operation_type=log.operation_type,
                operation_detail=log.operation_detail,
                risk_level=log.risk_level,
                status=log.status,
                timestamp=log.timestamp,
            )
            for log in recent_logs
        ],
    )


# ---------- 4. 设备编辑/审批/阻断 ----------
@router.put("/{device_id}", response_model=DeviceListItem)
async def update_device(device_id: int, req: DeviceUpdateRequest, db: Session = Depends(get_db)):
    """更新设备信息"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    update_data = req.model_dump(exclude_unset=True)

    # 处理元数据字段
    meta_fields = {"tags", "description"}
    meta_updates = {k: v for k, v in update_data.items() if k in meta_fields}
    direct_updates = {k: v for k, v in update_data.items() if k not in meta_fields}

    # 更新直接字段
    for key, value in direct_updates.items():
        if value is not None:
            setattr(device, key, value)

    # 更新元数据（重新编码 version）
    if meta_updates:
        current_meta = _parse_metadata(device)
        current_meta.update(meta_updates)
        device.version = _encode_version_with_meta(
            version=_get_base_version(device),
            port=current_meta.get("port", 8000),
            location=current_meta.get("location"),
            tags=current_meta.get("tags"),
            description=current_meta.get("description"),
        )

    db.commit()
    db.refresh(device)

    return DeviceListItem(
        id=device.id,
        name=device.name,
        hostname=device.hostname,
        ip_address=device.ip_address,
        os_info=device.os_info,
        version=_get_base_version(device),
        status=device.status,
        risk_level=device.risk_level,
        risk_score=device.risk_score,
        last_active=device.last_active,
        created_at=device.created_at,
    )


@router.post("/{device_id}/approve", response_model=DeviceActionResponse)
async def approve_device(device_id: int, db: Session = Depends(get_db)):
    """审批待注册设备，将状态从 pending 改为 online"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    if device.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"设备当前状态为 '{device.status}'，仅 pending 状态可审批",
        )

    device.status = "online"
    device.last_active = datetime.now()
    db.commit()

    return DeviceActionResponse(
        id=device.id,
        name=device.name,
        status=device.status,
        message=f"设备 '{device.name}' 已审批通过",
    )


@router.post("/{device_id}/block", response_model=DeviceActionResponse)
async def block_device(device_id: int, db: Session = Depends(get_db)):
    """阻断设备"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    if device.status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="设备已处于阻断状态",
        )

    device.status = "blocked"
    db.commit()

    return DeviceActionResponse(
        id=device.id,
        name=device.name,
        status=device.status,
        message=f"设备 '{device.name}' 已被阻断",
    )


@router.post("/{device_id}/unblock", response_model=DeviceActionResponse)
async def unblock_device(device_id: int, db: Session = Depends(get_db)):
    """解除设备阻断"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    if device.status != "blocked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"设备当前状态为 '{device.status}'，仅 blocked 状态可解除阻断",
        )

    device.status = "online"
    device.last_active = datetime.now()
    db.commit()

    return DeviceActionResponse(
        id=device.id,
        name=device.name,
        status=device.status,
        message=f"设备 '{device.name}' 已解除阻断",
    )


# ---------- 5. 设备列表（分页） ----------
@router.get("/list")
async def list_devices(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="按状态筛选"),
    risk_level: Optional[str] = Query(default=None, description="按风险等级筛选"),
    search: Optional[str] = Query(default=None, description="搜索设备名/主机名/IP"),
    db: Session = Depends(get_db),
):
    """
    分页获取设备列表，支持按状态、风险等级筛选和搜索。
    返回格式: {"items": [...], "total": N, "page": 1, "page_size": 20, "total_pages": M}
    """
    query = db.query(Device)

    # 筛选条件
    if status_filter:
        query = query.filter(Device.status == status_filter)
    if risk_level:
        query = query.filter(Device.risk_level == risk_level)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Device.name.like(pattern))
            | (Device.hostname.like(pattern))
            | (Device.ip_address.like(pattern))
        )

    query = query.order_by(Device.created_at.desc())

    # 分页
    result = _paginate(query, page, page_size)

    # 序列化
    items = [
        DeviceListItem(
            id=d.id,
            name=d.name,
            hostname=d.hostname,
            ip_address=d.ip_address,
            os_info=d.os_info,
            version=_get_base_version(d),
            status=d.status,
            risk_level=d.risk_level,
            risk_score=d.risk_score,
            last_active=d.last_active,
            created_at=d.created_at,
        ).model_dump()
        for d in result["items"]
    ]

    return {
        "items": items,
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
    }
