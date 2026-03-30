"""
OpenClaw Enterprise - 策略执行引擎
加载安全策略，对 Agent 上报的操作进行实时检查，违规生成告警。
"""
import re
import json
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel

from database import SessionLocal
from models import SecurityPolicy, Alert, AuditLog


# ==================== 数据模型 ====================

class AgentOperation(BaseModel):
    """Agent 上报的操作"""
    agent_id: str
    device_id: Optional[int] = None
    operation_type: str   # command_exec, file_read, file_write, api_call, message_send
    detail: str           # 具体操作内容
    timestamp: Optional[datetime] = None


class PolicyCheckResult(BaseModel):
    """策略检查结果"""
    allowed: bool = True
    violations: List[Dict] = []
    risk_level: str = "safe"   # safe, warning, danger


# ==================== 策略引擎 ====================

class PolicyEngine:
    """策略执行引擎 - 实时检查 Agent 操作是否违反安全策略"""

    def __init__(self):
        self._policies_cache = []
        self._cache_time = None
        self._cache_ttl = 30  # 30 秒缓存

    def _load_policies(self):
        """从数据库加载已启用的策略"""
        now = datetime.now()
        if self._cache_time and (now - self._cache_time).total_seconds() < self._cache_ttl:
            return self._policies_cache

        db = SessionLocal()
        try:
            policies = db.query(SecurityPolicy).filter(SecurityPolicy.is_enabled == True).all()
            self._policies_cache = []
            for p in policies:
                try:
                    config = json.loads(p.config) if p.config else {}
                except json.JSONDecodeError:
                    config = {}
                self._policies_cache.append({
                    "id": p.id,
                    "name": p.name,
                    "config": config,
                })
            self._cache_time = now
            return self._policies_cache
        finally:
            db.close()

    def check(self, op: AgentOperation) -> PolicyCheckResult:
        """检查一个 Agent 操作是否违反策略"""
        policies = self._load_policies()
        result = PolicyCheckResult()

        for policy in policies:
            name = policy["name"]
            config = policy["config"]

            # ---- 策略1: 禁止访问敏感目录 ----
            if "paths" in config and op.operation_type in ("file_read", "file_write", "command_exec"):
                for path in config["paths"]:
                    # 展开 ~ 
                    expanded = path.replace("~", "/Users/")  # 粗略展开
                    if path in op.detail or expanded in op.detail:
                        result.allowed = False
                        result.risk_level = "danger"
                        result.violations.append({
                            "policy_id": policy["id"],
                            "policy_name": name,
                            "reason": f"访问了受保护路径: {path}",
                            "matched": path,
                        })

            # ---- 策略2: 高危命令审批 ----
            if "commands" in config and op.operation_type == "command_exec":
                for cmd in config["commands"]:
                    if cmd in op.detail:
                        result.allowed = False
                        result.risk_level = "danger"
                        result.violations.append({
                            "policy_id": policy["id"],
                            "policy_name": name,
                            "reason": f"执行了高危命令: {cmd}",
                            "matched": cmd,
                        })

            # ---- 策略3: API 密钥明文检测 ----
            if config.get("enforce_env_ref") and op.operation_type in ("file_write", "command_exec"):
                # 检测常见密钥模式
                key_patterns = [
                    r'sk-[a-zA-Z0-9]{20,}',        # OpenAI
                    r'AKIA[A-Z0-9]{16}',            # AWS
                    r'ghp_[a-zA-Z0-9]{36}',         # GitHub
                    r'xoxb-[a-zA-Z0-9\-]+',         # Slack
                ]
                for pattern in key_patterns:
                    if re.search(pattern, op.detail):
                        result.allowed = False
                        result.risk_level = "danger"
                        result.violations.append({
                            "policy_id": policy["id"],
                            "policy_name": name,
                            "reason": "检测到明文 API 密钥",
                            "matched": pattern,
                        })
                        break

        # 没有违规但有可疑操作，标记 warning
        if result.allowed and op.operation_type == "command_exec":
            suspicious = ["curl", "wget", "nc ", "netcat", "python -c", "eval"]
            for s in suspicious:
                if s in op.detail:
                    result.risk_level = "warning"
                    break

        return result

    def check_and_record(self, op: AgentOperation) -> PolicyCheckResult:
        """检查操作 + 写入审计日志 + 违规时生成告警"""
        result = self.check(op)

        db = SessionLocal()
        try:
            # 写审计日志
            audit = AuditLog(
                device_id=op.device_id,
                operation_type=op.operation_type,
                operation_detail=op.detail[:500],
                risk_level=result.risk_level,
                status="blocked" if not result.allowed else "allowed",
                timestamp=op.timestamp or datetime.now(),
            )
            db.add(audit)

            # 违规时生成告警
            if not result.allowed:
                for v in result.violations:
                    alert = Alert(
                        title=f"策略违规: {v['policy_name']}",
                        description=f"Agent [{op.agent_id}] {v['reason']}\n操作: {op.detail[:200]}",
                        level="high",
                        device_id=op.device_id,
                        is_resolved=False,
                        created_at=datetime.now(),
                    )
                    db.add(alert)

            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

        return result


# 全局单例
engine = PolicyEngine()


# ==================== FastAPI 路由 ====================

from fastapi import APIRouter, Depends
router = APIRouter(tags=["策略引擎"])


class ReportRequest(BaseModel):
    """Agent 操作上报请求"""
    agent_id: str
    device_id: Optional[int] = None
    operation_type: str
    detail: str


class ReportResponse(BaseModel):
    """上报响应"""
    allowed: bool
    risk_level: str
    violations: List[Dict] = []


@router.post("/api/report", response_model=ReportResponse)
async def report_operation(req: ReportRequest):
    """
    Agent 操作上报接口
    
    Agent 在执行操作前/后调用此接口，平台实时检查策略并返回结果。
    违规操作自动生成告警。
    """
    op = AgentOperation(
        agent_id=req.agent_id,
        device_id=req.device_id,
        operation_type=req.operation_type,
        detail=req.detail,
    )
    result = engine.check_and_record(op)
    return ReportResponse(
        allowed=result.allowed,
        risk_level=result.risk_level,
        violations=result.violations,
    )


@router.post("/api/policy/check", response_model=ReportResponse)
async def check_operation(req: ReportRequest):
    """
    策略预检接口（只检查不记录）
    
    Agent 执行前调用，判断是否允许。
    """
    op = AgentOperation(
        agent_id=req.agent_id,
        device_id=req.device_id,
        operation_type=req.operation_type,
        detail=req.detail,
    )
    result = engine.check(op)
    return ReportResponse(
        allowed=result.allowed,
        risk_level=result.risk_level,
        violations=result.violations,
    )
