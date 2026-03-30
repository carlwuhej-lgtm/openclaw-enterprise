"""
OpenClaw Enterprise - Agent 操作拦截器
真正能拦截 Agent 操作的核心模块。

架构：
1. Agent 操作预检 API（/api/intercept/check）—— Agent 执行前调用，同步返回 allow/deny
2. 实时进程监控 —— 后台守护线程，检测高危命令并 kill
3. 文件系统监控 —— 监控敏感目录的访问
4. 拦截规则引擎 —— 支持正则、路径、命令黑名单、速率限制

与 OpenClaw 集成方式：
- 方式 A：通过 TOOLS.md 告诉 Agent "执行前先调用 /api/intercept/check"
- 方式 B：后台守护进程实时监控 + 强制 kill
- 方式 C：修改 OpenClaw exec 审批策略（exec.ask = always）配合本平台审批
"""
import os
import re
import json
import time
import signal
import threading
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

import psutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func

from database import SessionLocal
from models import SecurityPolicy, Alert, AuditLog, Device

logger = logging.getLogger("interceptor")


# ==================== 拦截规则定义 ====================

class InterceptRule:
    """单条拦截规则"""
    __slots__ = ("name", "type", "pattern", "action", "severity", "compiled")

    def __init__(self, name: str, rule_type: str, pattern: str,
                 action: str = "block", severity: str = "high"):
        self.name = name
        self.type = rule_type        # command, path, api_key, rate_limit, process
        self.pattern = pattern
        self.action = action          # block, warn, kill, alert
        self.severity = severity      # low, medium, high, critical
        self.compiled = re.compile(pattern, re.IGNORECASE) if rule_type != "rate_limit" else None


# ==================== 内置规则集 ====================

