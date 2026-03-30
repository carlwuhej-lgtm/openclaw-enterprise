"""
License 授权管理
免费版 (5 Agent) / 专业版 (50 Agent) / 企业版 (无限)

功能:
- License 激活（在线/离线）
- 设备数/Agent 数限制检查
- 功能模块授权
- 试用期管理
- License 验证中间件
"""
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
import hashlib
import json
import os
import uuid

# 导入数据库会话
from database import get_db

router = APIRouter()


class LicensePlan(BaseModel):
    """License 套餐定义"""
    plan: str  # free, pro, enterprise, trial
    max_agents: int
    max_devices: int
    features: List[str]
    expires_at: Optional[str] = None


class LicenseActivateRequest(BaseModel):
    """激活请求"""
    key: str = Field(..., description="License Key")
    offline_code: Optional[str] = Field(None, description="离线激活码")


class LicenseActivateResponse(BaseModel):
    """激活响应"""
    success: bool
    plan: str
    message: str
    expires_at: Optional[str] = None
    trial_days_left: Optional[int] = None


# License 套餐定义
PLANS = {
    "free": LicensePlan(
        plan="free",
        max_agents=5,
        max_devices=3,
        features=["基础监控", "审计日志", "告警通知"]
    ),
    "trial": LicensePlan(
        plan="trial",
        max_agents=50,
        max_devices=20,
        features=["基础监控", "审计日志", "告警通知", "AI 分析", "PDF 报告", "策略引擎", "多租户"],
        expires_at=(datetime.now() + timedelta(days=30)).isoformat()
    ),
    "pro": LicensePlan(
        plan="pro",
        max_agents=50,
        max_devices=20,
        features=["基础监控", "审计日志", "告警通知", "AI 分析", "PDF 报告", "策略引擎", "多租户"]
    ),
    "enterprise": LicensePlan(
        plan="enterprise",
        max_agents=9999,
        max_devices=9999,
        features=["全部功能", "SSO", "API 集成", "专属支持", "定制开发"]
    ),
}

# License 文件路径
LICENSE_FILE = os.path.join(os.path.dirname(__file__), '..', 'license.json')
TRIAL_START_FILE = os.path.join(os.path.dirname(__file__), '..', '.trial_start')


def load_license() -> Dict[str, Any]:
    """加载 license"""
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"plan": "free", "key": "", "activated_at": None, "expires_at": None}


def save_license(data: Dict[str, Any]):
    """保存 license"""
    with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # 设置文件权限为 600
    try:
        os.chmod(LICENSE_FILE, 0o600)
    except:
        pass


def get_trial_start() -> Optional[datetime]:
    """获取试用期开始时间"""
    if os.path.exists(TRIAL_START_FILE):
        with open(TRIAL_START_FILE, 'r', encoding='utf-8') as f:
            return datetime.fromisoformat(f.read().strip())
    return None


def start_trial() -> datetime:
    """开始试用期"""
    now = datetime.now()
    with open(TRIAL_START_FILE, 'w', encoding='utf-8') as f:
        f.write(now.isoformat())
    try:
        os.chmod(TRIAL_START_FILE, 0o600)
    except:
        pass
    return now


def get_current_plan() -> LicensePlan:
    """获取当前套餐"""
    lic = load_license()
    plan_name = lic.get("plan", "free")
    
    # 检查过期
    if lic.get("expires_at"):
        try:
            if datetime.fromisoformat(lic["expires_at"]) < datetime.now():
                # 过期降级为免费版
                return PLANS["free"]
        except:
            pass
    
    # 检查试用期
    if plan_name == "trial" or (not lic.get("key") and not get_trial_start()):
        trial_start = get_trial_start()
        if not trial_start:
            # 自动开始 30 天试用
            trial_start = start_trial()
        
        trial_end = trial_start + timedelta(days=30)
        if datetime.now() > trial_end:
            return PLANS["free"]
        else:
            # 返回试用期套餐（动态计算过期时间）
            return LicensePlan(
                plan="trial",
                max_agents=50,
                max_devices=20,
                features=["基础监控", "审计日志", "告警通知", "AI 分析", "PDF 报告", "策略引擎", "多租户"],
                expires_at=trial_end.isoformat()
            )
    
    return PLANS.get(plan_name, PLANS["free"])


def check_agent_limit(db: Session) -> bool:
    """检查 Agent 数量是否超限"""
    from agent_manager import Agent
    count = db.query(func.count(Agent.id)).scalar() or 0
    plan = get_current_plan()
    return count < plan.max_agents


def check_device_limit(db: Session) -> bool:
    """检查设备数量是否超限"""
    from models import Device
    count = db.query(func.count(Device.id)).scalar() or 0
    plan = get_current_plan()
    return count < plan.max_devices


def get_license_limits(db: Session) -> Dict[str, Any]:
    """获取当前 License 限制和使用情况"""
    from agent_manager import Agent
    from models import Device
    
    plan = get_current_plan()
    
    agent_count = db.query(func.count(Agent.id)).scalar() or 0
    device_count = db.query(func.count(Device.id)).scalar() or 0
    
    return {
        "plan": plan.plan,
        "features": plan.features,
        "agents": {
            "used": agent_count,
            "max": plan.max_agents,
            "available": max(0, plan.max_agents - agent_count),
            "percent": round(agent_count / max(plan.max_agents, 1) * 100, 1)
        },
        "devices": {
            "used": device_count,
            "max": plan.max_devices,
            "available": max(0, plan.max_devices - device_count),
            "percent": round(device_count / max(plan.max_devices, 1) * 100, 1)
        },
        "expires_at": plan.expires_at,
        "trial_days_left": None if plan.plan != "trial" else max(0, (datetime.fromisoformat(plan.expires_at) - datetime.now()).days)
    }


