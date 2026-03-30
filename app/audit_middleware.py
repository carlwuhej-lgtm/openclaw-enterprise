"""
审计中间件 - 自动记录所有 API 操作到 AuditLog
"""
import re
import asyncio
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from database import SessionLocal
from models import AuditLog


# ==================== 排除路径配置 ====================
EXCLUDE_EXACT = {"/", "/docs", "/openapi.json", "/redoc", "/api/report", "/api/policy/check", "/api/client/report", "/api/client/heartbeat"}
EXCLUDE_PREFIXES = ("/css/", "/js/", "/pages/")

# 平台自身的读取请求全部排除，只记写操作和扫描/管控类操作
EXCLUDE_GET_PREFIXES = (
    "/api/stats",
    "/api/devices",
    "/api/alerts",
    "/api/audit-logs",
    "/api/tenants",
    "/api/users",
    "/api/policies",
    "/api/agents",
    "/api/host",
    "/api/export",
    "/api/traffic",
    "/api/ai",
    "/api/notification",
    "/api/scan",
    "/api/report",
    "/api/process",
    "/api/agent",
    "/api/gateway",
)


def _should_skip(method: str, path: str) -> bool:
    """判断是否跳过记录"""
    if path in EXCLUDE_EXACT:
        return True
    if path.startswith(EXCLUDE_PREFIXES):
        return True
    # GET 请求：排除平台自身的数据查询
    if method == "GET" and path.startswith(EXCLUDE_GET_PREFIXES):
        return True
    return False


# ==================== HTTP Method → operation_type ====================
METHOD_TO_OP = {
    "GET": "api_read",
    "POST": "api_create",
    "PUT": "api_update",
    "DELETE": "api_delete",
}


# ==================== 风险等级判定 ====================
# danger 规则优先匹配
DANGER_PATTERNS = [
    re.compile(r"^/api/process/kill"),
    re.compile(r"^/api/enforcement/block"),
]

WARNING_PATTERNS = [
    re.compile(r"^/api/scan"),
    re.compile(r"^/api/enforcement"),
]


def _classify_risk(method: str, path: str) -> str:
    """根据 method + path 判定风险等级"""
    if method == "GET":
        return "safe"

    if method == "DELETE":
        return "warning"

    # POST / PUT
    if method in ("POST", "PUT"):
        for pattern in DANGER_PATTERNS:
            if pattern.search(path):
                return "danger"
        for pattern in WARNING_PATTERNS:
            if pattern.search(path):
                return "warning"
        return "safe"

    # 其他 method（PATCH 等）默认 safe
    return "safe"


# ==================== 状态码 → status ====================
def _classify_status(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "allowed"
    if 400 <= status_code < 500:
        return "blocked"
    if 500 <= status_code < 600:
        return "error"
    return "allowed"


# ==================== 敏感字段过滤 ====================
SENSITIVE_FIELDS = {'password', 'token', 'secret', 'key', 'api_key', 'apikey', 'access_token', 'refresh_token', 'private_key', 'credential'}
SENSITIVE_RE = re.compile(r'(' + '|'.join(re.escape(f) for f in SENSITIVE_FIELDS) + r')=([^&]+)', re.IGNORECASE)


def _filter_sensitive_params(params_str: str) -> str:
    """过滤查询参数中的敏感信息"""
    if not params_str:
        return ""
    # 将敏感字段值替换为 [REDACTED]
    return SENSITIVE_RE.sub(r'\1=[REDACTED]', params_str)


# ==================== 从路径提取 device_id ====================
DEVICE_ID_RE = re.compile(r"/api/devices/(\d+)")


def _extract_device_id(path: str):
    """尝试从路径中提取 device_id，提取不到返回 None"""
    m = DEVICE_ID_RE.search(path)
    if m:
        return int(m.group(1))
    return None


# ==================== 异步写入审计日志 ====================
def _write_audit_log(
    operation_type: str,
    operation_detail: str,
    risk_level: str,
    audit_status: str,
    device_id: int | None,
    timestamp: datetime,
):
    """在后台线程中同步写入审计日志（避免阻塞事件循环）"""
    db = SessionLocal()
    try:
        log = AuditLog(
            operation_type=operation_type,
            operation_detail=operation_detail,
            risk_level=risk_level,
            status=audit_status,
            device_id=device_id,
            timestamp=timestamp,
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ==================== 中间件实现 ====================
class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        # 排除不需要记录的路径
        if _should_skip(method, path):
            return await call_next(request)

        req_time = datetime.now()

        # 收集请求参数摘要（过滤敏感信息）
        params_summary = ""
        if request.query_params:
            raw_params = f" ?{str(request.query_params)}"
            params_summary = _filter_sensitive_params(raw_params)

        # 执行请求
        response: Response = await call_next(request)

        # 构建 operation_detail（限制 200 字符）
        detail = f"{method} {path}{params_summary}"
        if len(detail) > 200:
            detail = detail[:197] + "..."

        operation_type = METHOD_TO_OP.get(method, "api_read")
        risk_level = _classify_risk(method, path)
        audit_status = _classify_status(response.status_code)
        device_id = _extract_device_id(path)

        # 异步写入，不阻塞响应
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            None,
            _write_audit_log,
            operation_type,
            detail,
            risk_level,
            audit_status,
            device_id,
            req_time,
        )

        return response


# ==================== 注册函数 ====================
def setup_audit_middleware(app):
    """供 main.py 调用，注册审计中间件"""
    app.add_middleware(AuditMiddleware)
