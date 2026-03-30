# OpenClaw Enterprise Agent Client

轻量级守护进程，安装在员工电脑上，监控本机所有 AI Agent 的行为并上报到管控平台。

## 功能特性

- 🔍 **进程监控**：检测 OpenClaw、Cursor、Claude、Copilot、Windsurf、Cline 等 AI Agent 进程
- 🌐 **网络监控**：检测到 OpenAI、Anthropic、DeepSeek、Moonshot、智谱等 LLM API 的网络连接
- 📁 **文件监控**：监控 ~/.ssh、~/.aws、~/.gnupg 等敏感目录的访问变化
- 📋 **策略检查**：从管控平台拉取安全策略，本地预检并上报违规告警
- 💾 **离线缓存**：上报失败时本地缓存，恢复后自动重试
- 🖥️ **跨平台**：支持 macOS、Linux、Windows

## 编译

```bash
# 当前平台编译
go build -o ocw-agent .

# 交叉编译 - Linux amd64
GOOS=linux GOARCH=amd64 go build -o ocw-agent-linux .

# 交叉编译 - Linux arm64
GOOS=linux GOARCH=arm64 go build -o ocw-agent-linux-arm64 .

# 交叉编译 - Windows
GOOS=windows GOARCH=amd64 go build -o ocw-agent.exe .

# 交叉编译 - macOS Apple Silicon
GOOS=darwin GOARCH=arm64 go build -o ocw-agent-darwin-arm64 .
```

## 使用方式

```bash
# 基本使用
./ocw-agent --server http://192.168.1.100:8000

# 自定义上报间隔（秒）
./ocw-agent --server http://192.168.1.100:8000 --interval 60

# 指定配置文件
./ocw-agent --server http://192.168.1.100:8000 --config /path/to/agent.json
```

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--server` | 管控平台地址（**必填**） | - |
| `--interval` | 上报间隔（秒） | 30 |
| `--config` | 配置文件路径 | `~/.openclaw-enterprise/agent.json` |

## 配置文件

首次运行时自动生成配置文件：`~/.openclaw-enterprise/agent.json`

```json
{
  "server_url": "http://192.168.1.100:8000",
  "agent_id": "auto-generated-uuid",
  "hostname": "auto-detected",
  "interval": 30
}
```

- `agent_id` 首次运行自动生成，用于唯一标识该客户端
- 命令行参数优先级高于配置文件

## 上报数据格式

每个上报周期，客户端会采集并发送以下数据到 `POST {server}/api/report`：

```json
{
  "agent_id": "uuid",
  "hostname": "hostname",
  "os": "darwin",
  "timestamp": "2024-01-01T00:00:00Z",
  "processes": [
    {
      "pid": 1234,
      "name": "openclaw",
      "cmdline": "/usr/local/bin/openclaw ...",
      "cpu": 2.5,
      "memory": 1.2,
      "is_agent": true
    }
  ],
  "connections": [
    {
      "pid": 1234,
      "local_addr": "192.168.1.10:54321",
      "remote_addr": "104.18.6.192:443",
      "status": "ESTABLISHED",
      "is_llm_call": true,
      "provider": "openai"
    }
  ],
  "file_events": [
    {
      "path": "/home/user/.ssh/id_rsa",
      "operation": "write",
      "timestamp": "2024-01-01T00:00:00Z",
      "process_id": 0
    }
  ],
  "system_info": {
    "os": "darwin",
    "arch": "arm64",
    "hostname": "hostname",
    "ip": "192.168.1.10",
    "cpu_usage": 0,
    "mem_total": 17179869184,
    "mem_used": 8589934592
  }
}
```

## API 端点

客户端会调用管控平台的以下 API：

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/report` | 上报采集数据 |
| `GET` | `/api/policies` | 拉取安全策略 |
| `POST` | `/api/alerts` | 上报策略违规告警 |

## 识别的 AI Agent 进程

- OpenClaw (`openclaw`)
- Cursor (`cursor`)
- Claude Desktop (`claude`)
- GitHub Copilot (`copilot`)
- Windsurf (`windsurf`)
- Cline (`cline`)
- Aider (`aider`)
- Continue (`continue`)
- TabNine (`tabnine`)
- Codeium (`codeium`)
- Amazon Q (`amazon-q`)
- Node.js + .openclaw 目录
- Python + agent 关键词

## 监控的 LLM API 提供商

- OpenAI (`api.openai.com`)
- Anthropic (`api.anthropic.com`)
- 阿里云百炼 (`dashscope.aliyuncs.com`)
- DeepSeek (`api.deepseek.com`)
- Moonshot (`api.moonshot.cn`)
- 智谱 (`open.bigmodel.cn`)
- Google Gemini (`generativelanguage.googleapis.com`)
- Groq (`api.groq.com`)
- Mistral (`api.mistral.ai`)
- Cohere (`api.cohere.ai`)
- 百川 (`api.baichuan-ai.com`)
- MiniMax (`api.minimax.chat`)
- 百度 (`aip.baidubce.com`)
- 硅基流动 (`api.siliconflow.cn`)

## 监控的敏感目录

- `~/.ssh` - SSH 密钥
- `~/.gnupg` - GPG 密钥
- `~/.aws` - AWS 凭证
- `~/.azure` - Azure 凭证
- `~/.gcloud` - Google Cloud 凭证
- `~/.kube` - Kubernetes 配置
- `~/.docker` - Docker 配置
- `~/.env` - 环境变量
- `~/.gitconfig` - Git 配置
- `~/.npmrc` - NPM 配置
- `~/.pypirc` - PyPI 配置
- `/etc/shadow`、`/etc/passwd`（Linux）

## 技术特点

- **零外部依赖**：仅使用 Go 标准库
- **跨平台兼容**：macOS + Linux + Windows
- **轻量级**：编译后 < 10MB，运行内存 < 20MB
- **离线容错**：网络中断时本地缓存，恢复后自动重试
- **优雅关闭**：支持 SIGINT/SIGTERM 信号处理
