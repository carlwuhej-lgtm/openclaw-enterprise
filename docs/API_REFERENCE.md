# OpenClaw Enterprise API 参考文档

**版本**: v1.0.0  
**更新日期**: 2026-03-26

---

## 认证方式

所有 API 请求需要在 Header 中添加：

```
Authorization: Bearer <your_jwt_token>
```

获取 Token：`POST /api/auth/login`

---

## API 端点

### AI 分析

#### POST /api/ai/analyze/operation

**Analyze Operation**

分析操作

---

#### GET /api/ai/analyze/anomalies

**Get Anomalies**

获取异常告警 - 从数据库读取真实数据（按租户过滤）

---

#### GET /api/ai/analyze/risk/{device_ip}

**Get Risk Score**

获取风险评分

---

#### GET /api/ai/analyze/risk-scores

**Get All Risk Scores**

获取所有设备风险评分 - 从数据库读取真实数据（按租户过滤）

---

#### GET /api/ai/analyze/profile/{device_ip}

**Get Profile**

获取行为画像

---

#### GET /api/ai/analyze/statistics

**Get Statistics**

获取统计信息 - 从数据库读取真实数据（按租户过滤）

---

#### POST /api/ai/respond/configure

**Configure Action**

配置自动响应

---

#### POST /api/ai/respond/process

**Process Anomaly**

处理异常

---

### Agent 管理

#### POST /api/agent/install

**Install Agent**

安装 Agent

---

#### POST /api/agent/uninstall

**Uninstall Agent**

卸载 Agent

---

#### POST /api/agent/start

**Start Agent**

启动 Agent

---

#### POST /api/agent/stop

**Stop Agent**

停止 Agent

---

#### GET /api/agent/status

**Get Agent Status**

获取 Agent 状态

---

#### GET /api/agent/processes

**Detect Processes**

检测 OpenClaw 进程

---

#### GET /api/agent/connections

**Detect Connections**

检测 LLM 连接

---

#### POST /api/agent/kill

**Kill Process**

终止进程

---

#### GET /api/agent/violations

**Get Violations**

获取策略违规

---

### Agent 管理模块

#### GET /api/agents

**List Agents**

获取 Agent 列表（分页 + 设备过滤 + 租户隔离）

---

#### POST /api/agents

**Create Agent**

创建 Agent

---

#### GET /api/agents/{agent_id_int}

**Get Agent**

获取 Agent 详情

---

#### PUT /api/agents/{agent_id_int}

**Update Agent**

更新 Agent

---

#### DELETE /api/agents/{agent_id_int}

**Delete Agent**

删除 Agent

---

#### POST /api/agents/{agent_id_int}/start

**Start Agent**

启动 Agent

---

#### POST /api/agents/{agent_id_int}/stop

**Stop Agent**

停止 Agent

---

#### GET /api/agents/{agent_id_int}/heartbeat

**Get Heartbeat**

获取 Agent 心跳状态

---

#### POST /api/agents/batch

**Batch Import Agents**

批量导入 Agent — 从设备的 openclaw 配置自动发现并导入所有 agent

---

### License

#### GET /api/license

**Get License Info**

获取当前 License 信息

---

#### POST /api/license/activate

**Activate License**

激活 License Key

---

### Other

#### GET /api/devices/{device_id}

**Get Device**

获取单个设备

---

#### DELETE /api/devices/{device_id}

**Delete Device**

删除设备（支持级联删除关联的审计日志、告警和 Agent）

---

#### GET /

**Root**

---

#### GET /api/stats

**Get Stats**

获取统计数据（按租户过滤）

---

#### GET /api/devices

**Get Devices**

获取所有设备（分页，按租户过滤）

---

#### POST /api/devices

**Create Device**

创建设备

---

#### GET /api/audit-logs

**Get Audit Logs**

获取审计日志（分页，按租户过滤，支持多条件筛选）

---

#### GET /api/alerts

**Get Alerts**

获取告警（分页，按租户过滤）

---

#### POST /api/alerts

**Create Alert**

---

#### GET /api/tenants

**Get Tenants**

获取租户（分页，非 admin 只看自己的租户）

---

#### POST /api/tenants

**Create Tenant**

---

#### GET /api/users

**Get Users**

获取用户（分页，按租户过滤）

---

#### POST /api/users

**Create User**

---

#### GET /api/policies

**Get Policies**

获取安全策略（分页）

---

