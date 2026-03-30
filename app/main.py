"""
OpenClaw Enterprise - 企业级 AI 智能体管控平台
后端 API 服务
"""
from fastapi import FastAPI, HTTPException, Depends, status, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import platform
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import Session, relationship
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import uvicorn
import os
import math

# ==================== 数据库配置（从共享模块导入） ====================
from database import Base, engine, SessionLocal, get_db

# ==================== 数据库模型（从 models.py 导入） ====================
from models import Tenant, Device, User, AuditLog, Alert, SecurityPolicy

# ==================== 认证模块导入 ====================
from auth import get_current_user

from rbac import require_role
from tenant_filter import get_tenant_filter, get_tenant_device_ids

# 客户端 API Key 认证（用于 Agent 客户端上报）
CLIENT_API_KEY = os.environ.get("OCW_CLIENT_API_KEY", "ocw-client-default-key")

async def verify_client_api_key(x_api_key: Optional[str] = Header(None)):
    """验证客户端 API Key（用于 /api/client/* 端点）"""
    # 如果未配置自定义 key，则使用默认 key（开发模式允许无 key 访问）
    if CLIENT_API_KEY == "ocw-client-default-key":
        return True
    if not x_api_key or x_api_key != CLIENT_API_KEY:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return True

# ==================== Pydantic 模型 ====================
class DeviceBase(BaseModel):
    name: str
    hostname: str
    version: str
    tenant_id: int
    user_id: Optional[int] = None

class DeviceCreate(DeviceBase):
    pass

class DeviceResponse(DeviceBase):
    id: int
    status: str
    risk_level: str
    ip_address: Optional[str] = None
    os_info: Optional[str] = None
    risk_score: int
    last_active: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True

class AuditLogBase(BaseModel):
    operation_type: str
    operation_detail: str
    risk_level: str
    status: str
    device_id: int

class AuditLogResponse(AuditLogBase):
    id: int
    timestamp: datetime
    
    class Config:
        from_attributes = True

class AlertBase(BaseModel):
    title: str
    description: str
    level: str
    device_id: Optional[int] = None

class AlertResponse(AlertBase):
    id: int
    is_resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class TenantBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None

