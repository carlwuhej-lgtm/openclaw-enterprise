"""
OpenClaw Enterprise - Agent 管理模块
管理 OpenClaw 智能体（Agent）的 CRUD、生命周期和批量操作
"""
import json
import math
import subprocess
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Session

# 导入数据库基础设施
from database import Base, engine, SessionLocal, get_db

# 导入认证和权限模块
from auth import get_current_user
from models import User, Device
from tenant_filter import get_tenant_filter
from rbac import require_role


# ==================== 数据库模型 ====================

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(50), index=True)            # openclaw agent id，如 "daily", "security"
    name = Column(String(100))                            # 显示名称
    device_id = Column(Integer, ForeignKey("devices.id")) # 关联设备
    model = Column(String(100))                           # 使用的模型，如 "bailian/glm-5"
    workspace = Column(String(500))                       # 工作目录
    agent_dir = Column(String(500))                       # agent 配置目录
    status = Column(String(20), default="unknown")        # running, stopped, error, unknown
    description = Column(String(500))
    channels = Column(Text)                               # JSON: 关联的通信渠道
    last_heartbeat = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# 创建表
Base.metadata.create_all(bind=engine)


# ==================== Pydantic 模型 ====================

class AgentCreate(BaseModel):
    agent_id: str = Field(..., max_length=50, description="Agent ID，如 daily, security")
    name: str = Field(..., max_length=100, description="显示名称")
    device_id: Optional[int] = Field(None, description="关联设备 ID")
    model: Optional[str] = Field(None, max_length=100, description="使用的模型")
    workspace: Optional[str] = Field(None, max_length=500, description="工作目录")
    agent_dir: Optional[str] = Field(None, max_length=500, description="Agent 配置目录")
    status: Optional[str] = Field("unknown", max_length=20, description="状态")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    channels: Optional[str] = Field(None, description="关联通信渠道 (JSON)")


class AgentUpdate(BaseModel):
    agent_id: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=100)
    device_id: Optional[int] = None
    model: Optional[str] = Field(None, max_length=100)
    workspace: Optional[str] = Field(None, max_length=500)
    agent_dir: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = Field(None, max_length=500)
    channels: Optional[str] = None


