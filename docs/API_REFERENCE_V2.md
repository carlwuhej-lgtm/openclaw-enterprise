# OpenClaw Enterprise API 文档

**版本**: 1.0.0  
**基础 URL**: `http://localhost:8003`  
**认证方式**: Bearer Token (JWT)

---

## 📖 目录

1. [认证授权](#认证授权)
2. [实例管理](#实例管理)
3. [Agent 管理](#agent 管理)
4. [安全管控](#安全管控)
5. [审计日志](#审计日志)
6. [告警管理](#告警管理)
7. [健康检查](#健康检查)
8. [License 管理](#license 管理)

---

## 认证授权

### 获取 Token

```http
POST /api/token
Content-Type: application/x-www-form-urlencoded

username=admin&password=your_password
```

**响应**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### 使用 Token

在所有 API 请求的 Header 中添加：
```
Authorization: Bearer YOUR_ACCESS_TOKEN
```

---

## 实例管理

### 获取设备列表

```http
GET /api/devices?page=1&page_size=20&status=online
Authorization: Bearer YOUR_TOKEN
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20，最大 500 |
| status | string | 否 | 状态筛选：online/offline/warning/violation |
| search | string | 否 | 搜索关键词 |

**响应**:
```json
{
  "items": [
    {
      "id": 1,
      "name": "开发部 - 张三的电脑",
      "hostname": "zhangsan-mbp",
      "ip_address": "192.168.1.100",
      "status": "online",
      "risk_level": "low",
      "risk_score": 15,
      "version": "1.0.0",
      "created_at": "2026-03-27T10:00:00"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### 创建设备

```http
POST /api/devices
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "name": "测试设备",
  "hostname": "test-host",
  "version": "1.0.0",
  "tenant_id": 1,
  "user_id": 1
}
```

### 批量删除设备

```http
POST /api/devices/batch-delete
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "ids": [1, 2, 3, 4, 5]
}
```

**响应**:
```json
{
  "success": true,
  "deleted_count": 5,
  "failed": [],
  "message": "成功删除 5 台设备"
}
```

### 批量更新设备状态

```http
POST /api/devices/batch-update-status
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "ids": [1, 2, 3],
  "status": "offline"
}
```

---

## Agent 管理

### 获取 Agent 列表

```http
GET /api/agents?page=1&page_size=20
Authorization: Bearer YOUR_TOKEN
```

### 创建 Agent

```http
POST /api/agents
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "agent_id": "daily",
  "name": "日常助手",
  "device_id": 1,
  "model": "bailian/glm-5",
  "workspace": "/Users/user/.openclaw/agents/daily",
  "status": "running"
}
```

### 启动 Agent

```http
POST /api/agents/{agent_id}/start
Authorization: Bearer YOUR_TOKEN
```

### 停止 Agent

```http
POST /api/agents/{agent_id}/stop
Authorization: Bearer YOUR_TOKEN
```

---

## 安全管控

### 获取策略列表

```http
GET /api/policies?page=1&page_size=20
Authorization: Bearer YOUR_TOKEN
```

### 创建策略

```http
POST /api/policies
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "name": "敏感目录保护",
  "description": "禁止访问敏感目录",
  "is_enabled": true,
  "config": {
    "type": "path_block",
    "paths": ["/etc", "/root", "/.ssh"],
    "action": "block"
  }
}
```

### 更新策略

```http
PUT /api/policies/{policy_id}
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "name": "敏感目录保护（更新）",
  "is_enabled": false
}
```

---

## 审计日志

### 获取审计日志

```http
GET /api/audit-logs?page=1&page_size=50&operation_type=command_exec&risk_level=high
Authorization: Bearer YOUR_TOKEN
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码 |
| page_size | int | 否 | 每页数量 |
| operation_type | string | 否 | 操作类型 |
| risk_level | string | 否 | 风险级别 |
| status | string | 否 | 状态：allowed/blocked |
| start_date | string | 否 | 开始时间 (ISO 8601) |
| end_date | string | 否 | 结束时间 (ISO 8601) |

### 导出审计日志

```http
GET /api/audit-logs/export?format=csv&start_date=2026-03-01&end_date=2026-03-31
Authorization: Bearer YOUR_TOKEN
```

**响应**: CSV 文件下载

---

## 告警管理

### 获取告警列表

```http
GET /api/alerts?page=1&page_size=20&status=unresolved&level=critical
Authorization: Bearer YOUR_TOKEN
```

### 创建告警

```http
POST /api/alerts
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "title": "检测到高危操作",
  "description": "用户尝试执行 rm -rf /",
  "level": "critical",
  "device_id": 1
}
```

### 解决告警

```http
POST /api/alerts/{alert_id}/resolve
Authorization: Bearer YOUR_TOKEN
```

### 批量解决告警

```http
POST /api/alerts/batch-resolve
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "ids": [1, 2, 3, 4, 5]
}
```

### 批量删除告警

```http
POST /api/alerts/batch-delete
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "ids": [1, 2, 3]
}
```

---

## 健康检查

### 完整健康检查

```http
GET /api/health
```

**响应**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "timestamp": "2026-03-27T15:00:00",
  "checks": {
    "database": {
      "status": "up",
      "latency_ms": 1.5,
      "tables": {
        "devices": 10,
        "alerts": 50,
        "audit_logs": 1000
      }
    },
    "disk": {
      "status": "ok",
      "total_gb": 500,
      "used_gb": 200,
      "usage_percent": 40.0
    },
    "memory": {
      "status": "ok",
      "total_gb": 16,
      "used_gb": 8,
      "usage_percent": 50.0
    },
    "cpu": {
      "status": "ok",
      "usage_percent": 20.0,
      "cores": 8
    },
    "agents": {
      "status": "ok",
      "total": 5,
      "running": 5,
      "stopped": 0
    }
  }
}
```

### Kubernetes 存活探针

```http
GET /api/health/live
```

### Kubernetes 就绪探针

```http
GET /api/health/ready
```

### Prometheus 指标

```http
GET /api/health/metrics
```

**响应** (Prometheus 格式):
```
# HELP openclaw_devices_total Total number of devices
# TYPE openclaw_devices_total gauge
openclaw_devices_total 10

# HELP openclaw_alerts_total Total number of alerts
# TYPE openclaw_alerts_total gauge
openclaw_alerts_total 50

# HELP openclaw_memory_usage_percent Memory usage percentage
# TYPE openclaw_memory_usage_percent gauge
openclaw_memory_usage_percent 50.0
```

---

## License 管理

### 获取 License 信息

```http
GET /api/license
Authorization: Bearer YOUR_TOKEN
```

**响应**:
```json
{
  "plan": "pro",
  "features": [
    "基础监控",
    "审计日志",
    "告警通知",
    "AI 分析",
    "PDF 报告",
    "策略引擎",
    "多租户"
  ],
  "agents": {
    "used": 3,
    "max": 50,
    "available": 47,
    "percent": 6.0
  },
  "devices": {
    "used": 5,
    "max": 20,
    "available": 15,
    "percent": 25.0
  },
  "key": "OCW-PRO-***",
  "activated_at": "2026-03-01T10:00:00",
  "trial_days_left": null
}
```

### 激活 License

```http
POST /api/license/activate
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "key": "OCW-PRO-XXXX-XXXX"
}
```

**响应**:
```json
{
  "success": true,
  "plan": "pro",
  "message": "✅ PRO 套餐激活成功",
  "expires_at": null,
  "trial_days_left": null
}
```

### 开始试用

```http
POST /api/license/trial
Authorization: Bearer YOUR_TOKEN
```

**响应**:
```json
{
  "success": true,
  "message": "✅ 14 天试用期已开启",
  "trial_days_left": 14,
  "expires_at": "2026-04-10T15:00:00"
}
```

### 获取使用情况

```http
GET /api/license/usage
Authorization: Bearer YOUR_TOKEN
```

---

## 错误码说明

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或 Token 过期 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 423 | License 限制 |
| 500 | 服务器内部错误 |

---

## 限流说明

| 接口类型 | 限流 |
|----------|------|
| 认证接口 | 10 次/分钟 |
| 数据查询 | 100 次/分钟 |
| 数据写入 | 50 次/分钟 |
| 批量操作 | 10 次/分钟 |

---

**API 版本**: 1.0.0  
**最后更新**: 2026-03-27  
**文档地址**: https://docs.openclaw.ai/api
