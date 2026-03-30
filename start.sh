#!/bin/bash
# OpenClaw Enterprise 快速启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 OpenClaw Enterprise"
echo "======================"
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ 虚拟环境不存在${NC}"
    echo "请先运行安装脚本：./install.sh"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env 文件不存在${NC}"
    echo "请创建 .env 文件："
    echo "  cp .env.example .env"
    echo "  # 然后编辑 .env 配置环境变量"
    exit 1
fi

# 加载环境变量
export $(cat .env | grep -v "^#" | xargs)

# 检查 PostgreSQL
echo "📊 检查数据库连接..."
if ! python3 -c "from app.database import engine; engine.connect()" 2>/dev/null; then
    echo -e "${RED}❌ 数据库连接失败${NC}"
    echo "请检查:"
    echo "  1. PostgreSQL 是否运行：sudo systemctl status postgresql"
    echo "  2. .env 中的 DATABASE_URL 是否正确"
    exit 1
fi
echo -e "${GREEN}✅ 数据库连接正常${NC}"

# 检查 OpenClaw Gateway
echo "🚪 检查 Gateway 状态..."
if command -v openclaw &> /dev/null; then
    if openclaw gateway status | grep -q "running"; then
        echo -e "${GREEN}✅ Gateway 运行中${NC}"
    else
        echo -e "${YELLOW}⚠️ Gateway 未运行，正在启动...${NC}"
        openclaw gateway start
        sleep 2
    fi
else
    echo -e "${YELLOW}⚠️ OpenClaw 未安装，跳过 Gateway 检查${NC}"
fi

# 启动服务
echo ""
echo "🚀 启动 OpenClaw Enterprise..."

# 检查是否已运行
if pgrep -f "python.*app/main.py" > /dev/null; then
    echo -e "${YELLOW}⚠️ 服务已在运行${NC}"
    read -p "是否重启？(y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkill -f "python.*app/main.py"
        sleep 1
    else
        echo "✅ 服务保持运行"
        exit 0
    fi
fi

# 启动
nohup python3 app/main.py > ../logs/app.log 2>&1 &
APP_PID=$!

sleep 3

# 验证启动
if curl -s http://localhost:8003/api/stats > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 服务启动成功！${NC}"
    echo ""
    echo "📋 访问信息:"
    echo "   管理后台：http://localhost:8003"
    echo "   API 文档：http://localhost:8003/docs"
    echo "   进程 PID: $APP_PID"
    echo ""
    echo "📖 常用命令:"
    echo "   停止服务：./stop.sh"
    echo "   查看日志：tail -f logs/app.log"
    echo "   重启服务：./restart.sh"
else
    echo -e "${RED}❌ 服务启动失败${NC}"
    echo "查看日志：tail -f logs/app.log"
    exit 1
fi
