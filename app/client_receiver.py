"""
OpenClaw Enterprise - 客户端数据接收模块
接收 Agent 客户端上报的监控数据，写入数据库。
使用 API Key 认证，与用户 JWT 认证分离。
"""
import json
import os
from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Depends, Header, status
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import Device, AuditLog, Alert

# 客户端 API Key 认证
CLIENT_API_KEY = os.environ.get("OCW_CLIENT_API_KEY", "ocw-client-default-key")

async def verify_client_api_key(x_api_key: Optional[str] = Header(None)):
    """验证客户端 API Key（用于 /api/client/* 端点）"""
    if CLIENT_API_KEY == "ocw-client-default-key":
        # 开发模式：允许无 key 或默认 key
        return True
    if not x_api_key or x_api_key != CLIENT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key"
        )
    return True


router = APIRouter(tags=["客户端接收"])


# ==================== 数据模型 ====================

class ProcessInfo(BaseModel):
    pid: int = 0
    name: str = ""
    cmdline: str = ""
    cpu: float = 0.0
    memory: float = 0.0
    is_agent: bool = False


class ConnectionInfo(BaseModel):
    pid: int = 0
    local_addr: str = ""
    remote_addr: str = ""
    status: str = ""
    is_llm_call: bool = False
    provider: str = ""


class FileEvent(BaseModel):
    path: str = ""
    operation: str = ""  # read/write/delete
    timestamp: str = ""
    process_id: int = 0


class SystemInfo(BaseModel):
    os: str = ""
    arch: str = ""
    hostname: str = ""
    ip: str = ""
    cpu_usage: float = 0.0
    mem_total: int = 0
    mem_used: int = 0


class ClientReport(BaseModel):
    """客户端上报数据 - 所有字段可选，容错处理"""
    agent_id: str = ""
    hostname: str = ""
    os: str = ""
    timestamp: str = ""
    processes: List[ProcessInfo] = []
    connections: List[ConnectionInfo] = []
    file_events: List[FileEvent] = []
    system_info: Optional[SystemInfo] = None
    
    class Config:
        extra = "ignore"  # 忽略未知字段


class HeartbeatRequest(BaseModel):
    """心跳请求"""
    agent_id: str
    hostname: str = ""
    ip: str = ""
    os: str = ""
    version: str = ""


# ==================== 接收上报 ====================

