#!/bin/bash
# OpenClaw Enterprise 一键安装脚本 (Linux)
# 支持：Ubuntu 20.04+ / CentOS 7+ / Debian 10+
# 使用方式：curl -sSL https://.../install.sh | sudo bash

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检测操作系统
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
    else
        log_error "无法检测操作系统版本"
        exit 1
    fi
    
    log_info "检测到操作系统：$OS $VER"
}

# 检查是否以 root 运行
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用 sudo 运行此脚本"
        exit 1
    fi
}

# 检查系统要求
check_requirements() {
    log_info "检查系统要求..."
    
    # 检查内存
    MEM_TOTAL=$(free -m | awk '/^Mem:/{print $2}')
    if [ $MEM_TOTAL -lt 3000 ]; then
        log_warning "内存小于 3GB，可能影响性能"
    fi
    
    # 检查磁盘
    DISK_FREE=$(df -m / | tail -1 | awk '{print $4}')
    if [ $DISK_FREE -lt 10000 ]; then
        log_warning "磁盘空间小于 10GB"
    fi
}

# 安装系统依赖（Ubuntu/Debian）
install_deps_ubuntu() {
    log_info "安装系统依赖..."
    
    apt update
    apt install -y python3 python3-pip python3-venv python3-dev
    apt install -y postgresql postgresql-contrib
    apt install -y git curl wget
    apt install -y nginx
    
    log_success "系统依赖安装完成"
}

# 安装系统依赖（CentOS）
install_deps_centos() {
    log_info "安装系统依赖..."
    
    yum install -y epel-release
    yum install -y python3 python3-pip python3-devel
    yum install -y postgresql postgresql-server postgresql-contrib
    yum install -y git curl wget
    yum install -y nginx
    
    # 初始化 PostgreSQL
    postgresql-setup --initdb
    
    log_success "系统依赖安装完成"
}

# 创建数据库
create_database() {
    log_info "创建数据库..."
    
    # 生成随机密码
    DB_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
    
    # 启动 PostgreSQL
    systemctl start postgresql
    systemctl enable postgresql
    
    # 创建数据库和用户
    sudo -i -u postgres psql << EOF
CREATE DATABASE openclaw_enterprise;
CREATE USER openclaw WITH PASSWORD '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE openclaw_enterprise TO openclaw;
EOF
    
    # 保存密码（后续使用）
    echo "$DB_PASSWORD" > /tmp/.openclaw_db_password
    chmod 600 /tmp/.openclaw_db_password
    
    log_success "数据库创建完成"
}

# 下载项目
download_project() {
    log_info "下载项目..."
    
    INSTALL_DIR="/opt/openclaw-enterprise"
    
    # 创建目录
    mkdir -p $INSTALL_DIR
    cd $INSTALL_DIR
    
    # 下载代码
    if command -v git &> /dev/null; then
        git clone https://github.com/openclaw/openclaw-enterprise.git .
    else
        curl -L https://github.com/openclaw/openclaw-enterprise/archive/main.tar.gz | tar xz --strip-components=1
    fi
    
    log_success "项目下载完成：$INSTALL_DIR"
}

