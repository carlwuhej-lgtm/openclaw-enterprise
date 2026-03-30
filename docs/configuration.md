# 配置说明 (Configuration Guide)

本文档详细说明 OpenClaw Enterprise 的所有配置项。

---

## 💾 数据库说明

### 默认配置
- **开发/测试**: SQLite 3（文件数据库，无需安装）
- **生产环境**: PostgreSQL 14+（推荐）

### 数据库选择指南

| 场景 | 推荐数据库 | 说明 |
|------|-----------|------|
| 本地开发 | SQLite | 零配置，开箱即用 |
| 小规模部署 (<100 用户) | SQLite | 简单可靠，无需维护 |
| 中大规模部署 | PostgreSQL | 高性能，支持并发 |
| 企业级部署 | PostgreSQL + 主从复制 | 高可用，读写分离 |

---

## 📋 环境变量配置

### 必需配置

| 变量名 | 说明 | 示例值 | 默认值 |
|--------|------|--------|--------|
| `DATABASE_URL` | 数据库连接字符串 | `sqlite:///./app/openclaw_enterprise.db` | 无 |
| `SECRET_KEY` | JWT 签名密钥 | `your-secret-key` | 无 |

### 可选配置

| 变量名 | 说明 | 示例值 | 默认值 |
|--------|------|--------|--------|
| `ALGORITHM` | JWT 算法 | `HS256` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token 过期时间（分钟） | `1440` | `1440` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token 过期时间（天） | `30` | `30` |
| `CORS_ORIGINS` | 允许的 CORS 源 | `http://localhost:8003` | `http://localhost:8003` |
| `OPENCLAW_GATEWAY_TOKEN` | OpenClaw Gateway Token | `your-token` | 无 |
| `OPENCLAW_GATEWAY_PORT` | Gateway 端口 | `18789` | `18789` |
| `LOG_LEVEL` | 日志级别 | `INFO` | `INFO` |
| `TIMEZONE` | 时区 | `Asia/Shanghai` | `UTC` |

---

## 🔐 JWT 认证配置

### 生成安全密钥
```bash
# 方法 1: 使用 Python
python -c "import secrets; print(secrets.token_hex(32))"

# 方法 2: 使用 OpenSSL
openssl rand -hex 32

# 方法 3: 使用系统随机数
cat /dev/urandom | head -c 32 | xxd -p
```

### Token 过期时间建议
| 环境 | Access Token | Refresh Token |
|------|-------------|---------------|
| 开发 | 1440 分钟 (1 天) | 30 天 |
| 生产 | 60 分钟 | 7 天 |
| 高安全 | 15 分钟 | 1 天 |

---

## 🗄️ 数据库配置

### SQLite（开发环境）
```ini
DATABASE_URL=sqlite:///./app/openclaw_enterprise.db
```

### PostgreSQL（生产环境）
```ini
DATABASE_URL=postgresql://username:password@localhost:5432/openclaw_enterprise
```

### 连接池配置（高级）
```python
# 在 database.py 中调整
engine = create_engine(
    DATABASE_URL,
    pool_size=10,           # 连接池大小
    max_overflow=20,        # 最大溢出连接数
    pool_pre_ping=True,     # 自动检测失效连接
)
```

---

## 🌐 CORS 配置

### 开发环境
```ini
CORS_ORIGINS=http://localhost:8003,http://127.0.0.1:8003
```

### 生产环境
```ini
CORS_ORIGINS=https://your-domain.com
```

### 允许所有域（不推荐）
```ini
CORS_ORIGINS=*
```

---

## 📊 日志配置

### 日志级别
| 级别 | 说明 | 适用场景 |
|------|------|----------|
| `DEBUG` | 调试信息 | 开发调试 |
| `INFO` | 一般信息 | 生产环境 |
| `WARNING` | 警告信息 | 生产环境（精简） |
| `ERROR` | 错误信息 | 仅记录错误 |
| `CRITICAL` | 严重错误 | 仅记录严重问题 |

### 日志文件配置
```python
# 在 main.py 中添加日志处理器
import logging
from logging.handlers import RotatingFileHandler

# 创建轮转日志处理器
handler = RotatingFileHandler(
    'logs/app.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,           # 保留 5 个备份
)
```

---

## 🛡️ 安全配置

### 速率限制
```python
# 在 main.py 中配置
RateLimitMiddleware(
    app,
    max_requests=60,      # 最大请求数
    window_seconds=60,    # 时间窗口（秒）
)
```

### 敏感字段过滤
审计中间件自动过滤以下字段：
- `password`
- `token`
- `secret`
- `key`
- `api_key`
- `apikey`
- `access_token`
- `refresh_token`
- `private_key`
- `credential`

### 添加自定义敏感字段
```python
# 在 audit_middleware.py 中修改
SENSITIVE_FIELDS = {
    'password', 'token', 'secret', 'key',
    'your_custom_field',  # 添加自定义字段
}
```

---

## 🔔 通知配置

### 飞书通知
```ini
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx
```

### 邮件通知（待实现）
```ini
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-password
```

---

## 📦 性能优化配置

### 数据库连接池
```ini
# PostgreSQL 连接池
DATABASE_URL=postgresql://user:pass@host/db?pool_size=20&max_overflow=40
```

### API 分页限制
```python
# 在 API 端点中配置
page_size = min(max(page_size, 1), 100)  # 1-100 条/页
```

### 缓存配置（待实现）
```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

# Redis 缓存
FastAPICache.init(RedisBackend(redis), prefix="openclaw-cache")
```

---

## 🔧 故障排查

### 问题：无法启动服务
```bash
# 检查端口占用
lsof -i :8003

# 检查数据库文件权限
ls -la backend/app/*.db

# 查看日志
tail -f logs/app.log
```

### 问题：认证失败
```bash
# 检查 SECRET_KEY 是否一致
# 确保所有实例使用相同的密钥

# 检查 Token 是否过期
# Access Token 有效期由 ACCESS_TOKEN_EXPIRE_MINUTES 控制
```

### 问题：CORS 错误
```bash
# 检查 CORS_ORIGINS 配置
# 确保前端域名在允许列表中

# 检查浏览器控制台错误信息
# 常见错误：Access-Control-Allow-Origin
```

---

## 📚 相关文档

- [部署指南](deployment.md) - 生产环境部署步骤
- [API 文档](api.md) - RESTful API 接口文档
- [安全政策](../SECURITY.md) - 漏洞报告流程

---

如需帮助，请提交 [Issue](https://github.com/openclaw-enterprise/openclaw-enterprise/issues)。