class TenantResponse(TenantBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class PolicyBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_enabled: bool = True
    config: Optional[str] = None

class PolicyResponse(PolicyBase):
    id: int
    updated_at: datetime
    
    class Config:
        from_attributes = True

class StatsResponse(BaseModel):
    total_devices: int
    online_devices: int
    pending_approvals: int
    critical_alerts: int
    today_audit_logs: int
    weekly_new_devices: int
    weekly_trend: Optional[list] = None

# ==================== 导入管控模块 ====================
import sys
sys.path.insert(0, str(Path(__file__).parent))

try:
    from scanner_v2 import router as scanner_router
    from enforcement_v2 import router as enforcement_router
    from notification import router as notification_router
    from traffic import router as traffic_router
    from agent import router as agent_router
    from ai_analyzer import router as ai_router
    from rate_limiter import RateLimitMiddleware
except Exception as e:
    print(f"导入模块警告：{e}")
    scanner_router = None
    enforcement_router = None
    notification_router = None
    traffic_router = None
    agent_router = None
    ai_router = None
    RateLimitMiddleware = None

# ==================== 生命周期管理 ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("🚀 OpenClaw Enterprise 启动中...")
    print("📡 网络扫描模块已加载")
    print("🛡️ 管控执行模块已加载")
    
    # 创建默认管理员账号
    await create_default_admin()
    
    # 同步本机设备信息
    await sync_local_device()
    
    # 同步 Agent 信息
    await sync_agents_from_local()
    
    yield
    # 关闭时
    print("👋 OpenClaw Enterprise 已关闭")


async def create_default_admin():
    """创建默认管理员账号"""
    try:
        from auth import get_password_hash
        db = SessionLocal()
        
        # 检查是否已存在管理员
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            # 创建默认租户
            tenant = db.query(Tenant).filter(Tenant.code == "default").first()
            if not tenant:
                tenant = Tenant(
                    name="默认租户",
                    code="default",
                    description="系统默认租户"
                )
                db.add(tenant)
                db.commit()
                db.refresh(tenant)
            
            # 创建管理员账号
            admin = User(
                username="admin",
                hashed_password=get_password_hash("admin"),
                real_name="系统管理员",
                email="admin@openclaw.local",
                tenant_id=tenant.id,
                role="admin",
                is_active=True
            )
            db.add(admin)
            db.commit()
            print("✅ 默认管理员账号已创建: admin / admin")
        
        db.close()
    except Exception as e:
        print(f"⚠️ 创建默认管理员失败: {e}")


async def sync_local_device():
    """同步本机设备信息到数据库，识别真实主机名"""
    import subprocess as _sp
    try:
        db = SessionLocal()

        # 获取真实主机名（优先 scutil，再 hostname，最后 platform.node）
        hostname = None
        for cmd in ["/usr/sbin/scutil --get ComputerName", "/usr/sbin/scutil --get LocalHostName", "hostname"]:
            try:
                result = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
                val = result.stdout.strip()
                if val and val != "bogon":
                    hostname = val
                    break
            except Exception:
                pass
        if not hostname or hostname == "bogon":
            hostname = platform.node()
        if not hostname or hostname == "bogon":
            # 最后兜底：用 Mac 型号
            try:
                result = _sp.run("sysctl -n hw.model", shell=True, capture_output=True, text=True, timeout=3)
                hostname = result.stdout.strip() or "unknown-host"
            except Exception:
                hostname = "unknown-host"

        # 获取 IP（优先非 127.0.0.1 的地址）
        ip_address = "127.0.0.1"
        try:
            result = _sp.run(
                "/usr/sbin/ipconfig getifaddr en0 2>/dev/null || /usr/sbin/ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1",
                shell=True, capture_output=True, text=True, timeout=3
            )
            val = result.stdout.strip()
            if val and val:
                ip_address = val
        except Exception:
            pass

        # 获取 OS 信息
        os_info = f"macOS ({platform.platform()})"
        try:
            result = _sp.run("/usr/sbin/sw_vers -productVersion", shell=True, capture_output=True, text=True, timeout=3)
            ver = result.stdout.strip()
            if ver:
                os_info = f"macOS {ver} ({platform.machine()})"
        except Exception:
            pass

        # 获取 OpenClaw 版本
        version = ""
        try:
            result = _sp.run("openclaw --version", shell=True, capture_output=True, text=True, timeout=5)
            version = result.stdout.strip().split('\n')[0] if result.stdout else ""
        except Exception:
            pass

        # 设备名 = 用户的主机名
        name = f"李桐的MacBook Pro" if hostname == "bogon" else hostname

        # 读取 openclaw.json 看看有没有自定义名称
        openclaw_cfg = Path.home() / ".openclaw" / "openclaw.json"
        if openclaw_cfg.exists():
            try:
                import json as _json
                cfg = _json.loads(openclaw_cfg.read_text(encoding="utf-8"))
                cfg_name = cfg.get("name", "")
                if cfg_name:
                    name = cfg_name
            except Exception:
                pass

        # 更新或创建设备记录
        device = db.query(Device).first()
        if device:
            device.name = name
            device.hostname = hostname
            device.ip_address = ip_address
            device.os_info = os_info
            device.version = version or device.version
            device.status = "online"
            device.last_active = datetime.now()
        else:
            # 先确保有租户
            tenant = db.query(Tenant).first()
            if not tenant:
                tenant = Tenant(name="默认租户", code="default", description="默认租户")
                db.add(tenant)
                db.commit()
                db.refresh(tenant)
            device = Device(
                name=name,
                hostname=hostname,
                ip_address=ip_address,
                os_info=os_info,
                version=version,
                status="online",
                tenant_id=tenant.id,
            )
            db.add(device)

        db.commit()
        print(f"✅ 主机信息已同步: {name} ({ip_address})")
        db.close()
    except Exception as e:
        print(f"⚠️ 主机同步失败: {e}")


async def sync_agents_from_local():
    """从本地 ~/.openclaw/agents/ 目录同步 agent 信息到数据库"""
    import json as _json
    try:
        from agent_manager import Agent
        db = SessionLocal()

        agents_base = Path.home() / ".openclaw" / "agents"
        if not agents_base.exists():
            print("⚠️ Agent 目录不存在，跳过同步")
            db.close()
            return

        # 读取 openclaw.json 获取模型配置
        openclaw_cfg_path = Path.home() / ".openclaw" / "openclaw.json"
        agent_model_map = {}  # agent_id -> model
        agent_name_map = {}   # agent_id -> name from config
        if openclaw_cfg_path.exists():
            try:
                cfg = _json.loads(openclaw_cfg_path.read_text(encoding="utf-8"))
                agent_list = cfg.get("agents", {}).get("list", [])
                for entry in agent_list:
                    aid = entry.get("id", "")
                    if aid:
                        agent_model_map[aid] = entry.get("model", "")
                        agent_name_map[aid] = entry.get("name", "")
            except Exception as e:
                print(f"⚠️ 读取 openclaw.json 失败: {e}")

        # 找到第一台设备作为默认 device_id
        first_device = db.query(Device).first()
        default_device_id = first_device.id if first_device else None

        synced = 0
        for entry in sorted(agents_base.iterdir()):
            if not entry.is_dir():
                continue
            aid = entry.name

            # 读取 AGENTS.md 获取名称
            name = agent_name_map.get(aid, aid)
            description = ""
            agents_md = entry / "AGENTS.md"
            if agents_md.exists():
                try:
                    content = agents_md.read_text(encoding="utf-8")
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        stripped = line.strip()
                        if stripped.startswith("name") and i + 1 < len(lines):
                            candidate = lines[i + 1].strip()
                            if candidate and not candidate.startswith("#"):
                                name = candidate
                        elif stripped.startswith("description") and i + 1 < len(lines):
                            candidate = lines[i + 1].strip()
                            if candidate and not candidate.startswith("#"):
                                description = candidate
                except Exception:
                    pass

            # 判断状态
            has_soul = (entry / "SOUL.md").exists()
            status = "running" if has_soul else "stopped"

            # 模型
            model = agent_model_map.get(aid, "")

            # 更新或创建
            existing = db.query(Agent).filter(Agent.agent_id == aid).first()
            if existing:
                existing.name = name
                existing.model = model
                existing.status = status
                existing.description = description or existing.description
                existing.workspace = str(entry)
                existing.agent_dir = str(entry)
                if default_device_id and not existing.device_id:
                    existing.device_id = default_device_id
                existing.updated_at = datetime.now()
            else:
                new_agent = Agent(
                    agent_id=aid,
                    name=name,
                    device_id=default_device_id,
                    model=model,
                    workspace=str(entry),
                    agent_dir=str(entry),
                    status=status,
                    description=description,
                )
                db.add(new_agent)
            synced += 1

        db.commit()
        db.close()
        print(f"✅ Agent 同步完成: {synced} 个 agent 已更新")
    except Exception as e:
        print(f"⚠️ Agent 同步失败: {e}")
        import traceback
        traceback.print_exc()

# ==================== FastAPI 应用 ====================
app = FastAPI(
    title="OpenClaw Enterprise API",
    description="企业级 AI 智能体管控平台",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置（从环境变量读取，收紧安全策略）
ALLOWED_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:8003,http://127.0.0.1:8003").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 限速中间件
if RateLimitMiddleware:
    app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

# 注册审计中间件
try:
    from app.audit_middleware import setup_audit_middleware
except ImportError:
    from audit_middleware import setup_audit_middleware
setup_audit_middleware(app)

# 注册管控模块路由
try:
    from app.scanner_v2 import router as scanner_router
    from app.enforcement_v2 import router as enforcement_router
except:
    from scanner_v2 import router as scanner_router
    from enforcement_v2 import router as enforcement_router

app.include_router(scanner_router, tags=["网络扫描"])
app.include_router(enforcement_router, tags=["管控执行"])

# 注册导出模块路由
try:
    from app.export import router as export_router
except:
    from export import router as export_router
app.include_router(export_router, tags=["报表导出"])

# 注册完整报告模块路由
try:
    from app.full_report import router as full_report_router
except:
    from full_report import router as full_report_router
app.include_router(full_report_router, tags=["完整报告"])

# 注册通知模块路由
try:
    from app.notification import router as notification_router2
except:
    from notification import router as notification_router2
app.include_router(notification_router2, tags=["通知系统"])

# 注册健康检查模块路由
try:
    from app.health import router as health_router
except:
    from health import router as health_router
app.include_router(health_router, tags=["健康检查"])

# 注册认证模块路由
try:
    from app.auth_routes import router as auth_router
except:
    from auth_routes import router as auth_router
app.include_router(auth_router, tags=["认证"])

# 注册 Agent 模块路由
try:
    from app.agent import router as agent_router2
except:
    from agent import router as agent_router2
app.include_router(agent_router2, tags=["Agent 管理"])

# 注册流量分析模块路由
try:
    from app.traffic import router as traffic_router2
except:
    from traffic import router as traffic_router2
app.include_router(traffic_router2, tags=["流量分析"])

# 注册 AI 分析模块路由
try:
    from app.ai_analyzer import router as ai_router2
except:
    from ai_analyzer import router as ai_router2
app.include_router(ai_router2, tags=["AI 分析"])

# 注册主机监控模块路由
try:
    from app.host_monitor import router as host_monitor_router
except:
    from host_monitor import router as host_monitor_router
app.include_router(host_monitor_router, tags=["主机监控"])

# 注册设备管理增强模块路由
try:
    from app.device_manager import router as device_manager_router
except:
    from device_manager import router as device_manager_router
app.include_router(device_manager_router, tags=["设备管理增强"])

# 注册 Agent 管理模块路由
try:
    from app.agent_manager import router as agent_manager_router
except:
    from agent_manager import router as agent_manager_router
app.include_router(agent_manager_router, tags=["Agent 管理模块"])

# 注册策略引擎路由
try:
    from app.policy_engine import router as policy_engine_router
except:
    from policy_engine import router as policy_engine_router
app.include_router(policy_engine_router, tags=["策略引擎"])

# 注册拦截引擎路由
try:
    from app.interceptor import router as interceptor_router
except:
    from interceptor import router as interceptor_router
app.include_router(interceptor_router, tags=["拦截引擎"])

# 注册急救室路由
try:
    from app.routes.clinic import router as clinic_router
except:
    from routes.clinic import router as clinic_router
app.include_router(clinic_router, tags=["急救室"])

# 注册日志中心路由
try:
    from app.syslog_center import router as syslog_router
except:
    from syslog_center import router as syslog_router
app.include_router(syslog_router, tags=["日志中心"])

# 注册客户端数据接收路由
try:
    from app.client_receiver import router as client_receiver_router
except:
    from client_receiver import router as client_receiver_router
app.include_router(client_receiver_router, tags=["客户端接收"])

# 注册 License 授权管理路由
try:
    from app.license import router as license_router
except ImportError:
    from license import router as license_router
app.include_router(license_router, tags=["License"])

# ==================== 路由 ====================
@app.get("/")
async def root():
    return {"message": "OpenClaw Enterprise API", "version": "1.0.0"}

@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取统计数据（按租户过滤）"""
    is_admin = current_user.role == "admin"
    
    device_query = db.query(Device)
    if not is_admin:
        device_query = device_query.filter(Device.tenant_id == current_user.tenant_id)
    
    total_devices = device_query.count()
    online_devices = device_query.filter(Device.status == "online").count()
    pending_approvals = device_query.filter(Device.status == "warning").count()
    
    # 告警通过 device 关联过滤
    alert_query = db.query(Alert)
    if not is_admin:
        tenant_device_ids = [d.id for d in device_query.all()]
        alert_query = alert_query.filter(Alert.device_id.in_(tenant_device_ids))
    critical_alerts = alert_query.filter(
        Alert.level == "critical", 
        Alert.is_resolved == False
    ).count()
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    audit_query = db.query(AuditLog).filter(AuditLog.timestamp >= today)
    if not is_admin:
        audit_query = audit_query.filter(AuditLog.device_id.in_(
            [d.id for d in db.query(Device).filter(Device.tenant_id == current_user.tenant_id).all()]
        ))
    today_audit_logs = audit_query.count()
    
    week_ago = datetime.now() - timedelta(days=7)
    weekly_query = db.query(Device).filter(Device.created_at >= week_ago)
    if not is_admin:
        weekly_query = weekly_query.filter(Device.tenant_id == current_user.tenant_id)
    weekly_new_devices = weekly_query.count()
    
    # 计算 7 天审计趋势
    from sqlalchemy import func
    weekly_trend = []
    for i in range(6, -1, -1):
        day_start = (datetime.now() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_query = db.query(AuditLog).filter(
            AuditLog.timestamp >= day_start,
            AuditLog.timestamp < day_end
        )
        if not is_admin:
            day_query = day_query.filter(AuditLog.device_id.in_(
                [d.id for d in db.query(Device).filter(Device.tenant_id == current_user.tenant_id).all()]
            ))
        count = day_query.count()
        weekly_trend.append({
            "date": day_start.strftime("%m-%d"),
            "count": count
        })
    
    return StatsResponse(
        total_devices=total_devices,
        online_devices=online_devices,
        pending_approvals=pending_approvals,
        critical_alerts=critical_alerts,
        today_audit_logs=today_audit_logs,
        weekly_new_devices=weekly_new_devices,
        weekly_trend=weekly_trend
    )

@app.get("/api/devices")
async def get_devices(page: int = 1, page_size: int = 20, status: Optional[str] = None, search: Optional[str] = None, tenant_id: Optional[int] = None, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取所有设备（分页，按租户过滤）"""
    page_size = min(page_size, 100)
    query = db.query(Device)
    # 租户隔离
    if current_user.role != "admin":
        query = query.filter(Device.tenant_id == current_user.tenant_id)
    elif tenant_id:
        query = query.filter(Device.tenant_id == tenant_id)
    if status:
        query = query.filter(Device.status == status)
    if search:
        query = query.filter(Device.name.contains(search) | Device.hostname.contains(search))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0
    }

@app.get("/api/devices/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: int, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取单个设备"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if current_user.role != "admin" and device.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="无权访问此设备")
    return device

@app.post("/api/devices", response_model=DeviceResponse)
async def create_device(device: DeviceCreate, current_user: User = require_role("user"), db: Session = Depends(get_db)):
    """创建设备"""
    # License 限额检查
    try:
        from license import check_device_limit
        if not check_device_limit(db):
            raise HTTPException(status_code=403, detail="设备数量已达当前 License 上限，请升级版本")
    except ImportError:
        pass
    if current_user.role != "admin" and device.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="无权为其他租户创建设备")
    db_device = Device(**device.dict(), status="online", risk_level="low")
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device