BUILTIN_RULES: List[InterceptRule] = [
    # ---- 高危命令 ----
    InterceptRule("rm_rf", "command", r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force\s+).*(/|~|\$HOME|\.\.|/etc|/usr|/var|/System)",
                  action="block", severity="critical"),
    InterceptRule("rm_recursive", "command", r"rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+(/|~|\$HOME)",
                  action="block", severity="critical"),
    InterceptRule("dd_disk", "command", r"dd\s+.*of=/dev/",
                  action="block", severity="critical"),
    InterceptRule("mkfs", "command", r"mkfs\.",
                  action="block", severity="critical"),
    InterceptRule("chmod_777", "command", r"chmod\s+(-R\s+)?777\s+(/|~)",
                  action="block", severity="high"),
    InterceptRule("curl_bash", "command", r"curl\s+.*\|\s*(ba)?sh",
                  action="block", severity="critical"),
    InterceptRule("wget_bash", "command", r"wget\s+.*\|\s*(ba)?sh",
                  action="block", severity="critical"),
    InterceptRule("eval_exec", "command", r"(python|node|ruby|perl)\s+(-[a-z]\s+)?['\"].*(__import__|eval|exec|system|popen|subprocess)",
                  action="block", severity="high"),
    InterceptRule("reverse_shell", "command",
                  r"(bash\s+-i\s+>&|nc\s+-[a-z]*e\s+|ncat\s+.*-e|python.*socket.*connect|/dev/tcp/)",
                  action="block", severity="critical"),
    InterceptRule("crontab_write", "command", r"crontab\s+-[re]|echo\s+.*>>\s*/etc/cron",
                  action="block", severity="high"),
    InterceptRule("ssh_keygen_overwrite", "command", r"ssh-keygen\s+.*-f\s+.*id_rsa|cp\s+.*\.ssh/authorized_keys",
                  action="block", severity="high"),
    InterceptRule("kill_system", "command", r"kill\s+-9\s+(-1|1\b)|killall\s+",
                  action="block", severity="high"),
    InterceptRule("sudoers_edit", "command", r"visudo|echo\s+.*>>\s*/etc/sudoers",
                  action="block", severity="critical"),
    InterceptRule("reboot_shutdown", "command", r"(shutdown|reboot|halt|poweroff|init\s+[06])\b",
                  action="block", severity="high"),

    # ---- 渗透工具 ----
    InterceptRule("nmap", "command", r"\bnmap\b",
                  action="warn", severity="medium"),
    InterceptRule("sqlmap", "command", r"\bsqlmap\b",
                  action="block", severity="high"),
    InterceptRule("metasploit", "command", r"\b(msfconsole|msfvenom|meterpreter)\b",
                  action="block", severity="critical"),
    InterceptRule("hydra", "command", r"\b(hydra|medusa|john|hashcat)\b",
                  action="block", severity="high"),
    InterceptRule("nikto_dirb", "command", r"\b(nikto|dirb|dirbuster|gobuster|ffuf|wfuzz)\b",
                  action="warn", severity="medium"),

    # ---- 敏感路径 ----
    InterceptRule("ssh_keys", "path", r"(\.ssh/(id_|authorized_keys|known_hosts|config)|/etc/ssh/)",
                  action="block", severity="critical"),
    InterceptRule("gnupg", "path", r"\.gnupg/",
                  action="block", severity="high"),
    InterceptRule("aws_creds", "path", r"\.aws/(credentials|config)",
                  action="block", severity="critical"),
    InterceptRule("kube_config", "path", r"\.kube/config",
                  action="block", severity="high"),
    InterceptRule("env_file", "path", r"/\.env(\.\w+)?$",
                  action="warn", severity="medium"),
    InterceptRule("shadow", "path", r"/etc/(shadow|gshadow|master\.passwd)",
                  action="block", severity="critical"),
    InterceptRule("passwd", "path", r"/etc/passwd$",
                  action="warn", severity="low"),
    InterceptRule("openclaw_config", "path", r"\.openclaw/openclaw\.json",
                  action="block", severity="high"),
    InterceptRule("browser_data", "path",
                  r"(Chrome|Firefox|Safari).*(Cookies|Login Data|History|Bookmarks)",
                  action="block", severity="high"),
    InterceptRule("keychain", "path", r"\.keychain|Keychains/",
                  action="block", severity="critical"),

    # ---- API 密钥泄露 ----
    InterceptRule("openai_key", "api_key", r"sk-[a-zA-Z0-9\-_]{20,}",
                  action="block", severity="critical"),
    InterceptRule("aws_key", "api_key", r"AKIA[A-Z0-9]{16}",
                  action="block", severity="critical"),
    InterceptRule("github_token", "api_key", r"(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}",
                  action="block", severity="critical"),
    InterceptRule("slack_token", "api_key", r"xox[baprs]-[a-zA-Z0-9\-]{10,}",
                  action="block", severity="high"),
    InterceptRule("private_key_content", "api_key", r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
                  action="block", severity="critical"),
    InterceptRule("generic_secret", "api_key", r"(password|secret|token|api_key)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}",
                  action="warn", severity="medium"),
]


# ==================== 速率限制器 ====================

class RateLimiter:
    """滑动窗口速率限制"""

    def __init__(self):
        self._windows: Dict[str, list] = defaultdict(list)  # key -> [timestamp, ...]
        self._lock = threading.Lock()

    def check(self, key: str, max_count: int, window_seconds: int) -> Tuple[bool, int]:
        """
        检查速率限制。返回 (is_allowed, current_count)。
        """
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            # 清理过期记录
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]
            count = len(self._windows[key])
            if count >= max_count:
                return False, count
            self._windows[key].append(now)
            return True, count + 1

    def get_count(self, key: str, window_seconds: int) -> int:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]
            return len(self._windows[key])


# ==================== 拦截引擎 ====================

