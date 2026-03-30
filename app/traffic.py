"""
OpenClaw Enterprise - 流量分析模块
从审计日志和告警表统计流量数据
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import AuditLog, Alert, Device, User
from auth import get_current_user
from tenant_filter import get_tenant_filter, get_tenant_device_ids
from rbac import require_role


router = APIRouter()


# ==================== 数据统计 ====================

@router.get("/api/traffic/stats")
async def get_stats(current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取统计信息 - 从 audit_logs 表统计（按租户过滤）"""
    from agent_manager import Agent

    tenant_id = get_tenant_filter(current_user)
    device_ids = get_tenant_device_ids(db, current_user)
    
    audit_query = db.query(func.count(AuditLog.id))
    device_query = db.query(func.count(Device.id))
    
    if tenant_id is not None:
        device_query = device_query.filter(Device.tenant_id == tenant_id)
    if device_ids is not None:
        audit_query = audit_query.filter(AuditLog.device_id.in_(device_ids))

    total_packets = audit_query.scalar() or 0
    total_hosts = device_query.scalar() or 0
    total_agents = db.query(func.count(Agent.id)).scalar() or 0
    
    llm_query = db.query(func.count(AuditLog.id)).filter(AuditLog.operation_type == 'api_call')
    blocked_query = db.query(func.count(AuditLog.id)).filter(AuditLog.status == 'blocked')
    if device_ids is not None:
        llm_query = llm_query.filter(AuditLog.device_id.in_(device_ids))
        blocked_query = blocked_query.filter(AuditLog.device_id.in_(device_ids))
    
    llm_calls_detected = llm_query.scalar() or 0
    blocked = blocked_query.scalar() or 0

    return {
        "total_packets": total_packets,
        "total_hosts": total_hosts,
        "total_agents": total_agents,
        "openclaw_detected": total_hosts,
        "llm_calls_detected": llm_calls_detected,
        "blocked": blocked,
        "devices_detected": total_hosts,
    }


@router.get("/api/traffic/recent")
async def get_recent(limit: int = 20, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """返回最近的审计日志（最新 20 条，按租户过滤）"""
    device_ids = get_tenant_device_ids(db, current_user)
    
    query = db.query(AuditLog)
    if device_ids is not None:
        query = query.filter(AuditLog.device_id.in_(device_ids))
    
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "device_id": log.device_id,
            "user_id": log.user_id,
            "operation_type": log.operation_type,
            "operation_detail": log.operation_detail,
            "risk_level": log.risk_level,
            "status": log.status,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        }
        for log in logs
    ]


@router.get("/api/traffic/llm-calls")
async def get_llm_calls(limit: int = 50, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """返回 operation_type='api_call' 的日志（按租户过滤）"""
    device_ids = get_tenant_device_ids(db, current_user)
    
    query = db.query(AuditLog).filter(AuditLog.operation_type == 'api_call')
    if device_ids is not None:
        query = query.filter(AuditLog.device_id.in_(device_ids))
    
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "device_id": log.device_id,
            "user_id": log.user_id,
            "operation_type": log.operation_type,
            "operation_detail": log.operation_detail,
            "risk_level": log.risk_level,
            "status": log.status,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        }
        for log in logs
    ]