#### POST /api/policies

**Create Policy**

---

#### PUT /api/policies/{policy_id}

**Update Policy**

更新安全策略

---

#### DELETE /api/policies/{policy_id}

**Delete Policy**

---

#### GET /api/alerts/{alert_id}

**Get Alert**

---

#### PUT /api/alerts/{alert_id}

**Update Alert**

---

#### DELETE /api/alerts/{alert_id}

**Delete Alert**

---

#### POST /api/alerts/{alert_id}/resolve

**Resolve Alert**

---

#### POST /api/alerts/batch-resolve

**Batch Resolve Alerts**

---

#### GET /api/audit-logs/{log_id}

**Get Audit Log**

---

#### DELETE /api/audit-logs/{log_id}

**Delete Audit Log**

---

#### POST /api/audit-logs/clear

**Clear Audit Logs**

---

#### GET /api/tenants/{tenant_id}

**Get Tenant**

---

#### PUT /api/tenants/{tenant_id}

**Update Tenant**

---

#### DELETE /api/tenants/{tenant_id}

**Delete Tenant**

---

#### GET /api/users/{user_id}

**Get User**

---

#### PUT /api/users/{user_id}

**Update User**

---

#### DELETE /api/users/{user_id}

**Delete User**

---

#### POST /api/policies/{policy_id}/toggle

**Toggle Policy**

---

#### GET /pages/{page_name}

**Get Page**

返回前端页面

---

#### GET /css/{file_name}

**Get Css**

返回 CSS 文件

---

#### GET /js/{file_name}

**Get Js**

返回 JS 文件

---

### 主机监控

#### GET /api/host/status

**Host Status**

完整主机状态

---

#### GET /api/host/gateway

**Host Gateway**

Gateway 进程信息

---

#### GET /api/host/agents

**Host Agents**

Agent 列表及状态

---

#### GET /api/host/system

**Host System**

系统资源

---

#### GET /api/host/models

**Host Models**

模型配置

---

#### GET /api/host/version

**Host Version**

OpenClaw 版本

---

### 完整报告

#### GET /api/report/full

**Get Full Report**

生成完整的 AI Agent 安全治理报告

- **format**: pdf（默认）
- **period**: daily / weekly / monthly

---

### 客户端接收

#### POST /api/client/report

**Receive Report**

接收客户端上报的监控数据。
1. 更新/创建设备记录
2. AI Agent 进程写入审计日志
3. LLM 连接写入审计日志
4. 敏感文件事件写入审计日志 + 触发策略检查

---

#### POST /api/client/heartbeat

**Heartbeat**

客户端心跳，更新设备在线状态

---

#### GET /api/client/policies

**Get Client Policies**

客户端拉取策略列表

---

### 急救室

#### GET /api/clinic/check

**Clinic Check**

诊断 OpenClaw 问题

---

#### POST /api/clinic/fix

**Clinic Fix**

一键修复 OpenClaw 问题

---

#### GET /api/clinic/status

**Clinic Status**

快速检查 Gateway 状态

---

#### GET /api/clinic/logs

**Clinic Logs**

查看 Gateway 日志

---

#### POST /api/clinic/restart

**Clinic Restart**

重启 Gateway 服务

---

### 报表导出

#### GET /api/export/devices

**Export Devices**

导出设备列表（按租户过滤）

---

#### GET /api/export/audit-logs

**Export Audit Logs**

导出审计日志（按租户过滤）

---

#### GET /api/export/alerts

**Export Alerts**

导出告警列表（按租户过滤）

---

#### GET /api/report/compliance

**Generate Compliance Report**

生成合规报告

---

#### GET /api/report/dashboard

**Get Dashboard Data**

获取仪表盘数据（从数据库读取真实数据）

---

### 拦截引擎

#### POST /api/intercept/check

**Intercept Check**

🛡️ 操作预检接口（同步，低延迟）

Agent 执行操作前调用此接口，根据返回结果决定是否继续执行。
仅做检查，不写审计日志。

用法示例：
```
POST /api/intercept/check
{
    "agent_id": "daily",
    "operation_type": "command_exec",
    "content": "rm -rf /tmp/test"
}
```

响应：
- allowed=true: 放行
- allowed=false, action=block: 拦截，不要执行
- allowed=true, action=warn: 放行，但有警告

---

#### POST /api/intercept/report

**Intercept Report**

🛡️ 操作上报接口（检查 + 写审计日志 + 触发告警）

