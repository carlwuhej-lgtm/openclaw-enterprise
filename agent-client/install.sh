#!/bin/bash
# OpenClaw Enterprise Agent Client - Linux/macOS 安装脚本

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🐱 OpenClaw Enterprise Agent Client 安装程序${NC}"
echo ""

# 检测操作系统
OS=$(uname -s)
ARCH=$(uname -m)

case "$OS" in
    Linux*)     OS_TYPE="linux" ;;
    Darwin*)    OS_TYPE="darwin" ;;
    *)          echo -e "${RED}❌ 不支持的操作系统: $OS${NC}"; exit 1 ;;
esac

case "$ARCH" in
    x86_64)     ARCH_TYPE="amd64" ;;
    arm64|aarch64)  ARCH_TYPE="arm64" ;;
    *)          echo -e "${RED}❌ 不支持的架构: $ARCH${NC}"; exit 1 ;;
esac

BINARY_NAME="ocw-agent"
INSTALL_DIR="/usr/local/bin"
SERVICE_NAME="ocw-agent"

echo -e "${GREEN}📋 检测到系统: $OS_TYPE / $ARCH_TYPE${NC}"

# 获取管控平台地址
read -p "请输入管控平台地址 (默认: http://localhost:8000): " SERVER_URL
SERVER_URL=${SERVER_URL:-http://localhost:8000}

# 获取上报间隔
read -p "请输入上报间隔秒数 (默认: 60): " INTERVAL
INTERVAL=${INTERVAL:-60}

echo ""
echo -e "${YELLOW}⚙️  配置信息:${NC}"
echo "  管控平台: $SERVER_URL"
echo "  上报间隔: ${INTERVAL}秒"
echo ""

read -p "确认安装? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "取消安装"
    exit 0
fi

echo ""
echo -e "${GREEN}📦 开始安装...${NC}"

# 下载二进制文件（这里假设二进制文件在当前目录或从云端下载）
if [ ! -f "$BINARY_NAME" ]; then
    echo -e "${YELLOW}⬇️  正在下载二进制文件...${NC}"
    
    # 实际部署时，这里应该从 GitHub Releases 或内部服务器下载
    # 示例: curl -L -o "$BINARY_NAME" "https://github.com/openclaw/enterprise/releases/latest/download/ocw-agent-${OS_TYPE}-${ARCH_TYPE}"
    
    echo -e "${RED}❌ 二进制文件不存在，请先编译或下载${NC}"
    exit 1
fi

# 安装二进制文件
echo -e "${YELLOW}📁 安装二进制文件到 $INSTALL_DIR${NC}"
sudo cp "$BINARY_NAME" "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/$BINARY_NAME"

# 创建配置目录
CONFIG_DIR="$HOME/.openclaw-enterprise"
mkdir -p "$CONFIG_DIR"

# 生成 Agent ID
AGENT_ID="agent-$(date +%s)-$RANDOM"

# 创建配置文件
cat > "$CONFIG_DIR/config.yaml" << EOF
server_url: $SERVER_URL
agent_id: $AGENT_ID
interval: $INTERVAL
log_level: info
EOF

echo -e "${GREEN}✅ 配置文件已创建: $CONFIG_DIR/config.yaml${NC}"

# 创建 systemd 服务 (Linux)
if [ "$OS_TYPE" = "linux" ]; then
    echo -e "${YELLOW}🔧 创建 systemd 服务${NC}"
    
    sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=OpenClaw Enterprise Agent Client
After=network.target

[Service]
Type=simple
User=$(whoami)
ExecStart=$INSTALL_DIR/$BINARY_NAME --server $SERVER_URL --interval $INTERVAL
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME
    sudo systemctl start $SERVICE_NAME
    
    echo -e "${GREEN}✅ 服务已启动${NC}"
    sudo systemctl status $SERVICE_NAME --no-pager

# 创建 launchd 服务 (macOS)
elif [ "$OS_TYPE" = "darwin" ]; then
    echo -e "${YELLOW}🔧 创建 launchd 服务${NC}"
    
    PLIST_FILE="$HOME/Library/LaunchAgents/com.openclaw.agent.plist"
    
    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/$BINARY_NAME</string>
        <string>--server</string>
        <string>$SERVER_URL</string>
        <string>--interval</string>
        <string>$INTERVAL</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/openclaw-agent.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/openclaw-agent-error.log</string>
</dict>
</plist>
EOF

    launchctl load "$PLIST_FILE"
    
    echo -e "${GREEN}✅ 服务已启动${NC}"
    launchctl list | grep com.openclaw
fi

echo ""
echo -e "${GREEN}✅ 安装完成！${NC}"
echo ""
echo -e "${YELLOW}📝 后续操作:${NC}"
echo "  • 查看日志: sudo journalctl -u $SERVICE_NAME -f  (Linux)"
echo "             tail -f /tmp/openclaw-agent.log  (macOS)"
echo "  • 停止服务: sudo systemctl stop $SERVICE_NAME  (Linux)"
echo "             launchctl unload $PLIST_FILE  (macOS)"
echo "  • 重新配置: 编辑 $CONFIG_DIR/config.yaml"
echo ""
echo -e "${GREEN}🐱 Happy Hacking!${NC}"