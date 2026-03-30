# OpenClaw Enterprise 部署手册

**版本**: v1.0.0  
**更新日期**: 2026-03-26  
**部署方式**: 本地私有化部署

---

## 📋 目录

1. [系统概述](#系统概述)
2. [系统架构](#系统架构)
3. [环境要求](#环境要求)
4. [安装部署](#安装部署)
5. [配置说明](#配置说明)
6. [服务管理](#服务管理)
7. [日志管理](#日志管理)
8. [备份恢复](#备份恢复)
9. [安全加固](#安全加固)
10. [故障排查](#故障排查)
11. [常见问题](#常见问题)

---

## 系统概述

### 功能模块

| 模块 | 功能 | 端口 |
|------|------|------|
| **OpenClaw Gateway** | AI Agent 网关服务 | 18789 |
| **Enterprise Backend** | 企业管控平台后端 | 8003 |
| **Enterprise Frontend** | 企业管控平台前端 | - |
| **Syslog Server** | 日志接收服务 | 1514 |

### 核心功能

- ✅ AI Agent 安全管理
- ✅ 操作审计日志
- ✅ 安全策略管控
- ✅ 网络扫描发现
- ✅ 主机监控
- ✅ 日志转发（ELK/Splunk）
- ✅ 急救室自动诊断

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    客户端访问层                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  Web 浏览器 │  │  飞书机器人│  │  API 客户端 │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
└───────┼─────────────┼─────────────┼─────────────────────┘
        │             │             │
┌───────▼─────────────▼─────────────▼─────────────────────┐
│              OpenClaw Enterprise (端口 8003)              │
│  ┌─────────────────────────────────────────────────┐    │
│  │  FastAPI Backend + SQLite Database              │    │
│  │  - 用户认证 (JWT)                               │    │
│  │  - 设备管理                                     │    │
│  │  - Agent 管理                                    │    │
│  │  - 审计日志                                     │    │
│  │  - 安全策略                                     │    │
│  │  - 日志转发                                     │    │
│  └─────────────────────────────────────────────────┘    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              OpenClaw Gateway (端口 18789)               │
│  - Agent 执行引擎                                        │
│  - 技能调用                                             │
│  - 会话管理                                             │
└─────────────────────────────────────────────────────────┘
```

---

## 环境要求

### 硬件要求

| 规模 | CPU | 内存 | 磁盘 | 并发用户 |
|------|-----|------|------|---------|
| **小型** | 2 核 | 4GB | 50GB | < 50 |
| **中型** | 4 核 | 8GB | 100GB | < 200 |
| **大型** | 8 核 | 16GB | 500GB | < 1000 |

### 软件要求

| 组件 | 版本 | 说明 |
|------|------|------|
| **操作系统** | Ubuntu 20.04+ / CentOS 7+ / Debian 10+ | 64 位 Linux |
| **Python** | 3.10+ | 后端运行环境 |
| **Node.js** | 18+ | OpenClaw Gateway |
| **数据库** | SQLite 3 (内置) | 系统自带或手动安装 |

### 数据库要求

#### 🎯 数据库选择建议

| 部署规模 | 推荐数据库 | 理由 |
|---------|-----------|------|
| **小型 (< 50 用户)** | **SQLite** | ✅ 零配置、免维护、单文件、易备份 |
| **中型 (50-200 用户)** | **SQLite** 或 **PostgreSQL** | 根据并发量选择 |
| **大型 (> 200 用户)** | **PostgreSQL** | ✅ 高并发、集群支持、性能更好 |

#### 数据库对比

| 特性 | SQLite | PostgreSQL | MySQL |
|------|--------|------------|-------|
| **安装复杂度** | ⭐ 无需安装 | ⭐⭐⭐ 需单独安装 | ⭐⭐ 需单独安装 |
| **维护成本** | ⭐ 零维护 | ⭐⭐⭐ 需要 DBA | ⭐⭐ 需要维护 |
| **并发性能** | ⭐⭐ 一般 | ⭐⭐⭐⭐ 优秀 | ⭐⭐⭐ 良好 |
| **备份难度** | ⭐ 复制文件即可 | ⭐⭐ 需要工具 | ⭐⭐ 需要工具 |
| **数据一致性** | ⭐⭐⭐⭐ 强 | ⭐⭐⭐⭐⭐ 最强 | ⭐⭐⭐⭐ 强 |
| **适用场景** | 小型部署 | 企业级部署 | 通用场景 |

#### 我们的建议

**✅ 强烈推荐和本地部署一样的数据库（PostgreSQL），原因：**

1. **生产验证** - 本地已在用，稳定可靠
2. **高性能** - 支持高并发，适合企业场景
3. **易维护** - 成熟的数据库，工具丰富
4. **易扩展** - 未来支持集群、读写分离
5. **数据一致** - 和本地环境完全一致

**⚠️ 不推荐 SQLite，除非：**

- 测试环境
- 单机 < 20 用户
- 临时演示

**当前版本默认支持 PostgreSQL**，SQLite 需修改配置。

### 网络要求

| 端口 | 协议 | 用途 | 是否开放 |
|------|------|------|---------|
| 8003 | TCP | 企业管控平台 Web | 是 |
| 18789 | TCP | OpenClaw Gateway | 否 (仅本地) |
| 1514 | UDP/TCP | Syslog 日志接收 | 可选 |

---

## 安装部署

### 步骤 1: 准备环境

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian
# 或
sudo yum update -y  # CentOS

# 安装依赖
sudo apt install -y python3 python3-pip python3-venv nodejs npm git curl sqlite3

# 验证版本
python3 --version  # 应 >= 3.10
node --version     # 应 >= 18
sqlite3 --version  # 应 >= 3.30
```

### 步骤 1.5: 安装 PostgreSQL（必需）

**本地部署使用 PostgreSQL，请按以下步骤安装：**

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# CentOS/RHEL
sudo yum install -y postgresql postgresql-server
sudo postgresql-setup --initdb  # 仅 CentOS 首次需要

# 启动 PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 验证安装
psql --version  # 应 >= 12
sudo systemctl status postgresql
```

### 步骤 1.6: 配置数据库

```bash
# 切换到 postgres 用户
sudo -i -u postgres

# 创建数据库
psql << 'EOF'
CREATE DATABASE openclaw_enterprise;
CREATE USER openclaw WITH PASSWORD '123456.a';
GRANT ALL PRIVILEGES ON DATABASE openclaw_enterprise TO openclaw;
ALTER DATABASE openclaw_enterprise OWNER TO openclaw;
\q
EOF

# 退出 postgres 用户
exit

# 安装 Python 驱动
source /opt/openclaw-enterprise/venv/bin/activate
pip install psycopg2-binary

# 验证连接
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise -c "SELECT 1;"
```

### 步骤 1.7: 配置数据库连接

编辑 `backend/app/database.py` 或设置环境变量：

```bash
# 方法 1: 环境变量（推荐）
echo "DATABASE_URL=postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise" >> /opt/openclaw-enterprise/backend/.env

# 方法 2: 直接修改 database.py
# 编辑 /opt/openclaw-enterprise/backend/app/database.py
# 修改 DATABASE_URL 变量
```

---

### 可选：SQLite（仅测试用）

**如果是测试环境，可以用 SQLite：**

```bash
# 安装 SQLite
sudo apt install -y sqlite3

# 修改 database.py
# DATABASE_URL = "sqlite:///./enterprise.db"
```

### 步骤 2: 部署 OpenClaw Gateway

```bash
# 安装 OpenClaw
sudo npm install -g openclaw

# 初始化配置
mkdir -p ~/.openclaw
openclaw init

# 启动 Gateway
openclaw gateway start

# 验证服务
curl http://localhost:18789/api/status
```

### 步骤 3: 初始化数据库

```bash
cd /opt/openclaw-enterprise/backend

# 方法 1: 自动初始化（启动时自动创建）
python3 app/main.py &
sleep 3
curl http://localhost:8003/api/stats

# 方法 2: 手动初始化
python3 << 'EOF'
import sys
sys.path.insert(0, 'app')
from database import Base, engine
from models import Tenant, User, Device

# 创建所有表
Base.metadata.create_all(bind=engine)

# 创建默认租户
from sqlalchemy.orm import Session
db = Session()

tenant = Tenant(name="默认租户", code="default", description="系统默认租户")
db.add(tenant)
db.commit()

admin = User(
    username="admin",
    real_name="系统管理员",
    email="admin@localhost",
    tenant_id=tenant.id,
    role="admin"
)
db.add(admin)
db.commit()

print("✅ 数据库初始化完成")
print(f"默认管理员账号：admin / admin")
db.close()
EOF

# 验证数据库
sqlite3 app/enterprise.db ".tables"
sqlite3 app/enterprise.db "SELECT COUNT(*) FROM tenants;"
```

### 步骤 4: 部署 Enterprise 管控平台

```bash
# 1. 克隆项目
cd /opt
git clone <your-repo-url> openclaw-enterprise
cd openclaw-enterprise

# 2. 创建 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r backend/requirements.txt

# 4. 配置数据库（见步骤 3）

# 5. 配置 systemd 服务 (见下文)
```

### 步骤 4: 配置 systemd 服务

创建服务文件：

```bash
sudo tee /etc/systemd/system/openclaw-enterprise.service > /dev/null << 'EOF'
[Unit]
Description=OpenClaw Enterprise Backend
After=network.target openclaw-gateway.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/openclaw-enterprise/backend
Environment="PATH=/opt/openclaw-enterprise/venv/bin"
ExecStart=/opt/openclaw-enterprise/venv/bin/python3 app/main.py
Restart=always
RestartSec=10

# 安全配置
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# 重载 systemd
sudo systemctl daemon-reload

# 启用并启动服务
sudo systemctl enable openclaw-enterprise
sudo systemctl start openclaw-enterprise

# 查看状态
sudo systemctl status openclaw-enterprise
```

### 步骤 5: 配置 Nginx 反向代理 (可选)

```bash
sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/openclaw > /dev/null << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    # 企业管控平台
    location / {
        proxy_pass http://127.0.0.1:8003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # OpenClaw Gateway (可选)
    location /gateway/ {
        proxy_pass http://127.0.0.1:18789/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# 启用配置
sudo ln -s /etc/nginx/sites-available/openclaw /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 配置说明

### 环境变量配置

创建 `.env` 文件：

```bash
# /opt/openclaw-enterprise/backend/.env

# OpenClaw Gateway Token
OPENCLAW_GATEWAY_TOKEN=your-token-here

# 阿里云百炼 API Key
ALIYUN_API_KEY=sk-xxxxxxxxxxxxxxxx

# Tavily API Key (可选)
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx

# OpenRouter API Key (可选)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx

# 飞书凭证 (可选)
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx

# 日志转发配置
SYSLOG_HOST=192.168.1.100
SYSLOG_PORT=514
SYSLOG_PROTOCOL=udp
```

### openclaw.json 配置

```json
{
  "gateway": {
    "port": 18789,
    "mode": "local",
    "bind": "loopback"
  },
  "models": {
    "providers": {
      "bailian": {
        "baseUrl": "https://dashscope.aliyuncs.com/api/v1",
        "apiKey": "${ALIYUN_API_KEY}"
      }
    }
  },
  "agents": {
    "list": [
      {
        "id": "daily",
        "name": "日常助手",
        "model": "bailian/qwen-plus"
      },
      {
        "id": "security",
        "name": "安全专家",
        "model": "bailian/qwen-plus"
      }
    ]
  }
}
```

---

## 服务管理

### 启动/停止/重启

```bash
# OpenClaw Gateway
openclaw gateway start
openclaw gateway stop
openclaw gateway restart

# Enterprise Backend
sudo systemctl start openclaw-enterprise
sudo systemctl stop openclaw-enterprise
sudo systemctl restart openclaw-enterprise

# Nginx (如果配置了)
sudo systemctl restart nginx
```

### 查看日志

```bash
# Enterprise Backend
sudo journalctl -u openclaw-enterprise -f

# OpenClaw Gateway
tail -f /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log

# Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 健康检查

```bash
# 检查 Gateway
curl http://localhost:18789/api/status

# 检查 Enterprise
curl http://localhost:8003/api/stats

# 检查数据库
sqlite3 /opt/openclaw-enterprise/backend/app/enterprise.db "SELECT COUNT(*) FROM devices;"
```

---

## 数据库管理

### 数据库连接信息

```bash
# PostgreSQL 连接信息
主机：127.0.0.1
端口：5432
数据库：openclaw_enterprise
用户：openclaw
密码：123456.a

# 连接字符串
postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise
```

### 数据库初始化

```bash
cd /opt/openclaw-enterprise/backend

# 自动创建表（首次启动时）
source venv/bin/activate
python3 app/main.py

# 或手动初始化
python3 << 'EOF'
import sys
sys.path.insert(0, 'app')
from database import Base, engine
from models import Tenant, User

# 创建所有表
Base.metadata.create_all(bind=engine)

# 创建默认数据
from sqlalchemy.orm import Session
db = Session()

tenant = Tenant(name="默认租户", code="default")
db.add(tenant)
db.commit()

admin = User(username="admin", real_name="系统管理员", role="admin", tenant_id=tenant.id)
db.add(admin)
db.commit()

print("✅ 数据库初始化完成")
print("默认管理员：admin / admin")
db.close()
EOF
```

### 数据库备份

```bash
# 方法 1: pg_dump（推荐）
pg_dump postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise \
   > /backup/openclaw_$(date +%Y%m%d_%H%M%S).sql

# 方法 2: 压缩备份
pg_dump postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise | \
   gzip > /backup/openclaw_$(date +%Y%m%d_%H%M%S).sql.gz

# 方法 3: 仅结构备份
pg_dump -s postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise \
   > /backup/openclaw_schema_$(date +%Y%m%d).sql

# 定时备份（添加到 crontab）
0 2 * * * pg_dump postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise | gzip > /backup/openclaw_$(date +\%Y\%m\%d).sql.gz
```

### 数据库恢复

```bash
# 停止服务
sudo systemctl stop openclaw-enterprise

# 方法 1: 从 SQL 文件恢复
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise \
   < /backup/openclaw_20260326_120000.sql

# 方法 2: 从压缩文件恢复
gunzip -c /backup/openclaw_20260326_120000.sql.gz | \
   psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise

# 启动服务
sudo systemctl start openclaw-enterprise
```

### 数据库优化

```bash
# 清理旧数据（保留 90 天审计日志）
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise << 'EOF'
DELETE FROM audit_logs WHERE timestamp < NOW() - INTERVAL '90 days';
DELETE FROM syslog_entries WHERE timestamp < NOW() - INTERVAL '30 days';
VACUUM ANALYZE;
EOF

# 查看数据库大小
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise -c \
   "SELECT pg_size_pretty(pg_database_size('openclaw_enterprise'));"

# 查看表大小
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise -c \
   "SELECT relname AS table_name, pg_size_pretty(pg_total_relation_size(relid)) AS total_size FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;"

# 检查数据库健康状态
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise -c \
   "SELECT datname, numbackends, xact_commit, xact_rollback FROM pg_stat_database WHERE datname = 'openclaw_enterprise';"
```

### 数据库监控

```bash
# 查看连接数
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise -c \
   "SELECT count(*) as active_connections FROM pg_stat_activity WHERE datname = 'openclaw_enterprise';"

# 查看慢查询（需要开启 pg_stat_statements）
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise -c \
   "SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# 查看锁状态
psql postgresql://openclaw:123456.a@127.0.0.1:5432/openclaw_enterprise -c \
   "SELECT pid, usename, state, query FROM pg_stat_activity WHERE datname = 'openclaw_enterprise' AND state != 'idle';"

# 查看 PostgreSQL 日志
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### PostgreSQL 性能调优（可选）

编辑 `/etc/postgresql/*/main/postgresql.conf`：

```conf
# 内存配置（根据服务器配置调整）
shared_buffers = 256MB          # 推荐物理内存的 25%
effective_cache_size = 1GB      # 推荐物理内存的 50-75%
work_mem = 10MB                 # 每个排序/哈希操作
maintenance_work_mem = 128MB    # VACUUM/CREATE INDEX 使用

# 连接配置
max_connections = 100           # 最大连接数

# WAL 配置
wal_buffers = 16MB
checkpoint_completion_target = 0.9

# 日志配置
log_min_duration_statement = 1000  # 记录超过 1 秒的查询
log_checkpoints = on
log_connections = on
log_disconnections = on
```

重启 PostgreSQL：
```bash
sudo systemctl restart postgresql
```

---

## 日志管理

### 日志位置

| 日志类型 | 路径 | 轮转 |
|---------|------|------|
| **Gateway** | `/tmp/openclaw/openclaw-YYYY-MM-DD.log` | 按天 |
| **Enterprise** | `/opt/openclaw-enterprise/backend/logs/` | 手动 |
| **Nginx** | `/var/log/nginx/` | 按天 |
| **Syslog** | 数据库存储 | 手动清理 |

### 日志轮转配置

创建 logrotate 配置：

```bash
sudo tee /etc/logrotate.d/openclaw-enterprise > /dev/null << 'EOF'
/opt/openclaw-enterprise/backend/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data www-data
    postrotate
        systemctl reload openclaw-enterprise > /dev/null 2>&1 || true
    endscript
}
EOF
```

### 日志清理

```bash
# 清理 30 天前的日志
find /opt/openclaw-enterprise/backend/logs -name "*.log" -mtime +30 -delete

# 清理 Gateway 日志
find /tmp/openclaw -name "openclaw-*.log" -mtime +7 -delete
```

---

## 备份恢复

### 数据备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/openclaw"
DATE=$(date +%Y%m%d_%H%M%S)
DB_FILE="/opt/openclaw-enterprise/backend/app/enterprise.db"
CONFIG_DIR="/opt/openclaw-enterprise/backend"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
cp $DB_FILE $BACKUP_DIR/enterprise_$DATE.db

# 备份配置文件
tar -czf $BACKUP_DIR/config_$DATE.tar.gz \
    $CONFIG_DIR/.env \
    ~/.openclaw/openclaw.json

# 删除 30 天前的备份
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "备份完成：$BACKUP_DIR"
```

### 数据恢复

```bash
# 停止服务
sudo systemctl stop openclaw-enterprise

# 恢复数据库
cp /backup/openclaw/enterprise_20260326_120000.db \
   /opt/openclaw-enterprise/backend/app/enterprise.db

# 恢复配置
tar -xzf /backup/openclaw/config_20260326_120000.tar.gz -C /

# 启动服务
sudo systemctl start openclaw-enterprise
```

### 定时备份

```bash
# 添加到 crontab
crontab -e

# 每天凌晨 2 点备份
0 2 * * * /opt/openclaw-enterprise/bin/backup.sh
```

---

## 安全加固

### 防火墙配置

```bash
# UFW (Ubuntu)
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 1514/udp  # Syslog (可选)
sudo ufw enable

# firewalld (CentOS)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --permanent --add-port=1514/udp
sudo firewall-cmd --reload
```

### 修改默认密码

```bash
# 登录管控平台后
1. 进入"系统设置" → "用户管理"
2. 修改 admin 用户密码
3. 删除或禁用默认测试账号
```

### HTTPS 配置

```bash
# 使用 Let's Encrypt
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

### 访问控制

```nginx
# Nginx 访问控制
location / {
    # 允许特定 IP
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;
    
    proxy_pass http://127.0.0.1:8003;
}
```

---

## 故障排查

### Gateway 无法启动

```bash
# 检查端口占用
sudo lsof -i :18789

# 查看日志
tail -f /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log

# 重启 Gateway
openclaw gateway restart
```

### 后端服务异常

```bash
# 检查服务状态
sudo systemctl status openclaw-enterprise

# 查看日志
sudo journalctl -u openclaw-enterprise -n 100

# 检查数据库
sqlite3 /opt/openclaw-enterprise/backend/app/enterprise.db ".tables"

# 重启服务
sudo systemctl restart openclaw-enterprise
```

### 无法访问 Web 界面

```bash
# 检查 Nginx
sudo nginx -t
sudo systemctl status nginx

# 检查端口
sudo netstat -tlnp | grep :80
sudo netstat -tlnp | grep :8003

# 检查防火墙
sudo ufw status
```

### 数据库锁定

```bash
# 查找锁定进程
sudo lsof /opt/openclaw-enterprise/backend/app/enterprise.db

# 备份后重建
cp enterprise.db enterprise.db.bak
sqlite3 enterprise.db ".dump" | sqlite3 enterprise.db.new
mv enterprise.db.new enterprise.db
```

---

## 常见问题

### Q1: 端口 8003 被占用

**解决**:
```bash
# 查找占用进程
sudo lsof -i :8003

# 修改端口
# 编辑 backend/app/main.py，修改 uvicorn.run 的 port 参数
```

### Q2: 日志转发不工作

**检查**:
1. 确认目标服务器防火墙允许 514 端口
2. 测试连接：`nc -zv target-host 514`
3. 检查转发配置是否启用
4. 查看后端日志是否有发送错误

### Q3: Agent 无法执行命令

**检查**:
1. Gateway 是否正常运行：`openclaw gateway status`
2. 检查 API Key 配置是否正确
3. 查看 Gateway 日志是否有错误
4. 确认模型配额是否充足

### Q4: 数据库过大

**解决**:
```bash
# 清理旧日志
sqlite3 enterprise.db "DELETE FROM audit_logs WHERE timestamp < datetime('now', '-90 days');"
sqlite3 enterprise.db "DELETE FROM syslog_entries WHERE timestamp < datetime('now', '-30 days');"

# 压缩数据库
sqlite3 enterprise.db "VACUUM;"
```

### Q5: 内存占用过高

**解决**:
```bash
# 重启服务
sudo systemctl restart openclaw-enterprise
openclaw gateway restart

# 限制日志量
# 修改日志保留天数配置
```

---

## 技术支持

- **文档**: `/opt/openclaw-enterprise/docs/`
- **日志**: `/var/log/openclaw/`
- **配置**: `~/.openclaw/openclaw.json`

---

**部署完成！访问 `http://your-server-ip:8003` 开始使用。** 🎉
