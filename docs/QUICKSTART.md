# 🐱 OpenClaw Enterprise - 快速开始指南

## 5 分钟上手

### 步骤 1: 解压项目
```bash
unzip openclaw-enterprise-project.zip
cd openclaw-enterprise
```

### 步骤 2: 启动服务

**macOS/Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```bash
start.bat
```

### 步骤 3: 访问系统

浏览器打开：**http://localhost:8000/pages/dashboard**

---

## 初始界面

启动后你会看到：

### 控制台总览
- 📊 4 个统计卡片（设备数、待审批、告警、审计日志）
- 💻 设备列表（5 台示例设备）
- 📋 实时审计日志
- 🚨 实时告警（4 条示例告警）
- ⚙️ 安全策略（7 条策略）
- 🏢 租户分布（3 个部门）

---

## 功能演示

### 1. 查看设备
1. 点击左侧导航 **资产管理**
2. 查看 5 台示例设备
3. 点击 **详情** 查看设备信息
4. 点击 **阻断** 阻断违规设备

### 2. 配置策略
1. 点击左侧导航 **策略中心**
2. 点击开关启用/禁用策略
3. 点击 **保存配置** 提交更改

### 3. 查看审计
1. 点击左侧导航 **审计日志**
2. 查看操作记录
3. 点击标签筛选（全部/文件/命令/API/消息）

### 4. 处理告警
1. 点击左侧导航 **告警中心**
2. 查看告警列表
3. 点击 **标记解决** 处理告警

### 5. 管理租户
1. 点击左侧导航 **租户管理**
2. 查看 3 个示例租户
3. 点击 **编辑** 修改租户信息

---

## 示例数据

系统自动创建以下示例数据：

### 租户
- 研发中心 (28 台设备)
- 运维部 (12 台设备)
- 数据部 (7 台设备)

### 用户
- 张三 (研发中心)
- 李四 (研发中心)
- 王五 (运维部)
- 赵六 (数据部)

### 设备
| 设备名 | 用户 | 状态 | 风险 |
|--------|------|------|------|
| dev-macbook-001 | 张三 | 在线 | 低 |
| dev-macbook-015 | 李四 | 需升级 | 中 |
| unknown-pc-089 | 未识别 | 违规 | 高 |
| ops-server-003 | 王五 | 在线 | 低 |
| data-workstation-007 | 赵六 | 离线 | 中 |

### 告警
- 🔴 未授权设备接入 (严重)
- 🔴 敏感文件访问尝试 (严重)
- 🟠 版本过低 (高危)
- 🔵 Prompt 注入检测 (中危)

---

## API 测试

### 使用 Swagger UI
访问：http://localhost:8000/docs

### 使用 curl
```bash
# 获取统计数据
curl http://localhost:8000/api/stats

# 获取设备列表
curl http://localhost:8000/api/devices

# 获取审计日志
curl http://localhost:8000/api/audit-logs?limit=10

# 获取告警列表
curl http://localhost:8000/api/alerts

# 获取策略列表
curl http://localhost:8000/api/policies
```

---

## 常见问题

### Q1: 端口被占用
**错误**: `Address already in use`

**解决**:
```bash
# 查看占用端口的进程
lsof -i :8000

# 杀死进程
kill -9 <PID>
```

### Q2: Python 版本过低
**错误**: `Python 3.11+ required`

**解决**:
```bash
# 检查版本
python3 --version

# 升级 Python (macOS)
brew upgrade python
```

### Q3: 依赖安装失败
**错误**: `Failed to build wheel`

**解决**:
```bash
# 升级 pip
pip install --upgrade pip

# 重新安装
pip install -r requirements.txt
```

### Q4: 页面空白
**原因**: 后端服务未启动

**解决**:
1. 确认后端已启动 (看到 `Uvicorn running on http://0.0.0.0:8000`)
2. 检查浏览器控制台是否有错误
3. 清除浏览器缓存

---

## 下一步

### 学习资源
- 📖 [产品需求文档](docs/PRD.md)
- 📡 [API 文档](docs/API.md)
- 🚀 [部署指南](docs/DEPLOY.md)

### 自定义开发
1. 修改 `backend/app/main.py` 添加新 API
2. 复制 `frontend/pages/dashboard.html` 创建新页面
3. 修改 `frontend/js/app.js` 添加前端逻辑

### 生产部署
参考 [部署指南](docs/DEPLOY.md) 进行生产环境配置

---

## 获取帮助

- 📧 技术支持：support@openclaw.com
- 💬 社区论坛：https://github.com/openclaw/enterprise/discussions
- 📝 问题反馈：https://github.com/openclaw/enterprise/issues

---

**🐱 祝你使用愉快！**
