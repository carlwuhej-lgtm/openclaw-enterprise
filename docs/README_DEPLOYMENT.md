# OpenClaw Enterprise 部署文档索引

**版本**: 1.0.1  
**最后更新**: 2026-03-27

---

## 📖 快速导航

### 新手入门
1. **[Linux 一键部署](DEPLOYMENT_LINUX.md#快速部署)** ⭐ 推荐
2. **[Linux 手动部署](DEPLOYMENT_LINUX.md#详细部署)**
3. **[用户手册](USER_MANUAL_V2.md)**
4. **[API 文档](API_REFERENCE_V2.md)**

### 高级主题
- [性能优化](DEPLOYMENT_LINUX.md#性能优化)
- [安全加固](DEPLOYMENT_LINUX.md#安全加固)
- [监控告警](DEPLOYMENT_LINUX.md#监控告警)
- [故障排查](DEPLOYMENT_LINUX.md#故障排查)

---

## 🚀 快速开始（5 分钟）

### 方式 1: 一键安装（推荐）

```bash
# 下载安装脚本
curl -sSL https://raw.githubusercontent.com/openclaw/openclaw-enterprise/main/install.sh -o install.sh
chmod +x install.sh

# 执行安装
sudo ./install.sh
```

安装完成后访问：`http://服务器 IP:8003`

### 方式 2: Docker 部署（即将支持）

```bash
# 即将推出
docker run -d -p 8003:8003 openclaw/enterprise:latest
```

### 方式 3: 手动部署

查看 **[Linux 部署手册](DEPLOYMENT_LINUX.md)** 详细步骤。

---

## 📋 文档清单

### 部署文档
| 文档 | 说明 | 适用场景 |
|------|------|---------|
| **[DEPLOYMENT_LINUX.md](DEPLOYMENT_LINUX.md)** | Linux 部署完整指南 | Ubuntu/CentOS/Debian |
| **DEPLOYMENT_DOCKER.md** | Docker 部署指南 | 容器化部署（待创建） |
| **DEPLOYMENT_WINDOWS.md** | Windows 部署指南 | Windows Server（待创建） |

### 用户文档
| 文档 | 说明 |
|------|------|
| **[USER_MANUAL_V2.md](USER_MANUAL_V2.md)** | 用户操作手册 |
| **[QUICKSTART.md](QUICKSTART.md)** | 快速入门指南 |
| **[USER_GUIDE.md](USER_GUIDE.md)** | 用户使用指南 |

### 技术文档
| 文档 | 说明 |
|------|------|
| **[API_REFERENCE_V2.md](API_REFERENCE_V2.md)** | API 参考文档 |
| **[API.md](API.md)** | API 接口说明 |
| **[API_REFERENCE.md](API_REFERENCE.md)** | API 参考（旧版） |

### 运维文档
| 文档 | 说明 |
|------|------|
| **[DEPLOY.md](DEPLOY.md)** | 部署配置 |
| **[INSTALL.md](INSTALL.md)** | 安装指南 |
| **[MANUAL.md](MANUAL.md)** | 运维手册 |

### 产品文档
| 文档 | 说明 |
|------|------|
| **[PRD.md](PRD.md)** | 产品需求文档 |
| **[COMMERCIAL_READINESS.md](COMMERCIAL_READINESS.md)** | 商业化评估 |
| **[P0_COMPLETION_REPORT.md](P0_COMPLETION_REPORT.md)** | P0 任务完成报告 |

### 安全文档
| 文档 | 说明 |
|------|------|
| **[SECURITY_AUDIT.md](SECURITY_AUDIT.md)** | 安全审计报告 |
| **[SECURITY_IMPACT.md](SECURITY_IMPACT.md)** | 安全影响分析 |

### 发布说明
| 文档 | 说明 |
|------|------|
| **[RELEASE_NOTES_1.0.1.md](RELEASE_NOTES_1.0.1.md)** | v1.0.1 更新说明（30 天试用） |
| **[RELEASE_NOTES_1.0.0.md](RELEASE_NOTES_1.0.0.md)** | v1.0.0 发布说明（待创建） |

---

## 🎯 使用场景

### 场景 1: 个人开发者评估

**推荐**: [一键安装](DEPLOYMENT_LINUX.md#快速部署)

```bash
# 本地虚拟机或云服务器
curl -sSL https://.../install.sh | sudo bash

# 访问
http://localhost:8003
```

**时间**: 5 分钟  
**试用**: 30 天免费专业版

---

### 场景 2: 小团队测试

**推荐**: [手动部署](DEPLOYMENT_LINUX.md#详细部署)

1. 准备一台 Linux 服务器（4 核 8G）
2. 按照手动部署步骤安装
3. 配置 Nginx 反向代理
4. 配置 HTTPS
5. 创建团队账号

**时间**: 30 分钟  
**试用**: 30 天免费专业版（50 Agent）

---

### 场景 3: 企业 POC

**推荐**: 联系技术支持获取定制部署方案

**邮箱**: support@openclaw.ai  
**文档**: [企业部署指南](DEPLOYMENT_LINUX.md#企业部署)（待创建）

---

## 📞 获取帮助

### 文档资源
- 📖 [完整文档](docs/)
- 🌐 [在线文档](https://docs.openclaw.ai)
- 💬 [社区论坛](https://discord.gg/clawd)

### 技术支持
- 📧 邮箱：support@openclaw.ai
- 🎫 工单：管理后台 → 急救室 → 提交工单
- 📱 电话：400-XXX-XXXX（企业版用户）

### 常见问题
查看 [故障排查](DEPLOYMENT_LINUX.md#故障排查) 章节。

---

## 🎓 学习路径

### 第 1 天：安装部署
- [ ] 阅读 [Linux 部署手册](DEPLOYMENT_LINUX.md)
- [ ] 执行一键安装
- [ ] 验证服务运行

### 第 2 天：基础配置
- [ ] 阅读 [用户手册](USER_MANUAL_V2.md)
- [ ] 注册第一个实例
- [ ] 配置安全策略

### 第 3 天：功能测试
- [ ] 测试审计日志
- [ ] 测试告警功能
- [ ] 导出 PDF 报告

### 第 4-7 天：深度评估
- [ ] 测试 AI 分析
- [ ] 配置多租户
- [ ] API 集成测试
- [ ] 性能测试

### 第 2 周：决策
- [ ] 成本核算
- [ ] 技术方案评审
- [ ] 采购决策

---

## 📊 系统要求

### 最低配置
- CPU: 2 核
- 内存：4GB
- 磁盘：20GB
- 网络：10Mbps

### 推荐配置
- CPU: 4 核
- 内存：8GB
- 磁盘：100GB SSD
- 网络：100Mbps

### 支持的操作系统
- ✅ Ubuntu 20.04+
- ✅ CentOS 7+
- ✅ Debian 10+
- ⏳ Windows Server（待支持）
- ⏳ Docker（待支持）

---

## 🎁 试用政策

### 30 天免费试用
- ✅ 50 个 Agent
- ✅ 20 台设备
- ✅ 全部专业版功能
- ✅ 技术支持

### 试用转付费
- 专业版：¥3000/月
- 企业版：¥15000/月
- 年付 8 折
- 试用用户首年 7 折

---

## 📝 更新日志

### v1.0.1 (2026-03-27)
- ✅ 试用期延长至 30 天
- ✅ 新增 Linux 一键安装脚本
- ✅ 完善部署文档
- ✅ 修复 License 接口问题

### v1.0.0 (2026-03-27)
- ✅ P0 任务 100% 完成
- ✅ 完整的商业化功能
- ✅ 健康检查接口
- ✅ 批量操作功能
- ✅ License 管理系统

---

**文档版本**: 1.0.1  
**最后更新**: 2026-03-27  
**维护者**: OpenClaw Team
