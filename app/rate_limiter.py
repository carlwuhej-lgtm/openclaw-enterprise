"""
OpenClaw Enterprise - API 限速中间件
每 IP 每分钟最多 60 次请求，超限返回 429
使用内存字典 + 滑动时间窗口实现
"""
import time
from collections import defaultdict
from threading import Lock
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """API 限速中间件"""
    
    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()
    
    async def dispatch(self, request: Request, call_next):
        # 静态资源和健康检查不限速
        path = request.url.path
        if path.startswith(("/css/", "/js/", "/pages/", "/favicon")) or path == "/":
            return await call_next(request)
        
        # 获取客户端 IP
        client_ip = request.client.host if request.client else "unknown"
        # 考虑代理情况
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        
        now = time.time()
        
        with self._lock:
            # 清理过期记录
            window_start = now - self.window_seconds
            self._requests[client_ip] = [
                t for t in self._requests[client_ip] if t > window_start
            ]
            
            # 检查是否超限
            if len(self._requests[client_ip]) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "请求过于频繁，请稍后重试",
                        "retry_after": self.window_seconds
                    },
                    headers={"Retry-After": str(self.window_seconds)}
                )
            
            # 记录请求
            self._requests[client_ip].append(now)
        
        # 定期清理长时间不活跃的 IP 记录（每 1000 次请求清理一次）
        total = sum(len(v) for v in self._requests.values())
        if total > 10000:
            self._cleanup(now)
        
        return await call_next(request)
    
    def _cleanup(self, now: float):
        """清理过期 IP 记录"""
        with self._lock:
            cutoff = now - self.window_seconds * 10
            expired_ips = [
                ip for ip, timestamps in self._requests.items()
                if not timestamps or max(timestamps) < cutoff
            ]
            for ip in expired_ips:
                del self._requests[ip]
