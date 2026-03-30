# OpenClaw Enterprise Linux 部署手册

**版本**: 1.0.1  
**最后更新**: 2026-03-27  
**适用系统**: Linux (Ubuntu/CentOS/Debian)

---

## 📋 目录

1. [系统要求](#系统要求)
2. [快速部署](#快速部署)
3. [详细部署](#详细部署)
4. [配置说明](#配置说明)
5. [运维管理](#运维管理)
6. [故障排查](#故障排查)

---

## 系统要求

### 硬件要求

| 配置 | 最低要求 | 推荐配置 |
|------|---------|---------|
| **CPU** | 2 核 | 4 核+ |
| **内存** | 4GB | 8GB+ |
| **磁盘** | 20GB | 100GB+ SSD |
| **网络** | 10Mbps | 100Mbps+ |

### 软件要求

| 软件 | 版本 | 说明 |
|------|------|------|
| **操作系统** | Ubuntu 20.04+ / CentOS 7+ / Debian 10+ | 64 位 |
| **Python** | 3.10+ | 推荐 3.11 |
| **PostgreSQL** | 12+ | 或使用 SQLite（开发环境） |
| **Nginx** | 1.18+ | 可选，用于反向代理 |

---

## 快速部署（一键安装）

### 1. 下载安装脚本

```bash
curl -sSL https://raw.githubusercontent.com/openclaw/openclaw-enterprise/main/install.sh -o install.sh
chmod +x install.sh
```

### 2. 执行安装

```bash
sudo ./install.sh
```

安装过程约 3-5 分钟，自动完成：
- ✅ 安装 Python 3.11
- ✅ 安装 PostgreSQL
- ✅ 创建数据库和用户
- ✅ 安装依赖包
- ✅ 配置 systemd 服务
- ✅ 启动服务

### 3. 验证安装

```bash
# 检查服务状态
systemctl status openclaw-enterprise

# 查看访问地址
echo "访问地址：http://$(hostname -I | awk '{print $1}'):8003"
```

### 4. 首次登录

访问 `http://服务器 IP:8003`

**默认账号**:
- 用户名：`admin`
- 密码：安装时设置

---

## 详细部署（手动安装）

### 步骤 1: 安装系统依赖

#### Ubuntu/Debian

```bash
# 更新软件源
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y python3.11 python3.11-venv python3-pip git curl wget

# 安装 PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# 安装 Nginx（可选）
sudo apt install -y nginx
```

#### CentOS/RHEL

```bash
# 安装 EPEL 源
sudo yum install -y epel-release

# 安装基础工具
sudo yum install -y python3.11 python3-devel git curl wget

# 安装 PostgreSQL
sudo yum install -y postgresql postgresql-server postgresql-contrib

# 初始化 PostgreSQL（首次安装）
sudo postgresql-setup --initdb

# 安装 Nginx（可选）
sudo yum install -y nginx
```

---

### 步骤 2: 创建数据库

```bash
# 切换到 postgres 用户
sudo -i -u postgres

# 进入 PostgreSQL
psql

# 执行 SQL 命令
CREATE DATABASE openclaw_enterprise;
CREATE USER openclaw WITH PASSWORD '你的强密码_至少 16 位';
GRANT ALL PRIVILEGES ON DATABASE openclaw_enterprise TO openclaw;
\q

# 退出 postgres 用户
exit
```

---

### 步骤 3: 下载项目

```bash
# 创建应用目录
sudo mkdir -p /opt/openclaw-enterprise
cd /opt/openclaw-enterprise

# 下载代码（选择一种方式）

# 方式 1: Git 克隆
sudo git clone https://github.com/openclaw/openclaw-enterprise.git .

# 方式 2: 下载压缩包
sudo curl -L https://github.com/openclaw/openclaw-enterprise/archive/main.tar.gz | sudo tar xz --strip-components=1
```

---

### 步骤 4: 配置环境变量

```bash
# 进入 backend 目录
cd /opt/openclaw-enterprise/backend

# 创建 .env 文件
sudo tee .env > /dev/null << 'EOF'
# 数据库配置
DATABASE_URL=postgresql://openclaw:你的强密码_至少 16 位@127.0.0.1:5432/openclaw_enterprise

# JWT 认证配置
SECRET_KEY=$(openssl rand -hex 32)
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_DAYS=30

# 客户端 API Key（Agent 上报使用）
OCW_CLIENT_API_KEY=$(openssl rand -hex 16)

# 服务器配置
HOST=0.0.0.0
PORT=8003
EOF

# 设置文件权限
sudo chmod 600 .env
```

---

### 步骤 5: 安装 Python 依赖

```bash
cd /opt/openclaw-enterprise/backend

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

---

### 步骤 6: 初始化数据库

```bash
cd /opt/openclaw-enterprise/backend
source venv/bin/activate

# 加载环境变量
export $(cat .env | grep -v "^#" | xargs)

# 执行数据库迁移（如果有）
# alembic upgrade head

# 或者手动创建表
python3 -c "
from database import Base, engine
Base.metadata.create_all(bind=engine)
print('✅ 数据库表创建成功')
"
```

---

### 步骤 7: 创建 systemd 服务

```bash
# 创建服务文件
sudo tee /etc/systemd/system/openclaw-enterprise.service > /dev/null << 'EOF'
[Unit]
Description=OpenClaw Enterprise API Service
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/openclaw-enterprise/backend
Environment="PATH=/opt/openclaw-enterprise/backend/venv/bin"
ExecStart=/opt/openclaw-enterprise/backend/venv/bin/python app/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=openclaw-enterprise

# 安全配置
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable openclaw-enterprise

# 启动服务
sudo systemctl start openclaw-enterprise

# 查看状态
sudo systemctl status openclaw-enterprise
```

---

### 步骤 8: 配置防火墙

```bash
# Ubuntu (UFW)
sudo ufw allow 8003/tcp
sudo ufw reload

# CentOS (firewalld)
sudo firewall-cmd --permanent --add-port=8003/tcp
sudo firewall-cmd --reload

# 或者使用 iptables
sudo iptables -A INPUT -p tcp --dport 8003 -j ACCEPT
```

---

### 步骤 9: 配置 Nginx 反向代理（可选）

```bash
# 创建 Nginx 配置
sudo tee /etc/nginx/sites-available/openclaw-enterprise > /dev/null << 'EOF'
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://127.0.0.1:8003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时配置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # 缓冲配置
        proxy_buffering off;
    }

    # 静态文件（如果有）
    location /static {
        alias /opt/openclaw-enterprise/backend/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# 启用站点
sudo ln -s /etc/nginx/sites-available/openclaw-enterprise /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
```

---

## 配置说明

### 环境变量详解

**.env 文件**:

```bash
# ==================== 数据库配置 ====================
# PostgreSQL 连接字符串
# 格式：postgresql://用户名:密码@主机:端口/数据库名
DATABASE_URL=postgresql://openclaw:password@127.0.0.1:5432/openclaw_enterprise

# ==================== JWT 认证配置 ====================
# JWT 密钥（用于签名 token）
# 生产环境必须使用随机生成的 64 位密钥
SECRET_KEY=你的 64 位随机密钥

# JWT 算法
ALGORITHM=HS256

# Token 过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24 小时
REFRESH_TOKEN_EXPIRE_DAYS=30

# ==================== 客户端 API Key ====================
# Agent 客户端上报使用的 API Key
OCW_CLIENT_API_KEY=你的 API Key

# ==================== 服务器配置 ====================
# 监听地址
HOST=0.0.0.0

# 监听端口
PORT=8003

# 工作进程数
WORKERS=4
```

### 生成安全密钥

```bash
# 生成 SECRET_KEY（64 位）
openssl rand -hex 32

# 生成 API Key（32 位）
openssl rand -hex 16

# 生成密码（16 位）
openssl rand -base64 24
```

---

## 运维管理

### 服务管理

```bash
# 启动服务
sudo systemctl start openclaw-enterprise

# 停止服务
sudo systemctl stop openclaw-enterprise

# 重启服务
sudo systemctl restart openclaw-enterprise

# 查看状态
sudo systemctl status openclaw-enterprise

# 查看日志
sudo journalctl -u openclaw-enterprise -f

# 禁用开机自启
sudo systemctl disable openclaw-enterprise
```

### 日志管理

```bash
# 查看应用日志
sudo journalctl -u openclaw-enterprise -f

# 查看最近 100 行
sudo journalctl -u openclaw-enterprise -n 100

# 按时间查看
sudo journalctl -u openclaw-enterprise --since "2026-03-27 10:00:00"

# 导出日志
sudo journalctl -u openclaw-enterprise --since today > /tmp/openclaw.log
```

### 数据库备份

```bash
#!/bin/bash
# backup.sh - 数据库备份脚本

BACKUP_DIR="/var/backups/openclaw"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="openclaw_enterprise"
DB_USER="openclaw"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# 删除 30 天前的备份
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +30 -delete

echo "✅ 备份完成：$BACKUP_DIR/backup_$DATE.sql.gz"
```

**添加到 crontab**:
```bash
# 每天凌晨 2 点备份
0 2 * * * /opt/openclaw-enterprise/backup.sh
```

### 系统更新

```bash
# 1. 备份数据库
/opt/openclaw-enterprise/backup.sh

# 2. 停止服务
sudo systemctl stop openclaw-enterprise

# 3. 更新代码
cd /opt/openclaw-enterprise
sudo git pull

# 4. 更新依赖
cd backend
source venv/bin/activate
pip install -r requirements.txt

# 5. 执行迁移（如果有）
# alembic upgrade head

# 6. 重启服务
sudo systemctl start openclaw-enterprise

# 7. 验证
curl http://localhost:8003/api/health
```

---

## 故障排查

### 问题 1: 服务无法启动

**检查 systemd 状态**:
```bash
sudo systemctl status openclaw-enterprise
sudo journalctl -u openclaw-enterprise -n 50
```

**常见原因**:
1. 端口被占用
2. 数据库连接失败
3. 依赖包缺失
4. 权限问题

**解决方法**:
```bash
# 检查端口占用
sudo lsof -i :8003

# 测试数据库连接
psql -h 127.0.0.1 -U openclaw -d openclaw_enterprise -c "SELECT 1"

# 重新安装依赖
cd /opt/openclaw-enterprise/backend
source venv/bin/activate
pip install -r requirements.txt --force-reinstall
```

---

### 问题 2: 数据库连接失败

**错误信息**:
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**检查步骤**:
```bash
# 1. 检查 PostgreSQL 状态
sudo systemctl status postgresql

# 2. 检查数据库是否存在
psql -U postgres -c "\l" | grep openclaw

# 3. 检查用户权限
psql -U postgres -c "\du" | grep openclaw

# 4. 检查 .env 配置
cat /opt/openclaw-enterprise/backend/.env | grep DATABASE
```

**解决方法**:
```bash
# 重启 PostgreSQL
sudo systemctl restart postgresql

# 重新创建用户
sudo -i -u postgres
psql
DROP USER IF EXISTS openclaw;
CREATE USER openclaw WITH PASSWORD '新密码';
GRANT ALL PRIVILEGES ON DATABASE openclaw_enterprise TO openclaw;
\q
exit

# 更新 .env 文件
sudo nano /opt/openclaw-enterprise/backend/.env
```

---

### 问题 3: 内存不足

**错误信息**:
```
Killed
```

**检查内存**:
```bash
free -h
top
```

**解决方法**:
```bash
# 1. 增加 Swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2. 限制工作进程数
# 编辑 .env 文件
WORKERS=2

# 3. 优化数据库
sudo -i -u postgres
psql
VACUUM ANALYZE;
\q
```

---

### 问题 4: 磁盘空间不足

**检查磁盘**:
```bash
df -h
du -sh /opt/openclaw-enterprise/*
```

**清理日志**:
```bash
# 清理 systemd 日志（保留最近 7 天）
sudo journalctl --vacuum-time=7d

# 清理 PostgreSQL 日志
sudo find /var/log/postgresql -name "*.log" -mtime +30 -delete

# 清理应用日志
sudo find /var/log -name "openclaw*" -mtime +30 -delete
```

**扩容方案**:
```bash
# 1. 添加新磁盘
# 2. 挂载到 /var/lib/postgresql
# 3. 移动数据目录
sudo systemctl stop postgresql
sudo rsync -av /var/lib/postgresql/ /mnt/newdisk/postgresql/
sudo mount --bind /mnt/newdisk/postgresql /var/lib/postgresql
sudo systemctl start postgresql
```

---

### 问题 5: 无法访问 Web 界面

**检查步骤**:
```bash
# 1. 检查服务状态
sudo systemctl status openclaw-enterprise

# 2. 检查防火墙
sudo ufw status
# 或
sudo firewall-cmd --list-all

# 3. 检查端口监听
sudo netstat -tlnp | grep 8003

# 4. 本地测试
curl http://localhost:8003/api/health
```

**解决方法**:
```bash
# 开放端口
sudo ufw allow 8003/tcp
# 或
sudo firewall-cmd --permanent --add-port=8003/tcp
sudo firewall-cmd --reload

# 检查 Nginx 配置
sudo nginx -t
sudo systemctl restart nginx
```

---

## 安全加固

### 1. 修改默认端口

```bash
# 编辑 .env 文件
PORT=18789

# 重启服务
sudo systemctl restart openclaw-enterprise

# 更新防火墙
sudo ufw allow 18789/tcp
sudo ufw delete allow 8003/tcp
```

### 2. 配置 HTTPS

```bash
# 使用 Let's Encrypt
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

### 3. 限制访问 IP

```nginx
# Nginx 配置
location / {
    allow 192.168.1.0/24;  # 内网
    allow 10.0.0.0/8;      # 内网
    deny all;              # 拒绝其他
    
    proxy_pass http://127.0.0.1:8003;
}
```

### 4. 定期更新

```bash
# 每周检查更新
sudo apt update && sudo apt upgrade -y

# 每月更新系统
sudo unattended-upgrades
```

---

## 性能优化

### 1. 数据库优化

```sql
-- 添加索引
CREATE INDEX CONCURRENTLY idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX CONCURRENTLY idx_alerts_created ON alerts(created_at DESC);

-- 定期清理
VACUUM ANALYZE;
```

### 2. 启用缓存

```bash
# 安装 Redis
sudo apt install -y redis-server

# 配置缓存
# 编辑 backend/app/main.py
# 添加 Redis 缓存配置
```

### 3. 调整工作进程

```bash
# 根据 CPU 核心数调整
# 编辑 .env 文件
WORKERS=4  # CPU 核心数 * 2 + 1
```

---

## 监控告警

### 1. 系统监控

```bash
# 安装监控工具
sudo apt install -y htop iotop nethogs

# 查看资源使用
htop
```

### 2. 应用监控

```bash
# 查看 API 健康
curl http://localhost:8003/api/health

# 查看 Prometheus 指标
curl http://localhost:8003/api/health/metrics
```

### 3. 日志告警

```bash
# 创建监控脚本
sudo tee /opt/openclaw-enterprise/monitor.sh > /dev/null << 'EOF'
#!/bin/bash

# 检查服务状态
if ! systemctl is-active --quiet openclaw-enterprise; then
    echo "⚠️ 服务异常，尝试重启..."
    systemctl restart openclaw-enterprise
    # 发送告警邮件/短信
fi

# 检查磁盘空间
usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $usage -gt 90 ]; then
    echo "⚠️ 磁盘使用率：${usage}%"
    # 发送告警
fi
EOF

chmod +x /opt/openclaw-enterprise/monitor.sh

# 添加到 crontab（每 5 分钟检查一次）
*/5 * * * * /opt/openclaw-enterprise/monitor.sh
```

---

## 附录

### A. 常用命令速查

```bash
# 服务管理
systemctl start|stop|restart|status openclaw-enterprise

# 日志查看
journalctl -u openclaw-enterprise -f

# 数据库备份
pg_dump -U openclaw -h localhost openclaw_enterprise > backup.sql

# 数据库恢复
psql -U openclaw -h localhost openclaw_enterprise < backup.sql

# 更新系统
cd /opt/openclaw-enterprise && sudo git pull
sudo systemctl restart openclaw-enterprise
```

### B. 目录结构

```
/opt/openclaw-enterprise/
├── backend/
│   ├── app/              # 应用代码
│   ├── venv/             # Python 虚拟环境
│   ├── .env              # 环境配置
│   └── requirements.txt  # 依赖列表
├── frontend/
│   └── pages/            # 前端页面
├── docs/                 # 文档
├── backup.sh             # 备份脚本
└── monitor.sh            # 监控脚本
```

### C. 默认端口

| 服务 | 端口 | 说明 |
|------|------|------|
| OpenClaw API | 8003 | 主服务端口 |
| PostgreSQL | 5432 | 数据库端口 |
| Nginx | 80/443 | Web 服务器 |

---

**文档版本**: 1.0.1  
**最后更新**: 2026-03-27  
**技术支持**: support@openclaw.ai