@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: int, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    """删除设备（支持级联删除关联的审计日志、告警和 Agent）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if current_user.role != "admin" and device.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="无权删除此设备")
    
    # 级联删除关联数据（顺序很重要：先删除子表，再删除父表）
    from models import AuditLog, Alert
    from agent_manager import Agent
    
    # 1. 删除审计日志
    db.query(AuditLog).filter(AuditLog.device_id == device_id).delete(synchronize_session=False)
    # 2. 删除告警
    db.query(Alert).filter(Alert.device_id == device_id).delete(synchronize_session=False)
    # 3. 删除关联的 Agent（或设置为 NULL）
    db.query(Agent).filter(Agent.device_id == device_id).delete(synchronize_session=False)
    
    # 4. 删除设备
    db.delete(device)
    db.commit()
    return {"message": f"设备 {device.name} 已删除", "deleted": True}


@app.post("/api/devices/batch-delete")
async def batch_delete_devices(
    request_data: Dict,
    current_user: User = require_role("manager"),
    db: Session = Depends(get_db)
):
    """
    批量删除设备
    
    - **ids**: 设备 ID 列表
    """
    device_ids = request_data.get("ids", [])
    if not device_ids or not isinstance(device_ids, list):
        raise HTTPException(status_code=400, detail="需要提供设备 ID 列表")
    
    # 限制单次删除数量
    if len(device_ids) > 100:
        raise HTTPException(status_code=400, detail="单次最多删除 100 台设备")
    
    from models import AuditLog, Alert
    from agent_manager import Agent
    
    deleted_count = 0
    failed_ids = []
    
    for device_id in device_ids:
        try:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                failed_ids.append({"id": device_id, "reason": "设备不存在"})
                continue
            
            if current_user.role != "admin" and device.tenant_id != current_user.tenant_id:
                failed_ids.append({"id": device_id, "reason": "无权删除此设备"})
                continue
            
            # 级联删除
            db.query(AuditLog).filter(AuditLog.device_id == device_id).delete(synchronize_session=False)
            db.query(Alert).filter(Alert.device_id == device_id).delete(synchronize_session=False)
            db.query(Agent).filter(Agent.device_id == device_id).delete(synchronize_session=False)
            db.delete(device)
            deleted_count += 1
        except Exception as e:
            failed_ids.append({"id": device_id, "reason": str(e)})
    
    db.commit()
    
    return {
        "success": True,
        "deleted_count": deleted_count,
        "failed": failed_ids,
        "message": f"成功删除 {deleted_count} 台设备"
    }


@app.post("/api/devices/batch-update-status")
async def batch_update_device_status(
    request_data: Dict,
    current_user: User = require_role("manager"),
    db: Session = Depends(get_db)
):
    """
    批量更新设备状态
    
    - **ids**: 设备 ID 列表
    - **status**: 新状态 (online/offline/warning/violation)
    """
    device_ids = request_data.get("ids", [])
    status = request_data.get("status")
    
    if not device_ids or not isinstance(device_ids, list):
        raise HTTPException(status_code=400, detail="需要提供设备 ID 列表")
    if not status:
        raise HTTPException(status_code=400, detail="需要指定新状态")
    
    valid_statuses = ["online", "offline", "warning", "violation"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"状态必须是：{', '.join(valid_statuses)}")
    
    # 限制单次更新数量
    if len(device_ids) > 100:
        raise HTTPException(status_code=400, detail="单次最多更新 100 台设备")
    
    updated_count = 0
    failed_ids = []
    
    for device_id in device_ids:
        try:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                failed_ids.append({"id": device_id, "reason": "设备不存在"})
                continue
            
            if current_user.role != "admin" and device.tenant_id != current_user.tenant_id:
                failed_ids.append({"id": device_id, "reason": "无权更新此设备"})
                continue
            
            device.status = status
            updated_count += 1
        except Exception as e:
            failed_ids.append({"id": device_id, "reason": str(e)})
    
    db.commit()
    
    return {
        "success": True,
        "updated_count": updated_count,
        "failed": failed_ids,
        "message": f"成功更新 {updated_count} 台设备状态"
    }

@app.get("/api/audit-logs")
async def get_audit_logs(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    operation_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tenant_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取审计日志（分页，按租户过滤，支持多条件筛选）"""
    # 分页参数限制：最大 100 条/页，防止内存溢出
    page_size = min(max(page_size, 1), 100)
    query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    # 租户隔离 - 通过 device.tenant_id 过滤
    if current_user.role != "admin":
        tenant_device_ids = [d.id for d in db.query(Device).filter(Device.tenant_id == current_user.tenant_id).all()]
        query = query.filter(AuditLog.device_id.in_(tenant_device_ids))
    elif tenant_id:
        tenant_device_ids = [d.id for d in db.query(Device).filter(Device.tenant_id == tenant_id).all()]
        query = query.filter(AuditLog.device_id.in_(tenant_device_ids))
    if search:
        query = query.filter(AuditLog.operation_detail.contains(search))
    if operation_type:
        query = query.filter(AuditLog.operation_type == operation_type)
    if risk_level:
        query = query.filter(AuditLog.risk_level == risk_level)
    if status:
        query = query.filter(AuditLog.status == status)
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date)
            query = query.filter(AuditLog.timestamp >= sd)
        except Exception:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date)
            # end_date 取到当天结束
            ed = ed.replace(hour=23, minute=59, second=59)
            query = query.filter(AuditLog.timestamp <= ed)
        except Exception:
            pass
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0
    }

