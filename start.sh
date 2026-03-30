#!/bin/bash
# OpenClaw Enterprise 快速启动脚本（支持 SQLite 默认配置）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🚀 OpenClaw Enterprise"
echo "======================"
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  虚拟环境不存在，正在创建...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt -q
    echo -e "${GREEN}✅ 虚拟环境创建完成${NC}"
else
    source venv/bin/activate
fi

# 设置默认环境变量（如果没有 .env 文件）
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env 文件不存在，使用默认配置（SQLite）${NC}"
    export DATABASE_URL="sqlite:///./app/openclaw_enterprise.db"
    export SECRET_KEY="openclaw-enterprise-default-secret-key-for-development-only"
    export LOG_LEVEL="INFO"
    export TIMEZONE="Asia/Shanghai"
    export PORT="8003"
else
    # 加载 .env 配置
    export $(cat .env | grep -v "^#" | xargs)
fi

# 确保数据库目录存在
mkdir -p app

# 检查是否已运行
if pgrep -f "python.*app/main.py" > /dev/null; then
    echo -e "${YELLOW}⚠️  服务已在运行${NC}"
    read -p "是否重启？(y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "✅ 服务保持运行"
        exit 0
    fi
    pkill -f "python.*app/main.py"
    sleep 1
fi

# 创建日志目录
mkdir -p logs

# 启动服务
echo ""
echo "🚀 启动 OpenClaw Enterprise..."
nohup python3 app/main.py > logs/app.log 2>&1 &
APP_PID=$!

sleep 3

# 验证启动
if curl -s http://localhost:${PORT:-8003}/api/stats > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 服务启动成功！${NC}"
    echo ""
    echo "📋 访问信息:"
    echo "   管理后台：http://localhost:${PORT:-8003}"
    echo "   API 文档：http://localhost:${PORT:-8003}/docs"
    echo "   进程 PID: $APP_PID"
    echo ""
    echo "🔐 默认账号:"
    echo "   用户名：admin"
    echo "   密码：admin"
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
