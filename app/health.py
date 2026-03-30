"""
OpenClaw Enterprise - 健康检查模块
提供系统健康状态、依赖检查、性能指标
"""
import os
import time
import psutil
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from database import engine, SessionLocal
from models import Device, Alert, AuditLog


router = APIRouter()


class HealthCheck(BaseModel):
    """健康检查响应"""
    status: str  # healthy, degraded, unhealthy
    version: str
    uptime_seconds: int
    timestamp: str
    checks: Dict[str, Dict]


class DependencyCheck(BaseModel):
    """依赖检查"""
    name: str
    status: str  # up, down, degraded
    latency_ms: Optional[float]
    message: Optional[str]


# 启动时间
START_TIME = datetime.now()


def check_database() -> Dict:
    """检查数据库连接"""
    try:
        start = time.time()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = (time.time() - start) * 1000
        
        # 检查表是否存在
        db = SessionLocal()
        try:
            device_count = db.query(Device).count()
            alert_count = db.query(Alert).count()
            audit_count = db.query(AuditLog).count()
            
            return {
                "status": "up",
                "latency_ms": round(latency, 2),
                "tables": {
                    "devices": device_count,
                    "alerts": alert_count,
                    "audit_logs": audit_count
                }
            }
        finally:
            db.close()
    except Exception as e:
        return {
            "status": "down",
            "latency_ms": None,
            "error": str(e)
        }


def check_disk() -> Dict:
    """检查磁盘空间"""
    try:
        # 获取项目根目录所在分区
        project_path = os.path.dirname(os.path.dirname(__file__))
        usage = psutil.disk_usage(project_path)
        
        status = "ok"
        if usage.percent > 90:
            status = "critical"
        elif usage.percent > 80:
            status = "warning"
        
        return {
            "status": status,
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "usage_percent": round(usage.percent, 1)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def check_memory() -> Dict:
    """检查内存使用"""
    try:
        mem = psutil.virtual_memory()
        
        status = "ok"
        if mem.percent > 90:
            status = "critical"
        elif mem.percent > 80:
            status = "warning"
        
        return {
            "status": status,
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "usage_percent": round(mem.percent, 1)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def check_cpu() -> Dict:
    """检查 CPU 使用"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        status = "ok"
        if cpu_percent > 90:
            status = "critical"
        elif cpu_percent > 80:
            status = "warning"
        
        return {
            "status": status,
            "usage_percent": round(cpu_percent, 1),
            "cores": psutil.cpu_count()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def check_agents() -> Dict:
    """检查 Agent 状态"""
    try:
        db = SessionLocal()
        try:
            # 尝试从 agent_manager 模块导入 Agent 模型
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from agent_manager import Agent as AgentModel
            
            total = db.query(AgentModel).count()
            running = db.query(AgentModel).filter(AgentModel.status == "running").count()
            stopped = db.query(AgentModel).filter(AgentModel.status.in_(["stopped", "error"])).count()
            
            return {
                "status": "ok" if stopped == 0 else "warning",
                "total": total,
                "running": running,
                "stopped": stopped
            }
        finally:
            db.close()
    except Exception as e:
        return {
            "status": "warning",  # Agent 检查失败不影响整体健康
            "error": str(e),
            "message": "Agent manager not available"
        }


def get_overall_status(checks: Dict) -> str:
    """计算整体健康状态"""
    statuses = [check.get("status") for check in checks.values()]
    
    if "down" in statuses or "critical" in statuses:
        return "unhealthy"
    elif "warning" in statuses:
        return "degraded"
    else:
        return "healthy"


@router.get("/api/health")
async def health_check():
    """
    完整健康检查
    
    返回所有依赖组件的健康状态
    """
    checks = {
        "database": check_database(),
        "disk": check_disk(),
        "memory": check_memory(),
        "cpu": check_cpu(),
        "agents": check_agents()
    }
    
    overall_status = get_overall_status(checks)
    uptime = int((datetime.now() - START_TIME).total_seconds())
    
    return HealthCheck(
        status=overall_status,
        version="1.0.0",
        uptime_seconds=uptime,
        timestamp=datetime.now().isoformat(),
        checks=checks
    )


@router.get("/api/health/live")
async def liveness_probe():
    """
    存活探针 (Kubernetes)
    
    仅检查进程是否存活
    """
    return {"status": "alive"}


@router.get("/api/health/ready")
async def readiness_probe():
    """
    就绪探针 (Kubernetes)
    
    检查是否准备好接收流量
    """
    db_status = check_database()
    
    if db_status["status"] == "up":
        return {"status": "ready"}
    else:
        raise HTTPException(status_code=503, detail="Database not ready")


@router.get("/api/health/metrics")
async def get_metrics():
    """
    性能指标 (Prometheus 格式)
    
    返回 Prometheus 兼容的指标
    """
    db = SessionLocal()
    try:
        # 从 agent_manager 导入
        from agent_manager import Agent as AgentModel
        
        device_count = db.query(Device).count()
        alert_count = db.query(Alert).count()
        agent_count = db.query(AgentModel).count()
        audit_count = db.query(AuditLog).count()
        
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        disk = psutil.disk_usage(os.path.dirname(os.path.dirname(__file__)))
        
        metrics = f"""# HELP openclaw_devices_total Total number of devices
# TYPE openclaw_devices_total gauge
openclaw_devices_total {device_count}

# HELP openclaw_alerts_total Total number of alerts
# TYPE openclaw_alerts_total gauge
openclaw_alerts_total {alert_count}

# HELP openclaw_agents_total Total number of agents
# TYPE openclaw_agents_total gauge
openclaw_agents_total {agent_count}

# HELP openclaw_audit_logs_total Total number of audit logs
# TYPE openclaw_audit_logs_total gauge
openclaw_audit_logs_total {audit_count}

# HELP openclaw_memory_usage_percent Memory usage percentage
# TYPE openclaw_memory_usage_percent gauge
openclaw_memory_usage_percent {mem.percent}

# HELP openclaw_cpu_usage_percent CPU usage percentage
# TYPE openclaw_cpu_usage_percent gauge
openclaw_cpu_usage_percent {cpu}

# HELP openclaw_disk_usage_percent Disk usage percentage
# TYPE openclaw_disk_usage_percent gauge
openclaw_disk_usage_percent {disk.percent}

# HELP openclaw_uptime_seconds Service uptime in seconds
# TYPE openclaw_uptime_seconds counter
openclaw_uptime_seconds {int((datetime.now() - START_TIME).total_seconds())}
"""
        
        from fastapi.responses import Response
        return Response(content=metrics, media_type="text/plain; charset=utf-8")
    finally:
        db.close()