class InterceptEngine:
    """核心拦截引擎"""

    def __init__(self):
        self.rules: List[InterceptRule] = list(BUILTIN_RULES)
        self.rate_limiter = RateLimiter()
        self._db_rules_loaded_at: Optional[datetime] = None
        self._db_rules_ttl = 30  # 秒
        self._stats = {
            "total_checked": 0,
            "total_blocked": 0,
            "total_warned": 0,
            "total_allowed": 0,
        }
        self._lock = threading.Lock()

        # 速率限制配置
        self.rate_limits = {
            "command_exec": {"max": 30, "window": 60},     # 每分钟最多 30 次命令
            "file_write": {"max": 50, "window": 60},        # 每分钟最多 50 次写文件
            "api_call": {"max": 100, "window": 60},          # 每分钟最多 100 次 API 调用
            "llm_call": {"max": 20, "window": 60},           # 每分钟最多 20 次 LLM 调用
        }

    def _load_db_rules(self):
        """从数据库加载自定义规则"""
        now = datetime.now()
        if self._db_rules_loaded_at and (now - self._db_rules_loaded_at).total_seconds() < self._db_rules_ttl:
            return

        db = SessionLocal()
        try:
            policies = db.query(SecurityPolicy).filter(SecurityPolicy.is_enabled == True).all()
            # 清除旧的数据库规则（保留内置规则）
            builtin_names = {r.name for r in BUILTIN_RULES}
            self.rules = [r for r in self.rules if r.name in builtin_names]

            for p in policies:
                try:
                    config = json.loads(p.config) if p.config else {}
                except json.JSONDecodeError:
                    continue

                # 敏感路径策略
                if "paths" in config:
                    for path in config["paths"]:
                        escaped = re.escape(path).replace(r"\~", "~")
                        rule = InterceptRule(
                            name=f"db_path_{p.id}_{path}",
                            rule_type="path",
                            pattern=escaped,
                            action="block",
                            severity="high",
                        )
                        self.rules.append(rule)

                # 高危命令策略
                if "commands" in config:
                    for cmd in config["commands"]:
                        escaped = re.escape(cmd)
                        rule = InterceptRule(
                            name=f"db_cmd_{p.id}_{cmd}",
                            rule_type="command",
                            pattern=escaped,
                            action="block" if config.get("approval_required") else "warn",
                            severity="high",
                        )
                        self.rules.append(rule)

                # API 密钥检测
                if config.get("scan_patterns"):
                    for pat in config["scan_patterns"]:
                        rule = InterceptRule(
                            name=f"db_apikey_{p.id}_{pat}",
                            rule_type="api_key",
                            pattern=re.escape(pat) + r"[a-zA-Z0-9_\-]{10,}",
                            action="block",
                            severity="critical",
                        )
                        self.rules.append(rule)

            self._db_rules_loaded_at = now
        except Exception as e:
            logger.error(f"加载数据库规则失败: {e}")
        finally:
            db.close()

    def check(self, agent_id: str, operation_type: str, content: str,
              device_id: Optional[int] = None) -> "InterceptResult":
        """
        核心检查方法。

        参数:
            agent_id: Agent 标识
            operation_type: 操作类型（command_exec, file_read, file_write, api_call, llm_call, message_send）
            content: 操作内容（命令文本、文件路径、API URL 等）
            device_id: 设备 ID

        返回:
            InterceptResult
        """
        self._load_db_rules()

        with self._lock:
            self._stats["total_checked"] += 1

        result = InterceptResult(agent_id=agent_id, operation_type=operation_type, content=content[:200])
        violations = []

        # 1. 速率限制检查
        rate_key = f"{agent_id}:{operation_type}"
        limits = self.rate_limits.get(operation_type)
        if limits:
            allowed, count = self.rate_limiter.check(rate_key, limits["max"], limits["window"])
            if not allowed:
                violations.append(Violation(
                    rule_name="rate_limit",
                    rule_type="rate_limit",
                    reason=f"速率超限: {operation_type} 已达 {count}/{limits['max']} 次/分钟",
                    severity="high",
                    action="block",
                ))

        # 2. 规则匹配
        for rule in self.rules:
            matched = False

            if rule.type == "command" and operation_type == "command_exec":
                if rule.compiled and rule.compiled.search(content):
                    matched = True

            elif rule.type == "path" and operation_type in ("file_read", "file_write", "file_delete", "command_exec"):
                if rule.compiled and rule.compiled.search(content):
                    matched = True

            elif rule.type == "api_key" and operation_type in ("file_write", "command_exec", "message_send"):
                if rule.compiled and rule.compiled.search(content):
                    matched = True

            elif rule.type == "process":
                if rule.compiled and rule.compiled.search(content):
                    matched = True

            if matched:
                violations.append(Violation(
                    rule_name=rule.name,
                    rule_type=rule.type,
                    reason=f"匹配规则 [{rule.name}]: {rule.pattern[:60]}",
                    severity=rule.severity,
                    action=rule.action,
                ))

        # 3. 判定最终结果
        if violations:
            # 取最严格的 action
            actions_priority = {"block": 4, "kill": 3, "warn": 2, "alert": 1}
            worst_action = max(violations, key=lambda v: actions_priority.get(v.action, 0))
            result.action = worst_action.action
            result.allowed = worst_action.action not in ("block", "kill")
            result.risk_level = worst_action.severity
            result.violations = violations
        else:
            result.allowed = True
            result.action = "allow"
            result.risk_level = "safe"

        # 统计
        with self._lock:
            if not result.allowed:
                self._stats["total_blocked"] += 1
            elif result.violations:
                self._stats["total_warned"] += 1
            else:
                self._stats["total_allowed"] += 1

        return result

    def check_and_record(self, agent_id: str, operation_type: str, content: str,
                         device_id: Optional[int] = None) -> "InterceptResult":
        """检查 + 写审计日志 + 触发告警"""
        result = self.check(agent_id, operation_type, content, device_id)

        db = SessionLocal()
        try:
            # 写审计日志
            audit = AuditLog(
                device_id=device_id,
                operation_type=operation_type,
                operation_detail=f"[{agent_id}] {content[:400]}",
                risk_level=result.risk_level,
                status="blocked" if not result.allowed else ("warning" if result.violations else "allowed"),
                timestamp=datetime.now(),
            )
            db.add(audit)

            # 违规 → 告警
            if not result.allowed:
                for v in result.violations:
                    if v.action in ("block", "kill"):
                        alert = Alert(
                            title=f"拦截: {v.rule_name}",
                            description=(
                                f"Agent [{agent_id}] 操作被拦截\n"
                                f"类型: {operation_type}\n"
                                f"原因: {v.reason}\n"
                                f"内容: {content[:200]}"
                            ),
                            level=v.severity if v.severity in ("critical", "high") else "medium",
                            device_id=device_id,
                            is_resolved=False,
                            created_at=datetime.now(),
                        )
                        db.add(alert)

            db.commit()
        except Exception as e:
            logger.error(f"记录审计日志失败: {e}")
            db.rollback()
        finally:
            db.close()

        return result

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def get_rules_summary(self) -> List[dict]:
        """返回当前所有规则的摘要"""
        return [
            {"name": r.name, "type": r.type, "action": r.action, "severity": r.severity, "pattern": r.pattern[:80]}
            for r in self.rules
        ]


