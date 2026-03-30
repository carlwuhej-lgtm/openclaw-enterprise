#!/bin/bash
# 重启服务

echo "🔄 重启 OpenClaw Enterprise..."
./stop.sh
sleep 2
./start.sh