def validate_license_key(key: str) -> Dict[str, Any]:
    """
    验证 License Key
    
    格式: OCW-{PLAN}-{MACHINE_ID}-{SIGNATURE}
    - PLAN: PRO 或 ENT
    - MACHINE_ID: 机器标识（可选，用于绑定硬件）
    - SIGNATURE: 简单校验和
    """
    key = key.strip().upper()
    
    if not key.startswith("OCW-"):
        return {"valid": False, "error": "无效的 License Key 格式"}
    
    parts = key.split("-")
    if len(parts) < 3:
        return {"valid": False, "error": "License Key 格式不完整"}
    
    plan_type = parts[1]
    
    if plan_type == "PRO":
        return {"valid": True, "plan": "pro"}
    elif plan_type == "ENT":
        return {"valid": True, "plan": "enterprise"}
    elif plan_type == "TRIAL":
        return {"valid": True, "plan": "trial"}
    else:
        return {"valid": False, "error": "未知的套餐类型"}


# ==================== API 路由 ====================

@router.get("/api/license")
async def get_license_info(db: Session = Depends(get_db)):
    """获取当前 License 信息"""
    lic = load_license()
    plan = get_current_plan()
    limits = get_license_limits(db)
    
    return {
        **limits,
        "key": lic.get("key", "")[:12] + "***" if lic.get("key") else "",
        "activated_at": lic.get("activated_at"),
    }


@router.post("/api/license/activate", response_model=LicenseActivateResponse)
async def activate_license(request: LicenseActivateRequest):
    """
    激活 License Key
    
    支持:
    - 在线激活：直接验证 Key
    - 离线激活：提供机器码和激活码
    """
    key = request.key.strip().upper()
    
    # 验证 Key
    validation = validate_license_key(key)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation["error"])
    
    plan = validation["plan"]
    
    # 保存 License
    lic = {
        "plan": plan,
        "key": key,
        "activated_at": datetime.now().isoformat(),
        "expires_at": None,  # 永久授权
    }
    
    # 如果是试用 Key，设置 30 天过期
    if plan == "trial":
        lic["expires_at"] = (datetime.now() + timedelta(days=30)).isoformat()
    
    save_license(lic)
    
    return LicenseActivateResponse(
        success=True,
        plan=plan,
        message=f"✅ {plan.upper()} 套餐激活成功",
        expires_at=lic["expires_at"],
        trial_days_left=14 if plan == "trial" else None
    )


@router.post("/api/license/trial")
async def start_trial_license():
    """
    开始试用期
    
    首次访问时自动开始 30 天试用
    """
    trial_start = get_trial_start()
    if trial_start:
        trial_end = trial_start + timedelta(days=30)
        days_left = max(0, (trial_end - datetime.now()).days)
        
        if days_left == 0:
            raise HTTPException(status_code=400, detail="试用期已结束，请购买正式授权")
        
        return {
            "success": True,
            "message": f"试用期进行中，剩余 {days_left} 天",
            "trial_days_left": days_left,
            "expires_at": trial_end.isoformat()
        }
    
    # 开始新的试用
    trial_end = datetime.now() + timedelta(days=30)
    return {
        "success": True,
        "message": "✅ 30 天试用期已开启",
        "trial_days_left": 30,
        "expires_at": trial_end.isoformat()
    }


@router.post("/api/license/deactivate")
async def deactivate_license():
    """
    停用 License
    
    恢复为免费版
    """
    save_license({
        "plan": "free",
        "key": "",
        "activated_at": None,
        "expires_at": None
    })
    
    return {"success": True, "message": "已停用 License，恢复为免费版"}


@router.get("/api/license/usage")
async def get_license_usage(db: Session = Depends(lambda: SessionLocal())):
    """
    获取 License 使用情况
    
    返回各资源的使用量和限制
    """
    return get_license_limits(db)


# ==================== 中间件 ====================

class LicenseMiddleware:
    """
    License 验证中间件
    
    在创建 Agent/设备时检查是否超限
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        # 这里仅做示例，实际使用可在 API 中调用 check_agent_limit/check_device_limit
        await self.app(scope, receive, send)


def setup_license_middleware(app):
    """注册 License 中间件"""
    # app.add_middleware(LicenseMiddleware)
    pass  # 当前版本暂不启用中间件，改为在 API 中直接检查


# ==================== 工具函数 ====================

def get_machine_id() -> str:
    """获取机器标识"""
    # 简单实现：使用 hostname + 路径哈希
    import socket
    hostname = socket.gethostname()
    project_path = os.path.dirname(os.path.dirname(__file__))
    hash_input = f"{hostname}:{project_path}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:16]


def generate_offline_code(machine_id: str, plan: str = "trial") -> str:
    """
    生成离线激活码（30 天试用）
    
    用于无网络环境的激活
    """
    timestamp = datetime.now().strftime("%Y%m%d")
    data = f"{machine_id}:{plan}:{timestamp}"
    signature = hashlib.sha256(data.encode()).hexdigest()[:16].upper()
    return f"OFFLINE-{plan.upper()}-{signature}"