class AgentResponse(BaseModel):
    id: int
    agent_id: str
    name: str
    device_id: Optional[int] = None
    model: Optional[str] = None
    workspace: Optional[str] = None
    agent_dir: Optional[str] = None
    status: str
    description: Optional[str] = None
    channels: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AgentListResponse(BaseModel):
    items: List[AgentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== API 路由 ====================

router = APIRouter()


# ---------- CRUD ----------

@router.get("/api/agents", response_model=AgentListResponse)
async def list_agents(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=1000, description="每页数量"),
    device_id: Optional[int] = Query(None, description="按设备 ID 过滤"),
    current_user: User = require_role("viewer"),
    db: Session = Depends(get_db),
):
    """获取 Agent 列表（分页 + 设备过滤 + 租户隔离）"""
    import os
    
    query = db.query(Agent)
    
    # 租户隔离：通过 device.tenant_id 过滤
    tenant_id = get_tenant_filter(current_user)
    if tenant_id is not None:
        tenant_device_ids = [d.id for d in db.query(Device.id).filter(Device.tenant_id == tenant_id).all()]
        query = query.filter(Agent.device_id.in_(tenant_device_ids))
    
    if device_id is not None:
        query = query.filter(Agent.device_id == device_id)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    items = query.order_by(Agent.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # 实时检测 Agent 状态
    from datetime import timedelta
    now = datetime.now()
    for agent in items:
        # 远端 agent（有 last_heartbeat 的）：根据心跳判断状态
        if agent.last_heartbeat:
            if now - agent.last_heartbeat < timedelta(minutes=5):
                agent.status = "running"
            else:
                agent.status = "offline"
            continue

        # 本地 agent：检查 workspace 是否存在
        workspace_exists = os.path.isdir(agent.workspace) if agent.workspace else False
        
        # 检查是否有 SOUL.md（有效 Agent 的标志）
        soul_exists = os.path.isfile(os.path.join(agent.agent_dir or agent.workspace or '', 'SOUL.md')) if (agent.agent_dir or agent.workspace) else False
        
        # 根据 workspace 和 SOUL.md 判断状态
        if workspace_exists and soul_exists:
            agent.status = "running"
        elif workspace_exists:
            agent.status = "stopped"
        else:
            agent.status = "error"

    return AgentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/api/agents", response_model=AgentResponse, status_code=201)
async def create_agent(agent_in: AgentCreate, current_user: User = require_role("user"), db: Session = Depends(get_db)):
    """创建 Agent"""
    # License 限额检查
    try:
        from app.license import check_agent_limit
        if not check_agent_limit(db):
            # 获取当前 License 信息
            from app.license import get_current_plan
            plan = get_current_plan()
            raise HTTPException(
                status_code=403, 
                detail=f"Agent 数量已达当前 License 上限（{plan.max_agents}个），请升级版本",
                headers={"X-License-Plan": plan.plan, "X-License-Max-Agents": str(plan.max_agents)}
            )
    except ImportError as e:
        print(f"⚠️ License 检查导入失败：{e}")
        pass  # 如果 License 模块不可用，跳过检查
    
    db_agent = Agent(**agent_in.model_dump())
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent


@router.get("/api/agents/{agent_id_int}", response_model=AgentResponse)
async def get_agent(agent_id_int: int, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取 Agent 详情"""
    agent = db.query(Agent).filter(Agent.id == agent_id_int).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/api/agents/{agent_id_int}", response_model=AgentResponse)
async def update_agent(agent_id_int: int, agent_in: AgentUpdate, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    """更新 Agent"""
    agent = db.query(Agent).filter(Agent.id == agent_id_int).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = agent_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)
    agent.updated_at = datetime.now()

    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/api/agents/{agent_id_int}")
async def delete_agent(agent_id_int: int, current_user: User = require_role("admin"), db: Session = Depends(get_db)):
    """删除 Agent"""
    agent = db.query(Agent).filter(Agent.id == agent_id_int).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"message": "Agent deleted", "id": agent_id_int}


# ---------- Agent 操作 ----------

@router.post("/api/agents/{agent_id_int}/start")
async def start_agent(agent_id_int: int, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    """启动 Agent"""
    agent = db.query(Agent).filter(Agent.id == agent_id_int).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 尝试通过 openclaw 命令启动
    try:
        result = subprocess.run(
            ["openclaw", "agent", "start", agent.agent_id],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            agent.status = "running"
            agent.last_heartbeat = datetime.now()
            agent.updated_at = datetime.now()
            db.commit()
            return {"success": True, "message": f"Agent '{agent.agent_id}' 已启动", "output": result.stdout.strip()}
        else:
            agent.status = "error"
            agent.updated_at = datetime.now()
            db.commit()
            return {"success": False, "message": f"启动失败: {result.stderr.strip()}"}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="openclaw 命令未找到")
    except subprocess.TimeoutExpired:
        agent.status = "running"  # 超时通常意味着 agent 正在运行
        agent.last_heartbeat = datetime.now()
        agent.updated_at = datetime.now()
        db.commit()
        return {"success": True, "message": f"Agent '{agent.agent_id}' 启动中（进程未在超时内退出，可能已正常运行）"}


@router.post("/api/agents/{agent_id_int}/stop")
async def stop_agent(agent_id_int: int, current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    """停止 Agent"""
    agent = db.query(Agent).filter(Agent.id == agent_id_int).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = subprocess.run(
            ["openclaw", "agent", "stop", agent.agent_id],
            capture_output=True, text=True, timeout=15,
        )
        agent.status = "stopped"
        agent.updated_at = datetime.now()
        db.commit()
        return {"success": True, "message": f"Agent '{agent.agent_id}' 已停止", "output": result.stdout.strip()}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="openclaw 命令未找到")
    except subprocess.TimeoutExpired:
        agent.status = "stopped"
        agent.updated_at = datetime.now()
        db.commit()
        return {"success": True, "message": f"Agent '{agent.agent_id}' 停止命令已发送"}


@router.get("/api/agents/{agent_id_int}/heartbeat")
async def get_heartbeat(agent_id_int: int, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取 Agent 心跳状态"""
    agent = db.query(Agent).filter(Agent.id == agent_id_int).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {
        "id": agent.id,
        "agent_id": agent.agent_id,
        "status": agent.status,
        "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
    }


# ---------- 批量操作 ----------

@router.post("/api/agents/batch")
async def batch_import_agents(
    device_id: int = Query(..., description="设备 ID"),
    db: Session = Depends(get_db),
):
    """批量导入 Agent — 从设备的 openclaw 配置自动发现并导入所有 agent"""
    from pathlib import Path
    import os

    # 读取 openclaw 配置，发现所有 agent
    openclaw_dir = Path.home() / ".openclaw"
    agents_dir = openclaw_dir / "agents"

    if not agents_dir.exists():
        raise HTTPException(status_code=400, detail=f"未找到 agents 目录: {agents_dir}")

    imported: list[dict] = []
    skipped: list[dict] = []

    for entry in sorted(agents_dir.iterdir()):
        if not entry.is_dir():
            continue

        aid = entry.name  # e.g. "daily", "security"

        # 跳过已存在的
        existing = db.query(Agent).filter(Agent.agent_id == aid, Agent.device_id == device_id).first()
        if existing:
            skipped.append({"agent_id": aid, "reason": "already exists"})
            continue

        # 读取 AGENTS.md 获取名称和描述
        agents_md = entry / "AGENTS.md"
        name = aid
        description = ""
        if agents_md.exists():
            try:
                content = agents_md.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line_stripped = line.strip()
                    if line_stripped.startswith("name"):
                        # 尝试获取下一行作为 name
                        idx = content.splitlines().index(line)
                        if idx + 1 < len(content.splitlines()):
                            candidate = content.splitlines()[idx + 1].strip()
                            if candidate and not candidate.startswith("#"):
                                name = candidate
                    elif line_stripped.startswith("description"):
                        idx = content.splitlines().index(line)
                        if idx + 1 < len(content.splitlines()):
                            candidate = content.splitlines()[idx + 1].strip()
                            if candidate and not candidate.startswith("#"):
                                description = candidate
            except Exception:
                pass

        # 读取模型配置
        model = ""
        tools_md = entry / "TOOLS.md"
        if tools_md.exists():
            try:
                content = tools_md.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if "默认模型" in line or "default_model" in line.lower():
                        parts = line.split(":")
                        if len(parts) >= 2:
                            model = parts[-1].strip().strip("`")
                            break
            except Exception:
                pass

        # 读取渠道配置
        channels = ""
        soul_md = entry / "SOUL.md"
        # 简单检查是否有飞书/telegram/discord 相关配置
        channel_list = []
        for md_file in [soul_md, tools_md]:
            if md_file.exists():
                try:
                    content = md_file.read_text(encoding="utf-8").lower()
                    for ch in ["feishu", "telegram", "discord", "webchat", "slack"]:
                        if ch in content and ch not in channel_list:
                            channel_list.append(ch)
                except Exception:
                    pass
        if channel_list:
            channels = json.dumps(channel_list)

        workspace = str(entry)
        agent_dir_path = str(entry)

        db_agent = Agent(
            agent_id=aid,
            name=name,
            device_id=device_id,
            model=model,
            workspace=workspace,
            agent_dir=agent_dir_path,
            status="unknown",
            description=description,
            channels=channels,
        )
        db.add(db_agent)
        imported.append({"agent_id": aid, "name": name})

    db.commit()

    return {
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "total_imported": len(imported),
        "total_skipped": len(skipped),
    }