# ==================== 进程守卫 ====================

class ProcessGuard:
    """
    后台守护线程：实时检测系统中正在执行的高危命令并 kill。
    这是真正的「拦截」—— 不依赖 Agent 主动上报，而是主动扫描。
    """

    DANGEROUS_COMMANDS = [
        (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\$HOME)", "critical"),
        (r"dd\s+.*of=/dev/", "critical"),
        (r"mkfs\.", "critical"),
        (r":(){ :\|:& };:", "critical"),   # fork bomb
        (r"curl\s+.*\|\s*(ba)?sh", "critical"),
        (r"wget\s+.*\|\s*(ba)?sh", "critical"),
        (r"nc\s+-[a-z]*e\s+/bin/(ba)?sh", "critical"),
        (r"python.*socket.*connect", "high"),
    ]

    def __init__(self, engine: InterceptEngine):
        self.engine = engine
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._scan_interval = 3  # 秒
        self._killed_pids: set = set()  # 避免重复 kill 日志

    def start(self):
        """启动后台守护"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="process-guard")
        self._thread.start()
        logger.info("ProcessGuard 已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("ProcessGuard 已停止")

    def _loop(self):
        compiled = [(re.compile(p, re.IGNORECASE), sev) for p, sev in self.DANGEROUS_COMMANDS]
        while self._running:
            try:
                self._scan(compiled)
            except Exception as e:
                logger.error(f"ProcessGuard 扫描异常: {e}")
            time.sleep(self._scan_interval)

    def _scan(self, compiled: list):
        """扫描当前进程"""
        for proc in psutil.process_iter(["pid", "name", "cmdline", "username"]):
            try:
                info = proc.info
                pid = info["pid"]
                if pid in self._killed_pids:
                    continue

                cmdline = " ".join(info["cmdline"] or [])
                if not cmdline:
                    continue

                # 跳过自身和系统进程
                if info["name"] in ("python", "Python") and "interceptor" in cmdline:
                    continue

                for pattern, severity in compiled:
                    if pattern.search(cmdline):
                        # 检测到危险命令！
                        logger.warning(f"检测到危险进程 PID={pid}: {cmdline[:120]}")
                        self._handle_dangerous_process(pid, cmdline, severity)
                        self._killed_pids.add(pid)
                        break

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # 清理已不存在的 PID
        existing_pids = {p.pid for p in psutil.process_iter()}
        self._killed_pids &= existing_pids

    def _handle_dangerous_process(self, pid: int, cmdline: str, severity: str):
        """处理危险进程：kill + 记录审计 + 生成告警"""
        # Kill
        killed = False
        try:
            p = psutil.Process(pid)
            p.kill()  # SIGKILL
            killed = True
            logger.warning(f"已终止危险进程 PID={pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.error(f"无法终止 PID={pid}: {e}")

        # 记录
        db = SessionLocal()
        try:
            audit = AuditLog(
                operation_type="process_kill",
                operation_detail=f"[ProcessGuard] 检测并终止危险进程 PID={pid}: {cmdline[:300]}",
                risk_level=severity,
                status="blocked" if killed else "failed",
                timestamp=datetime.now(),
            )
            db.add(audit)

            alert = Alert(
                title=f"危险进程拦截: PID {pid}",
                description=(
                    f"ProcessGuard 检测到危险命令并{'已终止' if killed else '尝试终止(失败)'}。\n"
                    f"PID: {pid}\n"
                    f"命令: {cmdline[:300]}\n"
                    f"严重度: {severity}"
                ),
                level="critical" if severity == "critical" else "high",
                is_resolved=killed,
                created_at=datetime.now(),
            )
            db.add(alert)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @property
    def is_running(self) -> bool:
        return self._running


# ==================== 数据模型 ====================

class Violation(BaseModel):
    rule_name: str
    rule_type: str
    reason: str
    severity: str
    action: str


class InterceptResult(BaseModel):
    agent_id: str
    operation_type: str
    content: str
    allowed: bool = True
    action: str = "allow"
    risk_level: str = "safe"
    violations: List[Violation] = []
    timestamp: datetime = Field(default_factory=datetime.now)


class InterceptRequest(BaseModel):
    """拦截检查请求"""
    agent_id: str = Field(..., description="Agent 标识，如 daily, security")
    operation_type: str = Field(..., description="操作类型: command_exec, file_read, file_write, file_delete, api_call, llm_call, message_send")
    content: str = Field(..., description="操作内容: 命令文本、文件路径、URL 等")
    device_id: Optional[int] = Field(None, description="设备 ID")


class InterceptResponse(BaseModel):
    """拦截检查响应"""
    allowed: bool
    action: str          # allow, block, warn, kill
    risk_level: str      # safe, low, medium, high, critical
    violations: List[Violation] = []
    message: str = ""


class RuleCreateRequest(BaseModel):
    """创建自定义规则"""
    name: str
    rule_type: str = Field(..., description="command, path, api_key, process")
    pattern: str = Field(..., description="正则表达式")
    action: str = Field("block", description="block, warn, kill, alert")
    severity: str = Field("high", description="low, medium, high, critical")


# ==================== 全局实例 ====================

intercept_engine = InterceptEngine()
process_guard = ProcessGuard(intercept_engine)


# ==================== FastAPI 路由 ====================

router = APIRouter(tags=["拦截引擎"])


@router.on_event("startup")
async def start_process_guard():
    """应用启动时启动进程守卫"""
    process_guard.start()
    logger.info("🛡️ 拦截引擎已启动")


@router.on_event("shutdown")
async def stop_process_guard():
    process_guard.stop()


# ---------- 核心 API ----------

@router.post("/api/intercept/check", response_model=InterceptResponse)
async def intercept_check(req: InterceptRequest):
    """
    🛡️ 操作预检接口（同步，低延迟）

    Agent 执行操作前调用此接口，根据返回结果决定是否继续执行。
    仅做检查，不写审计日志。

    用法示例：
    ```
    POST /api/intercept/check
    {
        "agent_id": "daily",
        "operation_type": "command_exec",
        "content": "rm -rf /tmp/test"
    }
    ```

    响应：
    - allowed=true: 放行
    - allowed=false, action=block: 拦截，不要执行
    - allowed=true, action=warn: 放行，但有警告
    """
    result = intercept_engine.check(req.agent_id, req.operation_type, req.content, req.device_id)

    msg = "✅ 放行" if result.allowed else f"🚫 拦截: {result.violations[0].reason if result.violations else '策略禁止'}"
    if result.allowed and result.violations:
        msg = f"⚠️ 警告: {result.violations[0].reason}"

    return InterceptResponse(
        allowed=result.allowed,
        action=result.action,
        risk_level=result.risk_level,
        violations=result.violations,
        message=msg,
    )


@router.post("/api/intercept/report", response_model=InterceptResponse)
async def intercept_report(req: InterceptRequest):
    """
    🛡️ 操作上报接口（检查 + 写审计日志 + 触发告警）

    Agent 执行操作后调用此接口上报。
    """
    result = intercept_engine.check_and_record(req.agent_id, req.operation_type, req.content, req.device_id)

    msg = "✅ 已记录" if result.allowed else f"🚫 拦截并记录: {result.violations[0].reason if result.violations else ''}"

    return InterceptResponse(
        allowed=result.allowed,
        action=result.action,
        risk_level=result.risk_level,
        violations=result.violations,
        message=msg,
    )


# ---------- 管理 API ----------

@router.get("/api/intercept/stats")
async def get_intercept_stats():
    """拦截统计"""
    stats = intercept_engine.get_stats()
    stats["process_guard_running"] = process_guard.is_running
    stats["total_rules"] = len(intercept_engine.rules)
    stats["rate_limits"] = intercept_engine.rate_limits
    return stats


@router.get("/api/intercept/rules")
async def get_intercept_rules():
    """获取所有拦截规则"""
    return intercept_engine.get_rules_summary()


@router.post("/api/intercept/rules")
async def add_intercept_rule(req: RuleCreateRequest):
    """添加自定义拦截规则"""
    try:
        rule = InterceptRule(
            name=req.name,
            rule_type=req.rule_type,
            pattern=req.pattern,
            action=req.action,
            severity=req.severity,
        )
        intercept_engine.rules.append(rule)
        return {"success": True, "message": f"规则 [{req.name}] 已添加", "total_rules": len(intercept_engine.rules)}
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"无效的正则表达式: {e}")


@router.delete("/api/intercept/rules/{rule_name}")
async def delete_intercept_rule(rule_name: str):
    """删除拦截规则"""
    before = len(intercept_engine.rules)
    intercept_engine.rules = [r for r in intercept_engine.rules if r.name != rule_name]
    after = len(intercept_engine.rules)
    if before == after:
        raise HTTPException(status_code=404, detail=f"规则 [{rule_name}] 不存在")
    return {"success": True, "message": f"规则 [{rule_name}] 已删除"}


@router.post("/api/intercept/guard/start")
async def start_guard():
    """启动进程守卫"""
    process_guard.start()
    return {"success": True, "message": "ProcessGuard 已启动"}


@router.post("/api/intercept/guard/stop")
async def stop_guard():
    """停止进程守卫"""
    process_guard.stop()
    return {"success": True, "message": "ProcessGuard 已停止"}


@router.get("/api/intercept/guard/status")
async def guard_status():
    """进程守卫状态"""
    return {
        "running": process_guard.is_running,
        "scan_interval": process_guard._scan_interval,
        "killed_count": len(process_guard._killed_pids),
    }


# ---------- 批量测试 ----------

@router.post("/api/intercept/test")
async def test_intercept(operations: List[InterceptRequest]):
    """批量测试拦截规则（不写审计日志）"""
    results = []
    for op in operations[:50]:  # 限制 50 条
        r = intercept_engine.check(op.agent_id, op.operation_type, op.content, op.device_id)
        results.append({
            "content": op.content[:80],
            "allowed": r.allowed,
            "action": r.action,
            "risk_level": r.risk_level,
            "violations": [v.dict() for v in r.violations],
        })
    return results
