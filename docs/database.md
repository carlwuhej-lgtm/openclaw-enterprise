# 数据库配置指南 (Database Guide)

本文档详细说明 OpenClaw Enterprise 的数据库配置。

---

## 💾 数据库选择

### 默认配置
**OpenClaw Enterprise 默认使用 SQLite 3**，无需额外安装配置。

| 特性 | SQLite | PostgreSQL |
|------|--------|------------|
| **安装** | 无需安装（Python 内置） | 需要安装 |
| **配置** | 零配置 | 需配置连接字符串 |
| **适用场景** | 开发/测试/小规模部署 | 生产环境/大规模部署 |
| **并发性能** | 一般（适合<100 用户） | 优秀（支持高并发） |
| **数据文件** | `backend/app/openclaw_enterprise.db` | PostgreSQL 服务器 |
| **备份** | 复制文件即可 | 需要 pg_dump |

---

## 🚀 快速开始（SQLite）

### 无需任何配置，直接启动：

```bash
# 1. 克隆项目
git clone https://github.com/YOUR_USERNAME/openclaw-enterprise.git
cd openclaw-enterprise

# 2. 安装依赖
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 启动服务（自动创建 SQLite 数据库）
python app/main.py
```

**数据库文件位置**：
```
backend/app/openclaw_enterprise.db
```

### SQLite 配置选项

在 `.env` 文件中配置（可选）：
```ini
# SQLite 配置（默认）
DATABASE_URL=sqlite:///./app/openclaw_enterprise.db

# 启用 WAL 模式（提高并发性能）
DATABASE_URL=sqlite:///./app/openclaw_enterprise.db?check_same_thread=false

# 自定义数据库文件路径
DATABASE_URL=sqlite:////absolute/path/to/database.db
```

---

## 🏢 生产环境部署（PostgreSQL）

### 1. 安装 PostgreSQL

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib postgresql-client
```

#### CentOS/RHEL
```bash
sudo yum install postgresql-server postgresql-contrib
sudo postgresql-setup initdb
```

#### macOS
```bash
brew install postgresql
brew services start postgresql
```

#### Docker
```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=openclaw_enterprise \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:14
```

---

### 2. 创建数据库和用户

```bash
# 切换到 postgres 用户
sudo -i -u postgres

# 登录 PostgreSQL
psql

# 在 PostgreSQL 命令行中执行：
-- 创建数据库
CREATE DATABASE openclaw_enterprise;

-- 创建用户
CREATE USER openclaw_user WITH PASSWORD 'your_secure_password';

-- 授权
GRANT ALL PRIVILEGES ON DATABASE openclaw_enterprise TO openclaw_user;

-- 退出
\q
exit
```

---

### 3. 配置连接字符串

编辑 `backend/.env` 文件：

```ini
# PostgreSQL 连接字符串
# 格式：postgresql://用户名:密码@主机:端口/数据库名

# 本地连接
DATABASE_URL=postgresql://openclaw_user:your_secure_password@localhost:5432/openclaw_enterprise

# 远程连接
DATABASE_URL=postgresql://openclaw_user:your_secure_password@192.168.1.100:5432/openclaw_enterprise

# Docker 连接
DATABASE_URL=postgresql://openclaw_user:your_secure_password@postgres:5432/openclaw_enterprise
```

---

### 4. 测试连接

```bash
cd backend
source venv/bin/activate
python -c "
from database import engine
try:
    engine.connect()
    print('✅ 数据库连接成功')
except Exception as e:
    print(f'❌ 连接失败：{e}')
"
```

---

## 📊 数据库迁移

### 从 SQLite 迁移到 PostgreSQL

```bash
# 1. 安装迁移工具
pip install sqlakeyset dataset

# 2. 导出 SQLite 数据
python scripts/migrate_sqlite_to_postgres.py

# 3. 验证数据
# 4. 切换 .env 配置到 PostgreSQL
# 5. 重启服务
```

**迁移脚本**（待实现）：
```python
# scripts/migrate_sqlite_to_postgres.py
import sqlite3
import psycopg2
from sqlalchemy import create_engine

# 连接源数据库
sqlite_conn = sqlite3.connect('app/openclaw_enterprise.db')

# 连接目标数据库
pg_conn = psycopg2.connect(
    'postgresql://user:pass@localhost/openclaw_enterprise'
)

# 迁移数据...
```

---

## 🔧 性能优化

### SQLite 优化

```ini
# .env 配置
DATABASE_URL=sqlite:///./app/openclaw_enterprise.db?timeout=30&check_same_thread=false

# 在 database.py 中添加
engine = create_engine(
    DATABASE_URL,
    connect_args={
        'timeout': 30,
        'check_same_thread': False
    }
)
```

### PostgreSQL 优化

```ini
# .env 配置（连接池）
DATABASE_URL=postgresql://user:pass@localhost/openclaw_enterprise?pool_size=20&max_overflow=40

# 或使用 URL 参数
DATABASE_URL=postgresql://user:pass@localhost/openclaw_enterprise
# 在 database.py 中配置连接池参数
```

---

## 📁 数据库备份

### SQLite 备份
```bash
# 直接复制文件
cp backend/app/openclaw_enterprise.db backup_$(date +%Y%m%d).db

# 压缩备份
tar -czf backup_$(date +%Y%m%d).tar.gz backend/app/openclaw_enterprise.db
```

### PostgreSQL 备份
```bash
# 完整备份
pg_dump -U openclaw_user openclaw_enterprise > backup_$(date +%Y%m%d).sql

# 压缩备份
pg_dump -U openclaw_user openclaw_enterprise | gzip > backup_$(date +%Y%m%d).sql.gz

# 恢复
psql -U openclaw_user openclaw_enterprise < backup_$(date +%Y%m%d).sql
```

---

## 🐛 常见问题

### Q: SQLite 和 PostgreSQL 性能差距大吗？
**A**: 
- 小规模部署（<100 并发用户）：差距不明显
- 中等规模（100-500 并发）：PostgreSQL 性能更好
- 大规模（>500 并发）：必须使用 PostgreSQL

### Q: 可以从 SQLite 切换到 PostgreSQL 吗？
**A**: 可以，需要数据迁移。我们提供迁移脚本（见上方）。

### Q: 数据库文件在哪里？
**A**: 
- SQLite: `backend/app/openclaw_enterprise.db`
- PostgreSQL: PostgreSQL 服务器数据目录

### Q: 如何查看数据库内容？
**A**: 
```bash
# SQLite
sqlite3 backend/app/openclaw_enterprise.db
.tables
SELECT * FROM audit_logs LIMIT 10;

# PostgreSQL
psql -U openclaw_user -d openclaw_enterprise
\dt
SELECT * FROM audit_logs LIMIT 10;
```

---

## 📚 相关文档

- [部署指南](deployment.md) - 完整部署步骤
- [配置说明](configuration.md) - 所有配置项说明
- [API 文档](api.md) - 数据库相关 API

---

如需帮助，请提交 [Issue](https://github.com/YOUR_USERNAME/openclaw-enterprise/issues)。
