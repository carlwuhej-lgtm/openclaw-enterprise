#!/bin/bash
# OpenClaw Enterprise 安装脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🚀 OpenClaw Enterprise 安装程序"
echo "==============================="
echo ""

# 检查 Python 版本
echo "📋 检查系统要求..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 未安装${NC}"
    echo "请安装 Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "${RED}❌ Python 版本过低：$PYTHON_VERSION${NC}"
    echo "请安装 Python 3.10+"
    exit 1
fi
echo -e "${GREEN}✅ Python $PYTHON_VERSION${NC}"

# 创建虚拟环境
echo ""
echo "📦 创建虚拟环境..."
if [ -d "venv" ]; then
    echo -e "${YELLOW}⚠️  虚拟环境已存在，跳过${NC}"
else
    python3 -m venv venv
    echo -e "${GREEN}✅ 虚拟环境创建完成${NC}"
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo ""
echo "📦 安装依赖..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "${GREEN}✅ 依赖安装完成${NC}"

# 创建 .env 文件（如果不存在）
echo ""
echo "⚙️  配置环境变量..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✅ 已创建 .env 文件（使用默认配置）${NC}"
    echo -e "${YELLOW}ℹ️  提示：生产环境请修改 .env 中的 SECRET_KEY${NC}"
else
    echo -e "${GREEN}✅ .env 文件已存在${NC}"
fi

# 创建日志目录
mkdir -p logs

# 初始化数据库
echo ""
echo "📊 初始化数据库..."
export $(cat .env | grep -v "^#" | xargs)
python3 -c "
from app.database import Base, engine, SessionLocal
from app.models import User, Tenant
from app.auth import get_password_hash

Base.metadata.create_all(bind=engine)

db = SessionLocal()
tenant = db.query(Tenant).filter(Tenant.name=='default').first()
if not tenant:
    tenant = Tenant(name='default', description='默认租户')
    db.add(tenant)
    db.commit()

admin = db.query(User).filter(User.username=='admin').first()
if not admin:
    admin = User(
        username='admin',
        hashed_password=get_password_hash('admin'),
        real_name='系统管理员',
        email='admin@openclaw.local',
        tenant_id=tenant.id if tenant else 1,
        role='admin',
        is_active=True
    )
    db.add(admin)
    db.commit()
    print('✅ 创建默认管理员账号：admin / admin')

db.close()
"
echo -e "${GREEN}✅ 数据库初始化完成${NC}"

# 完成
echo ""
echo "================================"
echo -e "${GREEN}✅ 安装完成！${NC}"
echo ""
echo "🚀 启动服务：./start.sh"
echo "📖 查看文档：docs/README.md"
echo "🔐 默认账号：admin / admin"
echo ""
