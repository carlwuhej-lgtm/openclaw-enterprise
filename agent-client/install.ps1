# OpenClaw Enterprise Agent Client - Windows 安装脚本
# 使用 PowerShell 执行

$ErrorActionPreference = "Stop"

Write-Host "🐱 OpenClaw Enterprise Agent Client 安装程序" -ForegroundColor Green
Write-Host ""

# 检测架构
$ARCH = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture

if ($ARCH -eq "X64") {
    $ARCH_TYPE = "amd64"
} elseif ($ARCH -eq "Arm64") {
    $ARCH_TYPE = "arm64"
} else {
    Write-Host "❌ 不支持的架构: $ARCH" -ForegroundColor Red
    exit 1
}

Write-Host "📋 检测到系统: Windows / $ARCH_TYPE" -ForegroundColor Green

# 获取管控平台地址
$SERVER_URL = Read-Host "请输入管控平台地址 (默认: http://localhost:8000)"
if ([string]::IsNullOrWhiteSpace($SERVER_URL)) {
    $SERVER_URL = "http://localhost:8000"
}

# 获取上报间隔
$INTERVAL_STR = Read-Host "请输入上报间隔秒数 (默认: 60)"
if ([string]::IsNullOrWhiteSpace($INTERVAL_STR)) {
    $INTERVAL = 60
} else {
    $INTERVAL = [int]$INTERVAL_STR
}

Write-Host ""
Write-Host "⚙️  配置信息:" -ForegroundColor Yellow
Write-Host "  管控平台: $SERVER_URL"
Write-Host "  上报间隔: ${INTERVAL}秒"
Write-Host ""

$CONFIRM = Read-Host "确认安装? (y/n)"
if ($CONFIRM -ne "y") {
    Write-Host "取消安装"
    exit 0
}

Write-Host ""
Write-Host "📦 开始安装..." -ForegroundColor Green

# 安装路径
$INSTALL_DIR = "$env:ProgramFiles\OpenClaw"
$BINARY_NAME = "ocw-agent.exe"
$SERVICE_NAME = "OpenClawAgent"

# 创建安装目录
Write-Host "📁 创建安装目录: $INSTALL_DIR" -ForegroundColor Yellow
if (!(Test-Path $INSTALL_DIR)) {
    New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
}

# 检查二进制文件
$BINARY_PATH = ".\$BINARY_NAME"
if (!(Test-Path $BINARY_PATH)) {
    Write-Host "❌ 二进制文件不存在，请先编译或下载: $BINARY_PATH" -ForegroundColor Red
    exit 1
}

# 复制二进制文件
Write-Host "📁 安装二进制文件到 $INSTALL_DIR" -ForegroundColor Yellow
Copy-Item $BINARY_PATH "$INSTALL_DIR\" -Force

# 创建配置目录
$CONFIG_DIR = "$env:LOCALAPPDATA\OpenClaw"
if (!(Test-Path $CONFIG_DIR)) {
    New-Item -ItemType Directory -Path $CONFIG_DIR -Force | Out-Null
}

# 生成 Agent ID
$AGENT_ID = "agent-$([int](([DateTime]::UtcNow.Ticks - 621355968000000000) / 10000000))-$((Get-Random -Maximum 99999))"

# 创建配置文件
$CONFIG_PATH = "$CONFIG_DIR\config.yaml"
@"
server_url: $SERVER_URL
agent_id: $AGENT_ID
interval: $INTERVAL
log_level: info
"@ | Out-File -FilePath $CONFIG_PATH -Encoding UTF8

Write-Host "✅ 配置文件已创建: $CONFIG_PATH" -ForegroundColor Green

# 创建 Windows 服务
Write-Host "🔧 创建 Windows 服务" -ForegroundColor Yellow

# 检查是否已存在服务
$existing = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "⚠️  服务已存在，正在移除..." -ForegroundColor Yellow
    Stop-Service -Name $SERVICE_NAME -Force
    sc.exe delete $SERVICE_NAME | Out-Null
    Start-Sleep -Seconds 2
}

# 创建服务 (使用 sc.exe)
$BINARY_FULL_PATH = "$INSTALL_DIR\$BINARY_NAME"
$SERVICE_CMD = "`"$BINARY_FULL_PATH`" --server $SERVER_URL --interval $INTERVAL"

$cmd = "sc.exe create $SERVICE_NAME binPath= `"$SERVICE_CMD`" start= auto DisplayName= `"OpenClaw Enterprise Agent`""
Invoke-Expression $cmd

Write-Host "✅ 服务已创建" -ForegroundColor Green

# 启动服务
Write-Host "🚀 启动服务..." -ForegroundColor Yellow
Start-Service -Name $SERVICE_NAME

# 检查服务状态
$status = Get-Service -Name $SERVICE_NAME
if ($status.Status -eq "Running") {
    Write-Host "✅ 服务已启动" -ForegroundColor Green
} else {
    Write-Host "❌ 服务启动失败" -ForegroundColor Red
    Write-Host "状态: $($status.Status)"
    exit 1
}

Write-Host ""
Write-Host "✅ 安装完成！" -ForegroundColor Green
Write-Host ""
Write-Host "📝 后续操作:" -ForegroundColor Yellow
Write-Host "  • 查看日志: Get-EventLog -LogName Application -Source $SERVICE_NAME -Newest 10"
Write-Host "  • 停止服务: Stop-Service -Name $SERVICE_NAME"
Write-Host "  • 启动服务: Start-Service -Name $SERVICE_NAME"
Write-Host "  • 重新配置: 编辑 $CONFIG_PATH"
Write-Host ""
Write-Host "🐱 Happy Hacking!" -ForegroundColor Green