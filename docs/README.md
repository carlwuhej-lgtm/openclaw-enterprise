# OpenClaw Enterprise

<div align="center">

**企业级 AI Agent 安全治理平台**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![Security](https://img.shields.io/badge/security-audit-brightgreen.svg)](SECURITY.md)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [部署指南](docs/deployment.md) • [安全政策](SECURITY.md) • [贡献指南](CONTRIBUTING.md)

</div>

---

## 📖 项目简介

OpenClaw Enterprise 是专为企业级 AI Agent 部署设计的安全治理平台，提供统一认证、审计日志、策略引擎、风险拦截等核心功能，确保 AI Agent 操作安全合规、可溯源。

### 核心场景
- 🔐 **统一认证** - JWT Token 认证，支持多租户隔离
- 📋 **审计日志** - 自动记录所有 API 操作，敏感信息过滤
- 🛡️ **策略引擎** - 自定义安全策略，实时风险拦截
- 🔍 **网络扫描** - 自动发现内网 OpenClaw 实例
- 🚨 **告警中心** - 实时告警通知，支持多渠道推送
- 📊 **分析报表** - 可视化数据分析，导出 PDF 报告

---

## ✨ 功能特性

### 安全特性
| 功能 | 说明 |
|------|------|
| 🔒 **统一认证** | JWT Token 认证，支持角色权限控制（Admin/Manager/User/Viewer） |
| 🔒 **敏感数据过滤** | 审计日志自动过滤 password/token/key 等敏感字段 |
| 🔒 **租户隔离** | 多租户数据隔离，防止越权访问 |
| 🔒 **速率限制** | 60 请求/分钟，防止暴力攻击 |
| 🔒 **XSS/CSRF 防护** | 输入验证 + Token 验证 |
| 🔒 **密码安全** | SHA256+Salt 哈希存储 |

### 管理功能
| 功能 | 说明 |
|------|------|
| 📋 **审计日志** | 记录所有 API 操作，支持筛选/搜索/导出 |
| 🛡️ **策略引擎** | 自定义安全策略（敏感目录拦截/高危命令审批） |
| 🔍 **网络扫描** | 自动发现内网 OpenClaw 实例 |
| 🚨 **告警中心** | 实时告警，支持邮件/飞书/钉钉通知 |
| 📊 **分析报表** | 可视化数据看板，PDF 报告导出 |
| 💻 **实例管理** | 管理所有 OpenClaw 实例状态 |

---

## 🚀 快速开始

### 一键安装（推荐）
```bash
# 克隆项目
git clone https://github.com/YOUR_USERNAME/openclaw-enterprise.git
cd openclaw-enterprise

# 运行安装脚本
chmod +x install.sh
./install.sh

# 启动服务
cd backend && source venv/bin/activate
python app/main.py
```

### Docker 部署
```bash
# 构建镜像
docker build -t openclaw-enterprise .

# 启动容器
docker run -d \
  -p 8003:8003 \
  -v ./data:/app/data \
  -e SECRET_KEY=your-secret-key \
  openclaw-enterprise
```

### 访问控制台
- 地址：http://localhost:8003
- 默认账号：`admin` / `admin（请修改密码）`（首次登录请修改密码）

---

## 📦 技术架构

### 后端
- **框架**: FastAPI 0.109+
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **ORM**: SQLAlchemy 2.0
- **认证**: JWT (python-jose)
- **密码**: Passlib (SHA256+Salt)

### 前端
- **架构**: 原生 HTML/CSS/JavaScript
- **样式**: 自定义深色主题
- **图表**: 原生 Canvas + SVG

### 安全
- **中间件**: 审计日志中间件
- **过滤**: 敏感参数自动过滤
- **限制**: 速率限制中间件
- **隔离**: 租户数据隔离

---

## 📋 配置说明

### 环境变量
复制 `.env.example` 为 `.env` 并修改：

```bash
cd backend
cp .env.example .env
```

### 关键配置
```ini
# 数据库
DATABASE_URL=sqlite:///./app/openclaw_enterprise.db

# JWT 密钥（生产环境必须修改）
SECRET_KEY=your-secret-key-change-in-production

# CORS 配置
CORS_ORIGINS=http://localhost:8003

# Gateway 配置
OPENCLAW_GATEWAY_TOKEN=your-gateway-token
```

---

## 🛡️ 安全最佳实践

### 部署检查清单
- [ ] 修改默认管理员密码
- [ ] 使用强 SECRET_KEY（至少 32 位随机字符串）
- [ ] 启用 HTTPS（生产环境）
- [ ] 配置防火墙（仅开放必要端口）
- [ ] 定期备份数据库
- [ ] 不提交 .env 文件到代码仓库

### 开发注意事项
- [ ] 使用 `.env` 管理敏感配置
- [ ] 不硬编码密钥/密码
- [ ] 所有用户输入必须验证
- [ ] 数据库查询使用参数化（ORM 自动处理）
- [ ] 启用 CORS 限制

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [部署指南](docs/deployment.md) | 生产环境部署步骤 |
| [配置说明](docs/configuration.md) | 详细配置参数说明 |
| [API 文档](docs/api.md) | RESTful API 接口文档 |
| [安全政策](SECURITY.md) | 漏洞报告流程 |
| [贡献指南](CONTRIBUTING.md) | 如何贡献代码 |

---

## 🤝 贡献

欢迎贡献代码、文档或建议！

### 快速开始
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

### 开发环境
```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/openclaw-enterprise.git

# 创建虚拟环境
cd openclaw-enterprise/backend
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 运行开发服务器
python app/main.py
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代高性能 Web 框架
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL 工具包
- [OpenClaw](https://github.com/openclaw/openclaw) - AI Agent 运行时

---

<div align="center">

**Made with ❤️ by OpenClaw Team**

[⭐ Star this repo](https://github.com/YOUR_USERNAME/openclaw-enterprise/stargazers) • [🐛 Report Issue](https://github.com/YOUR_USERNAME/openclaw-enterprise/issues) • [💬 Discussions](https://github.com/YOUR_USERNAME/openclaw-enterprise/discussions)

</div>