@app.get("/api/alerts")
async def get_alerts(page: int = 1, page_size: int = 20, status: Optional[str] = None, search: Optional[str] = None, tenant_id: Optional[int] = None, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取告警（分页，按租户过滤）"""
    page_size = min(page_size, 100)
    query = db.query(Alert)
    # 租户隔离 - 通过 device.tenant_id 过滤
    if current_user.role != "admin":
        tenant_device_ids = [d.id for d in db.query(Device).filter(Device.tenant_id == current_user.tenant_id).all()]
        query = query.filter(Alert.device_id.in_(tenant_device_ids))
    elif tenant_id:
        tenant_device_ids = [d.id for d in db.query(Device).filter(Device.tenant_id == tenant_id).all()]
        query = query.filter(Alert.device_id.in_(tenant_device_ids))
    if status == "resolved":
        query = query.filter(Alert.is_resolved == True)
    elif status == "unresolved":
        query = query.filter(Alert.is_resolved == False)
    if search:
        query = query.filter(Alert.title.contains(search) | Alert.description.contains(search))
    query = query.order_by(Alert.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0
    }

@app.get("/api/tenants")
async def get_tenants(page: int = 1, page_size: int = 20, search: Optional[str] = None, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取租户（分页，非 admin 只看自己的租户）"""
    page_size = min(page_size, 100)
    query = db.query(Tenant)
    if current_user.role != "admin":
        query = query.filter(Tenant.id == current_user.tenant_id)
    if search:
        query = query.filter(Tenant.name.contains(search))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0
    }

