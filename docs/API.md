# API 文档 (API Reference)

OpenClaw Enterprise RESTful API 接口文档。

**Base URL**: `http://localhost:8003/api`

---

## 🔐 认证接口

### POST /auth/login
用户登录

**请求**
```json
{
  "username": "admin",
  "password": "your-password"
}
```

**响应**
```json
{
  "success": true,
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin"
  }
}
```

---

### POST /auth/register
用户注册

**请求**
```json
{
  "username": "newuser",
  "password": "strong-password",
  "real_name": "Real Name",
  "email": "user@example.com"
}
```

---

### GET /auth/me
获取当前用户信息

**请求头**
```
Authorization: Bearer <access_token>
```

---

## 📋 审计日志接口

### GET /audit-logs
获取审计日志列表

**参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码（默认 1） |
| `page_size` | int | 每页数量（1-100，默认 20） |
| `search` | string | 关键词搜索 |
| `operation_type` | string | 操作类型过滤 |
| `risk_level` | string | 风险级别过滤 |
| `status` | string | 状态过滤 |
| `start_date` | string | 开始日期（ISO 格式） |
| `end_date` | string | 结束日期（ISO 格式） |

**响应**
```json
{
  "items": [
    {
      "id": 1,
      "operation_type": "api_create",
      "operation_detail": "POST /api/auth/login",
      "risk_level": "safe",
      "status": "allowed",
      "timestamp": "2026-03-27T10:00:00"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

---

### DELETE /audit-logs/{log_id}
删除单条审计日志

**权限**: Admin

---

### POST /audit-logs/clear
批量清理旧日志

**请求**
```json
{
  "before_date": "2026-01-01"
}
```

**限制**
- 只能删除 30 天前的日志
- 单次最多删除 10000 条
- 清理操作本身会被记录

---

## 💻 设备管理接口

### GET /devices
获取设备列表

**参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码 |
| `page_size` | int | 每页数量 |
| `status` | string | 状态过滤 |
| `search` | string | 关键词搜索 |

---

### GET /devices/{device_id}
获取单个设备详情

---

### POST /devices
创建设备

**请求**
```json
{
  "name": "My Device",
  "hostname": "hostname",
  "version": "1.0.0",
  "tenant_id": 1
}
```

---

### DELETE /devices/{device_id}
删除设备（级联删除关联数据）

---

## 🚨 告警接口

### GET /alerts
获取告警列表

**参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | `resolved` / `unresolved` |
| `search` | string | 关键词搜索 |

---

### POST /alerts/{alert_id}/resolve
解决告警

---

### POST /alerts/batch-resolve
批量解决告警

**请求**
```json
{
  "ids": [1, 2, 3]
}
```

---

## 🛡️ 策略接口

### GET /policies
获取安全策略列表

---

### POST /policies
创建策略

**请求**
```json
{
  "name": "禁止访问敏感目录",
  "description": "阻止访问 ~/.ssh 等路径",
  "config": "{\"paths\": [\"~/.ssh\"]}",
  "is_enabled": true
}
```

---

### PUT /policies/{policy_id}
更新策略

---

### POST /policies/{policy_id}/toggle
切换策略启用状态

---

## 📊 统计接口

### GET /stats
获取统计数据

**响应**
```json
{
  "total_devices": 10,
  "online_devices": 8,
  "pending_approvals": 2,
  "critical_alerts": 1,
  "today_audit_logs": 150,
  "weekly_new_devices": 3,
  "weekly_trend": [
    {"date": "03-21", "count": 20},
    {"date": "03-22", "count": 25}
  ]
}
```

---

## 🔍 网络扫描接口

### POST /scan/start
启动网络扫描

**请求**
```json
{
  "target": "192.168.1.0/24",
  "ports": [22, 80, 443]
}
```

---

### GET /scan/status/{scan_id}
获取扫描状态

---

## 📈 流量分析接口

### GET /traffic/stats
获取流量统计

---

### GET /traffic/top-agents
获取活跃 Agent 排行

---

## 🤖 Agent 接口

### GET /agents
获取 Agent 列表

---

### GET /agents/{agent_id}
获取 Agent 详情

---

### POST /agents/{agent_id}/restart
重启 Agent

---

## 📝 通用响应格式

### 成功响应
```json
{
  "success": true,
  "message": "操作成功",
  "data": {}
}
```

### 错误响应
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数验证失败",
    "details": []
  }
}
```

---

## 🔑 认证说明

### 请求头格式
```
Authorization: Bearer <access_token>
```

### Token 获取
1. 调用 `/api/auth/login` 获取 access_token
2. 将 token 添加到请求头
3. Token 过期后使用 refresh_token 刷新

### Token 刷新
```bash
POST /api/auth/refresh
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

---

## 📚 相关文档

- [配置说明](configuration.md) - 环境变量配置
- [部署指南](deployment.md) - 生产环境部署
- [安全政策](../SECURITY.md) - 漏洞报告流程

---

如需帮助，请提交 [Issue](https://github.com/openclaw-enterprise/openclaw-enterprise/issues)。
