"""
OpenClaw Enterprise - 本机主机监控模块
实时采集本机 OpenClaw 实例的运行状态
"""
import json
import os
import platform
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

router = APIRouter(prefix="/api/host", tags=["主机监控"])


def _mask_key(value: str) -> str:
    """对 API 密钥等敏感信息脱敏：只显示前4位 + ***"""
    if not value or len(value) <= 4:
        return "***"
    return value[:4] + "***"


def _run_cmd(cmd: str, timeout: int = 5) -> Optional[str]:
    """安全执行系统命令，带超时"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return None


class HostMonitor:
    """本机 OpenClaw 实例状态采集器"""

    def __init__(self):
        self.home = Path.home()
        self.openclaw_dir = self.home / ".openclaw"
        self.config_path = self.openclaw_dir / "openclaw.json"
        # 常见 nvm 安装路径
        self.nvm_node_modules = (
            self.home
            / ".nvm"
            / "versions"
            / "node"
            / "v22.16.0"
            / "lib"
            / "node_modules"
            / "openclaw"
        )
        # 缓存友好主机名
        self._friendly_hostname = self._resolve_hostname()

    def _resolve_hostname(self) -> str:
        """获取友好主机名（优先 scutil ComputerName）"""
        for cmd in ["/usr/sbin/scutil --get ComputerName", "/usr/sbin/scutil --get LocalHostName"]:
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
                v = r.stdout.strip()
                if v and v != "bogon":
                    return v
            except Exception:
                pass
        fallback = platform.node()
        return fallback if fallback and fallback != "bogon" else "unknown-host"

    def collect_all(self) -> Dict[str, Any]:
        """采集完整主机状态"""
        result: Dict[str, Any] = {
            "collected_at": datetime.now().isoformat(),
            "hostname": self._friendly_hostname,
        }

        # 逐项采集，单项失败不影响其他
        collectors = {
            "gateway": self.get_gateway_status,
            "agents": self.get_agents,
            "system": self.get_system_info,
            "openclaw_version": self.get_openclaw_version,
            "models": self.get_models,
        }
        for key, fn in collectors.items():
            try:
                result[key] = fn()
            except Exception as e:
                result[key] = {"error": str(e)}

        return result

    # ------------------------------------------------------------------
    # Gateway 进程状态
    # ------------------------------------------------------------------
    def get_gateway_status(self) -> Dict[str, Any]:
        """获取 Gateway 进程信息（从 ps aux 采集）"""
        raw = _run_cmd("ps aux | grep -E 'openclaw-gateway|openclaw gateway' | grep -v grep")
        if not raw:
            return {"running": False, "message": "Gateway 进程未检测到"}

        processes: List[Dict[str, Any]] = []
        for line in raw.splitlines():
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            processes.append(
                {
                    "user": parts[0],
                    "pid": int(parts[1]),
                    "cpu_percent": float(parts[2]),
                    "mem_percent": float(parts[3]),
                    "vsz_kb": int(parts[4]),
                    "rss_kb": int(parts[5]),
                    "start_time": parts[8],
                    "elapsed": parts[9],
                    "command": parts[10],
                }
            )

        if not processes:
            return {"running": False, "message": "Gateway 进程未检测到"}

        return {"running": True, "process_count": len(processes), "processes": processes}

    # ------------------------------------------------------------------
    # Agent 配置信息
    # ------------------------------------------------------------------
    def get_agents(self) -> List[Dict[str, Any]]:
        """读取 openclaw.json 中的 agents 配置，并检测运行状态"""
        config = self._load_config()
        if config is None:
            return [{"error": "无法读取 openclaw.json"}]

        agents_cfg = config.get("agents", {})
        agent_list = agents_cfg.get("list", agents_cfg.get("entries", []))

        # 如果 list 是 dict（id → config），转成 list
        if isinstance(agent_list, dict):
            agents_out = []
            for agent_id, agent_val in agent_list.items():
                if isinstance(agent_val, dict):
                    entry = {"id": agent_id, **agent_val}
                else:
                    entry = {"id": agent_id, "value": agent_val}
                agents_out.append(entry)
            agent_list = agents_out

        # 检测 Gateway 是否在运行
        gateway_running = False
        gw_raw = _run_cmd("ps aux | grep -E 'openclaw-gateway|openclaw gateway' | grep -v grep")
        if gw_raw:
            gateway_running = True

        result: List[Dict[str, Any]] = []
        for agent in agent_list:
            if not isinstance(agent, dict):
                continue
            agent_id = agent.get("id", agent.get("name", "unknown"))
            info: Dict[str, Any] = {
                "id": agent_id,
                "name": agent.get("name", agent_id),
                "model": agent.get("model", "default"),
                # Gateway 运行且 workspace 存在则认为 agent 可用
                "status": "running" if gateway_running else "stopped",
            }
            # workspace 路径
            ws = agent.get("workspace", agent.get("workdir"))
            if ws:
                info["workspace"] = str(ws)
            else:
                # 尝试推断
                ws_path = self.openclaw_dir / "agents" / agent_id
                if ws_path.is_dir():
                    info["workspace"] = str(ws_path)

            # 检查 workspace 是否存在
            if "workspace" in info:
                info["workspace_exists"] = Path(info["workspace"]).is_dir()

            result.append(info)

        return result

    # ------------------------------------------------------------------
    # 系统资源
    # ------------------------------------------------------------------
    def get_system_info(self) -> Dict[str, Any]:
        """采集系统资源信息（macOS 兼容）"""
        info: Dict[str, Any] = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "hostname": self._friendly_hostname,
        }

        # CPU 核数
        cpu_count = os.cpu_count()
        if cpu_count:
            info["cpu_cores"] = cpu_count
        else:
            raw = _run_cmd("sysctl -n hw.ncpu") or _run_cmd(
                "getconf _NPROCESSORS_ONLN"
            )
            if raw and raw.isdigit():
                info["cpu_cores"] = int(raw)

        # 内存总量（macOS: sysctl hw.memsize）
        mem_raw = _run_cmd("sysctl -n hw.memsize")
        if mem_raw and mem_raw.isdigit():
            mem_bytes = int(mem_raw)
            info["memory_total_gb"] = round(mem_bytes / (1024**3), 2)
        else:
            # fallback Linux
            mem_raw = _run_cmd("grep MemTotal /proc/meminfo")
            if mem_raw:
                match = re.search(r"(\d+)", mem_raw)
                if match:
                    info["memory_total_gb"] = round(int(match.group(1)) / (1024**2), 2)

        # 磁盘使用（df -h /）
        df_raw = _run_cmd("df -h /")
        if df_raw:
            lines = df_raw.strip().splitlines()
            if len(lines) >= 2:
                # macOS df 可能把一行拆成两行
                data_line = " ".join(lines[1:])
                parts = data_line.split()
                if len(parts) >= 5:
                    info["disk"] = {
                        "filesystem": parts[0],
                        "size": parts[1],
                        "used": parts[2],
                        "available": parts[3],
                        "use_percent": parts[4],
                    }

        # 系统负载
        load_raw = _run_cmd("sysctl -n vm.loadavg") or _run_cmd(
            "cat /proc/loadavg"
        )
        if load_raw:
            nums = re.findall(r"[\d.]+", load_raw)
            if len(nums) >= 3:
                info["load_average"] = {
                    "1min": float(nums[0]),
                    "5min": float(nums[1]),
                    "15min": float(nums[2]),
                }

        # 系统运行时间
        uptime_raw = _run_cmd("uptime")
        if uptime_raw:
            info["uptime"] = uptime_raw.strip()

        return info

    # ------------------------------------------------------------------
    # OpenClaw 版本
    # ------------------------------------------------------------------
    def get_openclaw_version(self) -> Dict[str, Any]:
        """读取 OpenClaw package.json 中的版本"""
        pkg_path = self.nvm_node_modules / "package.json"

        # 尝试多个可能的路径
        candidates = [
            pkg_path,
            self.home
            / ".nvm"
            / "versions"
            / "node"
            / "v25.7.0"
            / "lib"
            / "node_modules"
            / "openclaw"
            / "package.json",
        ]

        # 也试试 which openclaw 来找路径
        which_result = _run_cmd("which openclaw")
        if which_result:
            # 从 bin 路径推断 lib 路径
            bin_path = Path(which_result).resolve()
            # 通常 .../bin/openclaw → .../lib/node_modules/openclaw/package.json
            node_base = bin_path.parent.parent
            candidates.append(
                node_base / "lib" / "node_modules" / "openclaw" / "package.json"
            )

        for p in candidates:
            try:
                if p.is_file():
                    with open(p, "r") as f:
                        pkg = json.load(f)
                    return {
                        "version": pkg.get("version", "unknown"),
                        "name": pkg.get("name", "openclaw"),
                        "description": pkg.get("description", ""),
                        "source": str(p),
                    }
            except (json.JSONDecodeError, OSError):
                continue

        # fallback: 命令行
        ver_raw = _run_cmd("openclaw --version 2>/dev/null || openclaw version 2>/dev/null")
        if ver_raw:
            return {"version": ver_raw, "source": "cli"}

        return {"error": "无法获取 OpenClaw 版本"}

    # ------------------------------------------------------------------
    # 模型提供商
    # ------------------------------------------------------------------
    def get_models(self) -> Dict[str, Any]:
        """从 config 中提取已配置的模型列表，敏感信息脱敏"""
        config = self._load_config()
        if config is None:
            return {"error": "无法读取 openclaw.json"}

        models_cfg = config.get("models", {})
        providers_cfg = models_cfg.get("providers", {})

        providers_out: List[Dict[str, Any]] = []

        if isinstance(providers_cfg, dict):
            for provider_id, provider_val in providers_cfg.items():
                entry: Dict[str, Any] = {"id": provider_id}
                if isinstance(provider_val, dict):
                    # 复制非敏感字段
                    for k, v in provider_val.items():
                        if k.lower() in ("apikey", "api_key", "key", "secret", "token"):
                            entry[k] = _mask_key(str(v)) if not str(v).startswith("${") else v
                        else:
                            entry[k] = v
                providers_out.append(entry)
        elif isinstance(providers_cfg, list):
            for prov in providers_cfg:
                if isinstance(prov, dict):
                    entry = {}
                    for k, v in prov.items():
                        if k.lower() in ("apikey", "api_key", "key", "secret", "token"):
                            entry[k] = _mask_key(str(v)) if not str(v).startswith("${") else v
                        else:
                            entry[k] = v
                    providers_out.append(entry)

        # 默认模型
        default_model = models_cfg.get("default", config.get("model"))

        result: Dict[str, Any] = {
            "default_model": default_model,
            "providers": providers_out,
            "provider_count": len(providers_out),
        }

        # 从 agents 中收集使用的模型
        agents = config.get("agents", {})
        agent_list = agents.get("list", agents.get("entries", []))
        models_in_use = set()
        if isinstance(agent_list, dict):
            for _, av in agent_list.items():
                if isinstance(av, dict) and "model" in av:
                    models_in_use.add(av["model"])
        elif isinstance(agent_list, list):
            for a in agent_list:
                if isinstance(a, dict) and "model" in a:
                    models_in_use.add(a["model"])
        if models_in_use:
            result["models_in_use"] = sorted(models_in_use)

        return result

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _load_config(self) -> Optional[Dict]:
        """加载 openclaw.json 配置"""
        try:
            if self.config_path.is_file():
                with open(self.config_path, "r") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
        return None


# ==================== 单例 ====================
_monitor = HostMonitor()


# ==================== FastAPI 路由 ====================
@router.get("/status")
async def host_status():
    """完整主机状态"""
    return _monitor.collect_all()


@router.get("/gateway")
async def host_gateway():
    """Gateway 进程信息"""
    return _monitor.get_gateway_status()


@router.get("/agents")
async def host_agents():
    """Agent 列表及状态"""
    return _monitor.get_agents()


@router.get("/system")
async def host_system():
    """系统资源"""
    return _monitor.get_system_info()


@router.get("/models")
async def host_models():
    """模型配置"""
    return _monitor.get_models()


@router.get("/version")
async def host_version():
    """OpenClaw 版本"""
    return _monitor.get_openclaw_version()