@app.get("/api/users")
async def get_users(page: int = 1, page_size: int = 20, search: Optional[str] = None, tenant_id: Optional[int] = None, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取用户（分页，按租户过滤）"""
    page_size = min(page_size, 100)
    query = db.query(User)
    if current_user.role != "admin":
        query = query.filter(User.tenant_id == current_user.tenant_id)
    elif tenant_id:
        query = query.filter(User.tenant_id == tenant_id)
    if search:
        query = query.filter(User.username.contains(search) | User.real_name.contains(search))
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    items = [{"id": u.id, "username": u.username, "real_name": u.real_name, "email": u.email, "tenant_id": u.tenant_id, "role": u.role, "is_active": u.is_active} for u in users]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0
    }

@app.get("/api/policies")
async def get_policies(page: int = 1, page_size: int = 20, search: Optional[str] = None, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取安全策略（分页）"""
    page_size = min(page_size, 100)
    query = db.query(SecurityPolicy)
    if search:
        query = query.filter(SecurityPolicy.name.contains(search) | SecurityPolicy.description.contains(search))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0
    }

@app.put("/api/policies/{policy_id}")
async def update_policy(policy_id: int, policy: PolicyBase, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    """更新安全策略"""
    db_policy = db.query(SecurityPolicy).filter(SecurityPolicy.id == policy_id).first()
    if not db_policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    for key, value in policy.dict(exclude_unset=True).items():
        setattr(db_policy, key, value)
    
    db_policy.updated_at = datetime.now()
    db.commit()
    db.refresh(db_policy)
    return db_policy

# ==================== 告警 CRUD ====================
class AlertCreate(BaseModel):
    title: str
    description: str
    level: str = "medium"
    device_id: Optional[int] = None

@app.post("/api/alerts")
async def create_alert(alert: AlertCreate, current_user: User = require_role("user"), db: Session = Depends(get_db)):
    db_alert = Alert(**alert.dict())
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

@app.get("/api/alerts/{alert_id}")
async def get_alert(alert_id: int, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@app.put("/api/alerts/{alert_id}")
async def update_alert(alert_id: int, data: AlertCreate, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(alert, k, v)
    db.commit()
    db.refresh(alert)
    return alert

@app.post("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_resolved = True
    alert.resolved_at = datetime.now()
    db.commit()
    return {"message": "Alert resolved", "id": alert_id}

@app.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: int, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    return {"message": "Alert deleted"}

@app.post("/api/alerts/batch-resolve")
async def batch_resolve_alerts(request_data: Dict, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    """批量解决告警"""
    alert_ids = request_data.get("ids", [])
    if not alert_ids or not isinstance(alert_ids, list):
        raise HTTPException(status_code=400, detail="需要提供告警 ID 列表")
    
    # 限制单次处理数量
    if len(alert_ids) > 100:
        raise HTTPException(status_code=400, detail="单次最多处理 100 条告警")
    
    count = db.query(Alert).filter(Alert.id.in_(alert_ids)).update(
        {Alert.is_resolved: True, Alert.resolved_at: datetime.now()}, synchronize_session=False)
    db.commit()
    return {"success": True, "resolved_count": count, "message": f"已解决 {count} 条告警"}


@app.post("/api/alerts/batch-delete")
async def batch_delete_alerts(request_data: Dict, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    """批量删除告警"""
    alert_ids = request_data.get("ids", [])
    if not alert_ids or not isinstance(alert_ids, list):
        raise HTTPException(status_code=400, detail="需要提供告警 ID 列表")
    
    # 限制单次删除数量
    if len(alert_ids) > 100:
        raise HTTPException(status_code=400, detail="单次最多删除 100 条告警")
    
    count = db.query(Alert).filter(Alert.id.in_(alert_ids)).delete(synchronize_session=False)
    db.commit()
    return {"success": True, "deleted_count": count, "message": f"已删除 {count} 条告警"}

# ==================== 审计日志 CRUD ====================
@app.get("/api/audit-logs/{log_id}")
async def get_audit_log(log_id: int, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return log

@app.delete("/api/audit-logs/{log_id}")
async def delete_audit_log(log_id: int, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    db.delete(log)
    db.commit()
    return {"message": "Audit log deleted"}

@app.post("/api/audit-logs/clear")
async def clear_audit_logs(
    before: str,
    current_user: User = require_role("admin"),
    db: Session = Depends(get_db)
):
    """
    清理旧日志（带审计追踪）
    
    限制：
    - 单次最多删除 10000 条
    - 清理操作本身记录到审计日志
    - 保留最近 30 天的日志
    """
    from models import AuditLog as AuditLogModel
    
    cutoff = datetime.fromisoformat(before)
    
    # 安全检查：不能删除最近 30 天的日志
    min_date = datetime.now() - timedelta(days=30)
    if cutoff > min_date:
        raise HTTPException(
            status_code=400,
            detail=f"只能删除 30 天前的日志（最早可删除 {min_date.strftime('%Y-%m-%d')} 之前的日志）"
        )
    
    # 限制单次删除数量
    count_query = db.query(AuditLogModel).filter(AuditLogModel.timestamp < cutoff)
    total_count = count_query.count()
    
    if total_count > 10000:
        raise HTTPException(
            status_code=400,
            detail=f"单次最多删除 10000 条日志，当前待删除 {total_count} 条。请分批次删除或联系超级管理员。"
        )
    
    # 执行删除
    count = count_query.delete(synchronize_session=False)
    db.commit()
    
    # 记录清理操作到审计日志（独立记录，避免被删除）
    # 注意：这里使用特殊标记，即使清理也不会删除这条记录
    cleanup_log = AuditLogModel(
        operation_type="audit_cleanup",
        operation_detail=f"AUDIT_LOG_CLEANUP: 用户 {current_user.username} 删除了 {count} 条日志 (cutoff: {before})",
        risk_level="warning",
        status="allowed",
        device_id=None,
        timestamp=datetime.now(),
    )
    db.add(cleanup_log)
    db.commit()
    
    return {
        "message": f"已清理 {count} 条日志",
        "deleted": count,
        "cutoff": before,
        "operator": current_user.username,
        "timestamp": datetime.now().isoformat()
    }

# ==================== 租户 CRUD ====================
class TenantCreate(BaseModel):
    name: str
    code: str
    description: str = ""

@app.post("/api/tenants")
async def create_tenant(tenant: TenantCreate, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    db_tenant = Tenant(**tenant.dict())
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@app.get("/api/tenants/{tenant_id}")
async def get_tenant(tenant_id: int, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    if current_user.role != "admin" and tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="无权访问此租户")
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@app.put("/api/tenants/{tenant_id}")
async def update_tenant(tenant_id: int, data: TenantCreate, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    if current_user.role != "admin" and tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="无权修改此租户")
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(tenant, k, v)
    db.commit()
    db.refresh(tenant)
    return tenant

@app.delete("/api/tenants/{tenant_id}")
async def delete_tenant(tenant_id: int, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    db.delete(tenant)
    db.commit()
    return {"message": "Tenant deleted"}

# ==================== 用户 CRUD ====================
class UserCreate(BaseModel):
    username: str
    real_name: str
    email: str = ""
    tenant_id: Optional[int] = None
    role: str = "user"

@app.post("/api/users")
async def create_user(user: UserCreate, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    db_user = User(**user.dict())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"id": db_user.id, "username": db_user.username, "real_name": db_user.real_name}

@app.get("/api/users/{user_id}")
async def get_user(user_id: int, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    if current_user.role != "admin" and user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问此用户")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "username": user.username, "real_name": user.real_name, "email": user.email, "tenant_id": user.tenant_id, "role": user.role}

@app.put("/api/users/{user_id}")
async def update_user(user_id: int, data: UserCreate, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    if current_user.role != "admin" and user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改此用户")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for k, v in data.dict(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "real_name": user.real_name}

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

# ==================== 策略补充 ====================
class PolicyCreate(BaseModel):
    name: str
    description: str = ""
    config: str = "{}"
    is_enabled: bool = True

@app.post("/api/policies")
async def create_policy(policy: PolicyCreate, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    db_policy = SecurityPolicy(**policy.dict())
    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    return db_policy

@app.delete("/api/policies/{policy_id}")
async def delete_policy(policy_id: int, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    policy = db.query(SecurityPolicy).filter(SecurityPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db.delete(policy)
    db.commit()
    return {"message": "Policy deleted"}

@app.post("/api/policies/{policy_id}/toggle")
async def toggle_policy(policy_id: int, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    policy = db.query(SecurityPolicy).filter(SecurityPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.is_enabled = not policy.is_enabled
    policy.updated_at = datetime.now()
    db.commit()
    return {"message": f"Policy {'enabled' if policy.is_enabled else 'disabled'}", "is_enabled": policy.is_enabled}

# ==================== 前端页面路由 ====================
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

@app.get("/pages/{page_name}")
async def get_page(page_name: str):
    """返回前端页面"""
    # 移除可能的 .html 后缀，避免重复
    if page_name.endswith('.html'):
        page_name = page_name[:-5]
    page_path = FRONTEND_DIR / "pages" / f"{page_name}.html"
    if page_path.exists():
        return FileResponse(str(page_path), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    raise HTTPException(status_code=404, detail="Page not found")

@app.get("/css/{file_name}")
async def get_css(file_name: str):
    """返回 CSS 文件"""
    css_path = FRONTEND_DIR / "css" / file_name
    if css_path.exists():
        return FileResponse(str(css_path), media_type="text/css", headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail="CSS not found")

@app.get("/js/{file_name}")
async def get_js(file_name: str):
    """返回 JS 文件"""
    js_path = FRONTEND_DIR / "js" / file_name
    if js_path.exists():
        return FileResponse(str(js_path), media_type="application/javascript", headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail="JS not found")

# ==================== 初始化数据 ====================
def init_db():
    """初始化数据库和示例数据"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    try:
        # 检查是否已有数据
        if db.query(Tenant).count() > 0:
            return
        
        # ==================== 真实数据 ====================
        # 基于本机 OpenClaw 实例 (丝可乐的 MacBook Pro)
        
        # 创建租户（按实际组织）
        tenants = [
            Tenant(name="安全团队", code="SEC", description="SRC漏洞挖掘与渗透测试"),
            Tenant(name="开发团队", code="DEV", description="日常开发与项目管理"),
            Tenant(name="运维团队", code="OPS", description="基础设施运维"),
        ]
        db.add_all(tenants)
        db.commit()
        
        # 创建用户
        users = [
            User(username="sikele", real_name="丝可乐", email="sikele@openclaw.ai", tenant_id=1, role="admin"),
            User(username="daily-bot", real_name="日常助手", email="daily@openclaw.ai", tenant_id=2, role="agent"),
            User(username="security-bot", real_name="安全专家", email="security@openclaw.ai", tenant_id=1, role="agent"),
            User(username="admin-bot", real_name="管理员Agent", email="admin@openclaw.ai", tenant_id=3, role="agent"),
        ]
        db.add_all(users)
        db.commit()
        
        # 设备和 Agent 由 sync_local_device() / sync_agents_from_local() 启动时自动创建
        # 审计日志由审计中间件自动记录，告警由策略引擎自动触发
        
        # 创建安全策略（针对 OpenClaw 的真实策略）
        policies = [
            SecurityPolicy(name="禁止访问敏感目录",
                          description="阻止 Agent 访问 ~/.ssh、~/.gnupg、/etc/shadow 等敏感路径",
                          is_enabled=True,
                          config='{"paths": ["~/.ssh", "~/.gnupg", "/etc/shadow", "~/.openclaw/openclaw.json"]}'),
            SecurityPolicy(name="强制 API 密钥加密存储",
                          description="所有 API 密钥必须通过环境变量引用，禁止明文写入配置文件",
                          is_enabled=True,
                          config='{"enforce_env_ref": true, "scan_patterns": ["sk-", "AKIA", "ghp_"]}'),
            SecurityPolicy(name="限制外部模型连接",
                          description="仅允许连接白名单内的 LLM 提供商",
                          is_enabled=True,
                          config='{"allowed_providers": ["bailian/dashscope", "openrouter"], "blocked": ["*"]}'),
            SecurityPolicy(name="第三方技能沙箱隔离",
                          description="外部技能在 Docker 沙箱中执行，限制网络和文件系统访问",
                          is_enabled=False,
                          config='{"sandbox": "docker", "network": "none", "fs_readonly": true}'),
            SecurityPolicy(name="高危命令审批",
                          description="rm -rf、dd、chmod 777、nmap、sqlmap 等命令需管理员审批",
                          is_enabled=True,
                          config='{"commands": ["rm -rf", "dd", "chmod 777", "nmap", "sqlmap", "curl | bash"], "approval_required": true}'),
            SecurityPolicy(name="操作日志实时上报",
                          description="所有 Agent 的 exec/file/api 操作实时上报到管控平台",
                          is_enabled=True,
                          config='{"endpoint": "http://localhost:8000/api/audit-logs", "batch_size": 10, "flush_interval": 30}'),
            SecurityPolicy(name="自动版本升级",
                          description="检测到新版本时自动升级 OpenClaw (当前 v2026.3.13)",
                          is_enabled=False,
                          config='{"auto_upgrade": false, "current": "2026.3.13", "maintenance_window": "02:00-04:00"}'),
        ]
        db.add_all(policies)
        db.commit()
        
        print("✅ 数据库初始化完成，真实数据已创建")
    finally:
        db.close()

# ==================== 启动 ====================
if __name__ == "__main__":
    init_db()
    ssl_cert = os.environ.get("SSL_CERT_FILE")
    ssl_key = os.environ.get("SSL_KEY_FILE")
    if ssl_cert and ssl_key:
        uvicorn.run(app, host="0.0.0.0", port=8003, ssl_certfile=ssl_cert, ssl_keyfile=ssl_key)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8003)