Agent 执行操作后调用此接口上报。

---

#### GET /api/intercept/stats

**Get Intercept Stats**

拦截统计

---

#### GET /api/intercept/rules

**Get Intercept Rules**

获取所有拦截规则

---

#### POST /api/intercept/rules

**Add Intercept Rule**

添加自定义拦截规则

---

#### DELETE /api/intercept/rules/{rule_name}

**Delete Intercept Rule**

删除拦截规则

---

#### POST /api/intercept/guard/start

**Start Guard**

启动进程守卫

---

#### POST /api/intercept/guard/stop

**Stop Guard**

停止进程守卫

---

#### GET /api/intercept/guard/status

**Guard Status**

进程守卫状态

---

#### POST /api/intercept/test

**Test Intercept**

批量测试拦截规则（不写审计日志）

---

### 日志中心

#### POST /api/syslog/start

**Start Syslog Server**

启动 syslog 服务器

---

#### POST /api/syslog/stop

**Stop Syslog Server**

停止 syslog 服务器

---

#### GET /api/syslog/status

**Get Syslog Status**

获取 syslog 服务器状态

---

#### GET /api/syslog/entries/{entry_id}

**Get Syslog Entry**

获取单条日志详情

---

#### GET /api/syslog/entries

**Get Syslog Entries**

获取 syslog 条目（分页 + 过滤）

---

#### GET /api/syslog/stats

**Get Syslog Stats**

获取 syslog 统计信息

---

#### DELETE /api/syslog/clear

**Clear Syslog Entries**

清理旧日志（保留最近 N 天）

---

#### GET /api/syslog/forward-targets

**Get Forward Targets**

获取日志转发目标列表

---

#### POST /api/syslog/forward-targets

**Create Forward Target**

添加日志转发目标

---

#### DELETE /api/syslog/forward-targets/{target_id}

**Delete Forward Target**

删除日志转发目标

---

#### POST /api/syslog/forward-targets/{target_id}/toggle

**Toggle Forward Target**

切换转发目标状态

---

#### POST /api/syslog/forward-targets/{target_id}/test

**Test Forward Target**

测试转发目标连接

---

#### POST /api/syslog/test

**Send Test Syslog**

发送测试日志

---

### 流量分析

#### GET /api/traffic/stats

**Get Stats**

获取统计信息 - 从 audit_logs 表统计（按租户过滤）

---

#### GET /api/traffic/recent

**Get Recent**

返回最近的审计日志（最新 20 条，按租户过滤）

---

#### GET /api/traffic/llm-calls

**Get Llm Calls**

返回 operation_type='api_call' 的日志（按租户过滤）

---

#### GET /api/traffic/timeline

**Get Timeline**

按小时统计审计日志数量（最近 24 小时，按租户过滤）

---

#### GET /api/traffic/flows

**Get Flows**

获取流量记录 - 从审计日志读取（按租户过滤）

---

#### GET /api/traffic/devices

**Get Detected Devices**

获取检测到的设备 - 从 devices 表读取（按租户过滤）

---

#### GET /api/traffic/alerts

**Get Alerts**

获取告警列表 - 从 alerts 表读取（按租户过滤）

---

#### POST /api/traffic/check

**Check Traffic**

检查 URL 是否是 LLM 调用

---

#### GET /api/traffic/sniffer/status

**Get Sniffer Status**

获取嗅探状态（已弃用，保留接口兼容）

---

#### POST /api/traffic/sniffer/start

**Start Sniffer**

启动嗅探（已弃用，保留接口兼容）

---

#### POST /api/traffic/sniffer/stop

**Stop Sniffer**

停止嗅探（已弃用，保留接口兼容）

---

#### POST /api/traffic/clear

**Clear Data**

清空流量数据（已弃用，保留接口兼容）

---

### 策略引擎

#### POST /api/report

**Report Operation**

Agent 操作上报接口

Agent 在执行操作前/后调用此接口，平台实时检查策略并返回结果。
违规操作自动生成告警。

---

#### POST /api/policy/check

**Check Operation**

策略预检接口（只检查不记录）

Agent 执行前调用，判断是否允许。

---

### 管控执行

#### POST /api/enforcement/v2/block

**Block Device V2**

高级阻断（v2）

---

#### POST /api/enforcement/v2/unblock

**Unblock Device V2**

解除阻断（v2）

---

#### GET /api/enforcement/v2/status