@router.post("/api/client/report")
async def receive_report(report: ClientReport, verified: bool = Depends(verify_client_api_key), db: Session = Depends(get_db)):
    """
    接收客户端上报的监控数据。
    1. 更新/创建设备记录
    2. AI Agent 进程写入审计日志
    3. LLM 连接写入审计日志
    4. 敏感文件事件写入审计日志 + 触发策略检查
    """
    now = datetime.now()

    # 1. 更新/创建设备
    device = db.query(Device).filter(Device.hostname == report.hostname).first()
    ip = report.system_info.ip if report.system_info else ""

    if not device:
        device = Device(
            name=report.hostname,
            hostname=report.hostname,
            ip_address=ip,
            os_info=report.os,
            version="agent-client",
            status="online",
            risk_level="low",
            risk_score=0,
            last_active=now,
            created_at=now,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
    else:
        device.last_active = now
        device.status = "online"
        if ip:
            device.ip_address = ip
        if report.os:
            device.os_info = report.os
        db.commit()

    device_id = device.id

    # 2. AI Agent 进程 → 审计日志 + 自动注册到 agents 表
    from agent_manager import Agent
    agent_procs = [p for p in report.processes if p.is_agent]
    for proc in agent_procs:
        log = AuditLog(
            device_id=device_id,
            operation_type="process_detected",
            operation_detail=f"AI Agent 进程: PID {proc.pid} {proc.name} | {proc.cmdline[:200]}",
            risk_level="safe",
            status="allowed",
            timestamp=now,
        )
        db.add(log)

        # 自动注册/更新 agent 到 agents 表
        agent_name = proc.name
        # 尝试从 cmdline 提取 agent id (如 .openclaw/agents/daily → daily)
        import re as _re
        agent_id_match = _re.search(r'\.openclaw/agents/(\w+)', proc.cmdline)
        agent_id = agent_id_match.group(1) if agent_id_match else agent_name

        existing_agent = db.query(Agent).filter(
            Agent.agent_id == agent_id,
            Agent.device_id == device_id
        ).first()
        if existing_agent:
            existing_agent.status = "running"
            existing_agent.last_heartbeat = now
        else:
            new_agent = Agent(
                agent_id=agent_id,
                name=agent_name,
                device_id=device_id,
                status="running",
                last_heartbeat=now,
            )
            db.add(new_agent)

    # 3. LLM 连接 → 审计日志
    llm_conns = [c for c in report.connections if c.is_llm_call]
    for conn in llm_conns:
        log = AuditLog(
            device_id=device_id,
            operation_type="llm_call",
            operation_detail=f"LLM API 调用: {conn.provider} | {conn.remote_addr} (PID {conn.pid})",
            risk_level="warning",
            status="allowed",
            timestamp=now,
        )
        db.add(log)

    # 4. 敏感文件事件 → 审计日志 + 策略检查
    for event in report.file_events:
        # 策略检查
        risk = "warning"
        status = "allowed"
        sensitive_paths = ["/.ssh", "/.gnupg", "/.aws", "/etc/shadow", "/etc/passwd", "credentials", ".env"]
        for sp in sensitive_paths:
            if sp in event.path:
                risk = "danger"
                status = "blocked"
                # 生成告警
                alert = Alert(
                    title=f"敏感文件访问: {event.path}",
                    description=f"设备 [{report.hostname}] 的进程(PID {event.process_id}) 访问了敏感文件: {event.path}",
                    level="high",
                    device_id=device_id,
                    is_resolved=False,
                    created_at=now,
                )
                db.add(alert)
                break

        log = AuditLog(
            device_id=device_id,
            operation_type=f"file_{event.operation}",
            operation_detail=f"文件{event.operation}: {event.path}",
            risk_level=risk,
            status=status,
            timestamp=now,
        )
        db.add(log)

    db.commit()

    return {
        "success": True,
        "device_id": device_id,
        "processed": {
            "processes": len(agent_procs),
            "llm_calls": len(llm_conns),
            "file_events": len(report.file_events),
        },
        "message": "数据已接收",
    }


# ==================== 心跳 ====================

@router.post("/api/client/heartbeat")
async def heartbeat(req: HeartbeatRequest, verified: bool = Depends(verify_client_api_key), db: Session = Depends(get_db)):
    """客户端心跳，更新设备在线状态"""
    now = datetime.now()

    device = db.query(Device).filter(Device.hostname == req.hostname).first()
    if device:
        device.last_active = now
        device.status = "online"
        if req.ip:
            device.ip_address = req.ip
        if req.version:
            device.version = req.version
        db.commit()
        return {"success": True, "device_id": device.id, "message": "heartbeat ok"}
    else:
        # 新设备自动注册
        device = Device(
            name=req.hostname,
            hostname=req.hostname,
            ip_address=req.ip,
            os_info=req.os,
            version=req.version or "agent-client",
            status="online",
            risk_level="low",
            risk_score=0,
            last_active=now,
            created_at=now,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return {"success": True, "device_id": device.id, "message": "registered and heartbeat ok"}


# ==================== 客户端拉取策略 ====================

@router.get("/api/client/policies")
async def get_client_policies(db: Session = Depends(get_db)):
    """客户端拉取策略列表"""
    from models import SecurityPolicy
    policies = db.query(SecurityPolicy).filter(SecurityPolicy.is_enabled == True).all()
    result = []
    for p in policies:
        try:
            config = json.loads(p.config) if p.config else {}
        except:
            config = {}
        result.append({
            "id": p.id,
            "name": p.name,
            "config": config,
        })
    return result
