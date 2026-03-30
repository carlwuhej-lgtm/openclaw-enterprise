# OpenClaw Enterprise - 部署指南

## 环境要求

### 最低配置
- CPU: 2 核
- 内存：4GB
- 存储：20GB
- 系统：Linux/macOS/Windows

### 推荐配置
- CPU: 4 核
- 内存：8GB
- 存储：50GB SSD
- 系统：Ubuntu 22.04 LTS

---

## 快速开始

### 1. 下载项目
```bash
# 解压项目
unzip openclaw-enterprise-project.zip
cd openclaw-enterprise
```

### 2. 启动服务

**macOS/Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```bash
start.bat
```

### 3. 访问系统
- 前端：http://localhost:8000/pages/dashboard
- API 文档：http://localhost:8000/docs

---

## Docker 部署

### 1. 构建镜像
```bash
docker build -t openclaw/enterprise:latest .
```

### 2. 运行容器
```bash
docker run -d \
  -p 8000:8000 \
  -v ./data:/app/data \
  --name openclaw-enterprise \
  openclaw/enterprise:latest
```

### 3. Docker Compose
```yaml
version: '3.8'

services:
  app:
    image: openclaw/enterprise:latest
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite:///./data/openclaw.db
    restart: unless-stopped
```

---

## 生产环境部署

### 1. 数据库配置 (PostgreSQL)

**安装 PostgreSQL:**
```bash
# Ubuntu
sudo apt install postgresql postgresql-contrib

# macOS
brew install postgresql
```

**创建数据库:**
```bash
createdb openclaw_enterprise
```

**配置连接:**
```python
# 修改 backend/app/main.py
DATABASE_URL = "postgresql://user:password@localhost/openclaw_enterprise"
```

### 2. Nginx 反向代理

**安装 Nginx:**
```bash
sudo apt install nginx
```

**配置 Nginx:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**重启 Nginx:**
```bash
sudo systemctl restart nginx
```

### 3. HTTPS 配置

**使用 Let's Encrypt:**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### 4. 系统服务 (systemd)

**创建服务文件:**
```bash
sudo nano /etc/systemd/system/openclaw.service
```

**内容:**
```ini
[Unit]
Description=OpenClaw Enterprise
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/openclaw-enterprise/backend
Environment="PATH=/opt/openclaw-enterprise/backend/venv/bin"
ExecStart=/opt/openclaw-enterprise/backend/venv/bin/python app/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**启动服务:**
```bash
sudo systemctl enable openclaw
sudo systemctl start openclaw
sudo systemctl status openclaw
```

---

## 监控与日志

### 1. 日志配置

**应用日志:**
```python
# 修改 backend/app/main.py
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('openclaw.log'),
        logging.StreamHandler()
    ]
)
```

### 2. 接入 ELK

**Filebeat 配置:**
```yaml
filebeat.inputs:
- type: log
  paths:
    - /var/log/openclaw/*.log

output.elasticsearch:
  hosts: ["http://elasticsearch:9200"]
```

### 3. Prometheus 监控

**metrics 端点:**
```python
from prometheus_fastapi_instrumentator import Instrumentator

instrumentator.instrument(app).expose(app)
```

---

## 备份与恢复

### 1. 数据库备份

**SQLite:**
```bash
cp openclaw_enterprise.db openclaw_enterprise.db.backup.$(date +%Y%m%d)
```

**PostgreSQL:**
```bash
pg_dump openclaw_enterprise > backup.sql
psql openclaw_enterprise < backup.sql
```

### 2. 定期备份 (cron)
```bash
# 每天凌晨 2 点备份
0 2 * * * /opt/openclaw-enterprise/backup.sh
```

---

## 故障排查

### 1. 服务无法启动
```bash
# 检查端口占用
lsof -i :8000

# 检查日志
tail -f openclaw.log
```

### 2. 数据库连接失败
```bash
# 检查数据库文件
ls -la *.db

# 检查 PostgreSQL 状态
systemctl status postgresql
```

### 3. 前端无法访问
```bash
# 检查 Nginx 配置
nginx -t

# 检查 Nginx 日志
tail -f /var/log/nginx/error.log
```

---

## 性能优化

### 1. 数据库优化
```sql
-- 添加索引
CREATE INDEX idx_device_status ON devices(status);
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_alert_level ON alerts(level);
```

### 2. 缓存配置
```python
# 使用 Redis 缓存
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

@cache(expire=60)
async def get_stats():
    # ...
```

### 3. 异步处理
```python
# 使用 Celery 处理耗时任务
@app.post("/api/devices/scan")
async def scan_devices():
    scan_task.delay()
    return {"message": "扫描任务已启动"}
```

---

## 安全加固

### 1. 防火墙配置
```bash
# 仅开放必要端口
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 2. 访问控制
```python
# 添加认证中间件
@app.middleware("http")
async def auth_middleware(request, call_next):
    token = request.headers.get("Authorization")
    if not validate_token(token):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)
```

### 3. 速率限制
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/api/devices")
@limiter.limit("100/minute")
async def get_devices(request: Request):
    # ...
```

---

**文档版本**: v1.0  
**创建日期**: 2026-03-20