**Get Enforcement Status**

获取管控状态

---

#### GET /api/process/scan

**Scan Processes**

扫描 OpenClaw 进程

---

#### POST /api/process/kill

**Kill Process**

终止进程

---

#### POST /api/process/kill-all

**Kill All Openclaw**

终止所有 OpenClaw 进程

---

#### POST /api/persistence/install

**Install Service**

安装系统服务

---

#### GET /api/enforcement/v2/rules

**Get Rules**

获取阻断规则

---

#### POST /api/enforcement/v2/rules

**Add Rule**

添加阻断规则

---

#### GET /api/enforcement/v2/log

**Get Log**

获取执行日志

---

### 网络扫描

#### POST /api/scan/v2

**Scan Network V2**

高级网络扫描（v2）

---

#### POST /api/scan/v2/auto-register

**Scan And Register**

扫描并自动将发现的 OpenClaw 实例注册到设备表（去重：IP 或主机名匹配即更新），同时同步 Agent 信息

---

#### GET /api/scan/coverage

**Get Scan Coverage**

获取 agent-client 覆盖率：已注册设备中有多少在持续上报

---

#### GET /api/scan/stats

**Get Scan Stats**

获取扫描统计

---

#### GET /api/scan/fingerprints

**Get Fingerprints**

获取 OpenClaw 指纹列表

---

### 认证

#### POST /api/auth/login

**Login**

用户登录

---

#### POST /api/auth/register

**Register**

用户注册（默认创建 viewer 角色，需管理员激活）

---

#### GET /api/auth/me

**Get Me**

获取当前用户信息

---

#### POST /api/auth/logout

**Logout**

用户登出（前端清除 Token 即可）

---

#### POST /api/auth/change-password

**Change Password**

修改密码

---

#### POST /api/auth/refresh

**Refresh Token**

用 refresh token 换新的 access token

---

#### GET /api/auth/permissions

**Get Permissions**

获取当前用户的菜单和操作权限

---

#### GET /api/auth/users

**List Users**

获取用户列表（管理员）

---

#### PUT /api/auth/users/{user_id}

**Update User**

更新用户信息（管理员）

---

#### DELETE /api/auth/users/{user_id}

**Delete User**

删除用户（管理员）

---

#### POST /api/auth/users/{user_id}/reset-password

**Reset Password**

重置用户密码（管理员）

---

### 设备管理增强

#### POST /api/devices/register

**Register Device**

手动注册设备。注册后状态为 pending，等待审批。

---

#### POST /api/devices/discover

**Discover Devices**

扫描指定 IP 段发现 OpenClaw 实例。
通过 HTTP 连接检测 /api/stats 端点判断是否为 OpenClaw。

---

#### GET /api/devices/{device_id}/detail

**Get Device Detail**

获取设备详细信息，包括关联的最近审计日志。

---

#### PUT /api/devices/{device_id}

**Update Device**

更新设备信息

---

#### POST /api/devices/{device_id}/approve

**Approve Device**

审批待注册设备，将状态从 pending 改为 online

---

#### POST /api/devices/{device_id}/block

**Block Device**

阻断设备

---

#### POST /api/devices/{device_id}/unblock

**Unblock Device**

解除设备阻断

---

#### GET /api/devices/list

**List Devices**

分页获取设备列表，支持按状态、风险等级筛选和搜索。
返回格式: {"items": [...], "total": N, "page": 1, "page_size": 20, "total_pages": M}

---

### 通知系统

#### GET /api/notification/configs

**Get Notification Configs**

获取通知配置列表

---

#### POST /api/notification/configs

**Create Notification Config**

创建通知配置

---

#### DELETE /api/notification/configs/{config_id}

**Delete Notification Config**

删除通知配置

---

#### POST /api/notification/send

**Send Notification**

发送通知

---

#### POST /api/notification/alert

**Send Alert**

发送告警通知

---

#### GET /api/notification/log

**Get Notification Log**

获取通知日志

---

#### POST /api/notification/test/{config_id}

**Test Notification**

测试通知渠道

---

#### GET /api/notification/stats

**Get Notification Stats**

获取通知统计

---

#### GET /api/notification/config

**Get Notification Config Api**

获取前端通知配置

---

#### POST /api/notification/config

**Save Notification Config Api**

保存前端通知配置

---

#### POST /api/notification/test

**Test Notification Api**

测试通知渠道

---