@router.get("/api/traffic/timeline")
async def get_timeline(current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """按小时统计审计日志数量（最近 24 小时，按租户过滤）"""
    now = datetime.now()
    start = now - timedelta(hours=24)

    device_ids = get_tenant_device_ids(db, current_user)
    
    query = db.query(AuditLog).filter(AuditLog.timestamp >= start)
    if device_ids is not None:
        query = query.filter(AuditLog.device_id.in_(device_ids))
    
    logs = query.all()

    # 按小时聚合
    hourly: dict[str, int] = {}
    for h in range(24):
        hour_start = start + timedelta(hours=h)
        key = hour_start.strftime("%H:00")
        hourly[key] = 0

    for log in logs:
        if log.timestamp:
            key = log.timestamp.strftime("%H:00")
            if key in hourly:
                hourly[key] += 1

    return [{"hour": k, "count": v} for k, v in hourly.items()]


# ==================== 保留的原有路由 ====================

@router.get("/api/traffic/flows")
async def get_flows(limit: int = 100, openclaw_only: bool = False,
                    llm_only: bool = False, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取流量记录 - 从审计日志读取（按租户过滤）"""
    device_ids = get_tenant_device_ids(db, current_user)
    
    query = db.query(AuditLog)
    if device_ids is not None:
        query = query.filter(AuditLog.device_id.in_(device_ids))
    if llm_only:
        query = query.filter(AuditLog.operation_type == 'api_call')
    if openclaw_only:
        query = query.filter(AuditLog.operation_type.in_(['api_call', 'skill_exec', 'agent_action']))
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "src_ip": "",
            "src_port": 0,
            "dst_ip": "",
            "dst_port": 0,
            "protocol": "HTTPS" if log.operation_type == 'api_call' else "HTTP",
            "payload_size": 0,
            "payload_sample": log.operation_detail or "",
            "is_openclaw": True,
            "is_llm_call": log.operation_type == 'api_call',
            "device_id": log.device_id,
            "operation_type": log.operation_type,
            "risk_level": log.risk_level,
            "status": log.status,
        }
        for log in logs
    ]


@router.get("/api/traffic/devices")
async def get_detected_devices(current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取检测到的设备 - 从 devices 表读取（按租户过滤）"""
    tenant_id = get_tenant_filter(current_user)
    query = db.query(Device)
    if tenant_id is not None:
        query = query.filter(Device.tenant_id == tenant_id)
    devices = query.all()
    return [
        {
            "ip": d.ip_address or "",
            "hostname": d.hostname or d.name or "",
            "name": d.name or "",
            "status": d.status or "offline",
            "risk_level": d.risk_level or "low",
            "version": d.version or "",
            "openclaw_calls": db.query(func.count(AuditLog.id)).filter(
                AuditLog.device_id == d.id
            ).scalar() or 0,
        }
        for d in devices
    ]


@router.get("/api/traffic/alerts")
async def get_alerts(limit: int = 100, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取告警列表 - 从 alerts 表读取（按租户过滤）"""
    device_ids = get_tenant_device_ids(db, current_user)
    
    query = db.query(Alert)
    if device_ids is not None:
        query = query.filter(Alert.device_id.in_(device_ids))
    
    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    return [
        {
            "id": a.id,
            "title": a.title or "",
            "description": a.description or "",
            "level": a.level or "info",
            "device_id": a.device_id,
            "is_resolved": a.is_resolved,
            "timestamp": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


class URLRequest(BaseModel):
    url: str
    src_ip: Optional[str] = None


# LLM API 域名特征（保留用于 URL 检测）
LLM_SIGNATURES = {
    'api.openai.com': 'OpenAI',
    'api.anthropic.com': 'Anthropic',
    'api.cohere.com': 'Cohere',
    'api.deepseek.com': 'DeepSeek',
    'bailian.aliyuncs.com': '阿里云百炼',
    'dashscope.aliyuncs.com': '阿里云通义',
    'api.qwen.ai': '通义千问',
    'api.glm.cn': '智谱 AI',
    'api.chatglm.cn': '智谱 GLM',
    'api.minimax.chat': 'MiniMax',
    'api.moonshot.cn': '月之暗面',
}


@router.post("/api/traffic/check")
async def check_traffic(request: URLRequest):
    """检查 URL 是否是 LLM 调用"""
    result = {
        'is_llm_call': False,
        'provider': None,
        'risk_level': 'low',
        'details': {}
    }

    url_lower = request.url.lower()
    for sig, provider in LLM_SIGNATURES.items():
        if sig in url_lower:
            result['is_llm_call'] = True
            result['provider'] = provider
            if provider in ['OpenAI', 'Anthropic']:
                result['risk_level'] = 'high'
                result['details']['reason'] = '未授权的外部 LLM'
            else:
                result['risk_level'] = 'medium'
                result['details']['reason'] = '外部 LLM 调用'
            break

    return result


@router.get("/api/traffic/sniffer/status")
async def get_sniffer_status():
    """获取嗅探状态（已弃用，保留接口兼容）"""
    return {
        "running": False,
        "interface": None,
        "detected_count": 0,
        "message": "嗅探功能已替换为审计日志分析"
    }


@router.post("/api/traffic/sniffer/start")
async def start_sniffer(interface: Optional[str] = None):
    """启动嗅探（已弃用，保留接口兼容）"""
    raise HTTPException(status_code=400, detail="嗅探功能已替换为审计日志分析，无需手动启动")


@router.post("/api/traffic/sniffer/stop")
async def stop_sniffer():
    """停止嗅探（已弃用，保留接口兼容）"""
    return {"success": True, "message": "嗅探功能已替换为审计日志分析"}


@router.post("/api/traffic/clear")
async def clear_data():
    """清空流量数据（已弃用，保留接口兼容）"""
    return {"success": True, "message": "请通过审计日志管理页面操作"}
