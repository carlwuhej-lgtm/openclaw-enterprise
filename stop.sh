#!/bin/bash
# 停止服务

echo "🛑 停止 OpenClaw Enterprise..."

# 停止应用
pkill -f "python.*app/main.py" 2>/dev/null && echo "✅ 应用已停止" || echo "⚠️ 应用未运行"

# 不自动停止 Gateway（可能其他服务在用）
# openclaw gateway stop

echo "✅ 停止完成"