# 配置环境变量
setup_env() {
    log_info "配置环境变量..."
    
    cd /opt/openclaw-enterprise/backend
    
    # 读取数据库密码
    DB_PASSWORD=$(cat /tmp/.openclaw_db_password)
    
    # 生成密钥
    SECRET_KEY=$(openssl rand -hex 32)
    API_KEY=$(openssl rand -hex 16)
    
    # 创建 .env 文件
    cat > .env << EOF
# 数据库配置
DATABASE_URL=postgresql://openclaw:${DB_PASSWORD}@127.0.0.1:5432/openclaw_enterprise

# JWT 认证配置
SECRET_KEY=${SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_DAYS=30

# 客户端 API Key
OCW_CLIENT_API_KEY=${API_KEY}

# 服务器配置
HOST=0.0.0.0
PORT=8003
EOF
    
    chmod 600 .env
    
    log_success "环境变量配置完成"
}

# 安装 Python 依赖
install_python_deps() {
    log_info "安装 Python 依赖..."
    
    cd /opt/openclaw-enterprise/backend
    
    # 创建虚拟环境
    python3 -m venv venv
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 升级 pip
    pip install --upgrade pip
    
    # 安装依赖
    pip install -r requirements.txt
    
    log_success "Python 依赖安装完成"
}

# 初始化数据库
init_database() {
    log_info "初始化数据库..."
    
    cd /opt/openclaw-enterprise/backend
    source venv/bin/activate
    export $(cat .env | grep -v "^#" | xargs)
    
    # 创建表
    python3 -c "
from database import Base, engine
Base.metadata.create_all(bind=engine)
print('数据库表创建成功')
"
    
    log_success "数据库初始化完成"
}

# 创建 systemd 服务
create_service() {
    log_info "创建 systemd 服务..."
    
    cat > /etc/systemd/system/openclaw-enterprise.service << 'EOF'
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

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    
    # 重新加载
    systemctl daemon-reload
    
    # 启用服务
    systemctl enable openclaw-enterprise
    
    log_success "systemd 服务创建完成"
}

# 配置防火墙
setup_firewall() {
    log_info "配置防火墙..."
    
    # UFW (Ubuntu)
    if command -v ufw &> /dev/null; then
        ufw allow 8003/tcp
        ufw reload
    fi
    
    # firewalld (CentOS)
    if command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-port=8003/tcp
        firewall-cmd --reload
    fi
    
    log_success "防火墙配置完成（端口 8003）"
}

# 启动服务
start_service() {
    log_info "启动服务..."
    
    systemctl start openclaw-enterprise
    
    # 等待服务启动
    sleep 5
    
    # 检查状态
    if systemctl is-active --quiet openclaw-enterprise; then
        log_success "服务启动成功"
    else
        log_error "服务启动失败，请查看日志：journalctl -u openclaw-enterprise"
        exit 1
    fi
}

# 显示安装信息
show_info() {
    echo ""
    log_success "=========================================="
    log_success "  OpenClaw Enterprise 安装完成！"
    log_success "=========================================="
    echo ""
    
    # 获取服务器 IP
    IP_ADDR=$(hostname -I | awk '{print $1}')
    
    echo -e "${GREEN}访问地址:${NC} http://${IP_ADDR}:8003"
    echo -e "${GREEN}文档目录:${NC} /opt/openclaw-enterprise/docs"
    echo -e "${GREEN}服务状态:${NC} systemctl status openclaw-enterprise"
    echo -e "${GREEN}查看日志:${NC} journalctl -u openclaw-enterprise -f"
    echo ""
    echo -e "${YELLOW}重要提示:${NC}"
    echo "1. 首次登录请查看 /opt/openclaw-enterprise/backend/.env 获取初始密码"
    echo "2. 首次访问自动开启 30 天免费试用"
    echo "3. 生产环境请修改默认密码并配置 HTTPS"
    echo ""
    echo -e "${YELLOW}下一步:${NC}"
    echo "1. 访问 http://${IP_ADDR}:8003"
    echo "2. 阅读 /opt/openclaw-enterprise/docs/USER_MANUAL_V2.md"
    echo "3. 开始使用 30 天免费试用"
    echo ""
}

# 清理临时文件
cleanup() {
    rm -f /tmp/.openclaw_db_password
}

# 主函数
main() {
    echo ""
    echo -e "${BLUE}=========================================="
    echo "  OpenClaw Enterprise 一键安装脚本"
    echo "==========================================${NC}"
    echo ""
    
    # 检查 root
    check_root
    
    # 检测系统
    detect_os
    
    # 检查要求
    check_requirements
    
    # 安装依赖
    case $OS in
        *Ubuntu*|*Debian*)
            install_deps_ubuntu
            ;;
        *CentOS*|*RedHat*)
            install_deps_centos
            ;;
        *)
            log_error "不支持的操作系统：$OS"
            exit 1
            ;;
    esac
    
    # 创建数据库
    create_database
    
    # 下载项目
    download_project
    
    # 配置环境
    setup_env
    
    # 安装 Python 依赖
    install_python_deps
    
    # 初始化数据库
    init_database
    
    # 创建服务
    create_service
    
    # 配置防火墙
    setup_firewall
    
    # 启动服务
    start_service
    
    # 清理
    cleanup
    
    # 显示信息
    show_info
}

# 运行主函数
main
