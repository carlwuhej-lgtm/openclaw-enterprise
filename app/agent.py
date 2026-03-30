"""
OpenClaw Enterprise - 终端 Agent 模块
轻量级客户端 Agent，实现深度管控
"""
import os
import sys
import psutil
import subprocess
import socket
import time
import json
import threading
from datetime import datetime
from typing import List, Dict, Optional, Callable
from pydantic import BaseModel
from pathlib import Path


class AgentConfig(BaseModel):
    """Agent 配置"""
    server_url: str
    agent_id: str
    check_interval: int = 30  # 心跳间隔（秒）
    report_interval: int = 300  # 报告间隔（秒）
    auto_start: bool = True


class ProcessInfo(BaseModel):
    """进程信息"""
    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_percent: float
    create_time: str
    cmdline: str
    is_openclaw: bool = False


class NetworkConnection(BaseModel):
    """网络连接"""
    pid: int
    laddr: str
    raddr: str
    status: str
    is_llm_call: bool = False


class AgentStatus(BaseModel):
    """Agent 状态"""
    agent_id: str
    hostname: str
    os: str
    os_version: str
    cpu_percent: float
    memory_total: int
    memory_used: int
    disk_total: int
    disk_used: int
    network_interfaces: List[str]
    openclaw_processes: List[ProcessInfo]
    llm_connections: List[NetworkConnection]
    last_heartbeat: datetime
    uptime: int


class TerminalAgent:
    """终端 Agent"""
    
    # OpenClaw 进程特征
    OPENCLAW_PROCESS_NAMES = [
        'openclaw',
        'clawdbot',
        'moltbot',
        'molty',
        'node',  # OpenClaw 是 Node.js 应用
    ]
    
    # OpenClaw 相关文件
    OPENCLAW_FILES = [
        '.openclaw',
        'openclaw.config',
        'clawdbot',
        'MEMORY.md',
    ]
    
    # LLM API 域名
    LLM_DOMAINS = [
        'api.openai.com',
        'api.anthropic.com',
        'api.cohere.com',
        'api.deepseek.com',
        'bailian.aliyuncs.com',
        'dashscope.aliyuncs.com',
    ]
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.running = False
        self.server_connected = False
        self.last_heartbeat = None
        self.callbacks = {
            'process_detected': [],
            'llm_call_detected': [],
            'policy_violated': []
        }
    
    def start(self):
        """启动 Agent"""
        self.running = True
        
        # 启动心跳线程
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        
        # 启动监控线程
        threading.Thread(target=self._monitor_loop, daemon=True).start()
        
        return True
    
    def stop(self):
        """停止 Agent"""
        self.running = False
    
    def _heartbeat_loop(self):
        """心跳循环"""
        while self.running:
            try:
                status = self.get_status()
                self._send_heartbeat(status)
                self.last_heartbeat = datetime.now()
                self.server_connected = True
            except Exception as e:
                self.server_connected = False
            
            time.sleep(self.config.check_interval)
    
    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                # 检测 OpenClaw 进程
                processes = self.detect_openclaw_processes()
                for proc in processes:
                    self._trigger_callback('process_detected', proc)
                
                # 检测 LLM 连接
                connections = self.detect_llm_connections()
                for conn in connections:
                    self._trigger_callback('llm_call_detected', conn)
                
                # 检查策略违规
                violations = self.check_policy_violations()
                for violation in violations:
                    self._trigger_callback('policy_violated', violation)
                
            except Exception as e:
                pass
            
            time.sleep(10)  # 每 10 秒检查一次
    
    def _send_heartbeat(self, status: AgentStatus):
        """发送心跳"""
        # 实际实现需要发送到服务器
        # 这里仅做示例
        pass
    
    def _trigger_callback(self, event: str, data: dict):
        """触发回调"""
        for callback in self.callbacks.get(event, []):
            try:
                callback(data)
            except:
                pass
    
    def on(self, event: str, callback: Callable):
        """注册事件回调"""
        if event in self.callbacks:
            self.callbacks[event].append(callback)
    
    def get_status(self) -> AgentStatus:
        """获取 Agent 状态"""
        # 系统信息
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # 网络接口
        interfaces = list(psutil.net_if_stats().keys())
        
        # OpenClaw 进程
        openclaw_procs = self.detect_openclaw_processes()
        
        # LLM 连接
        llm_conns = self.detect_llm_connections()
        
        return AgentStatus(
            agent_id=self.config.agent_id,
            hostname=socket.gethostname(),
            os=sys.platform,
            os_version=self._get_os_version(),
            cpu_percent=cpu_percent,
            memory_total=memory.total,
            memory_used=memory.used,
            disk_total=disk.total,
            disk_used=disk.used,
            network_interfaces=interfaces,
            openclaw_processes=openclaw_procs,
            llm_connections=llm_conns,
            last_heartbeat=datetime.now(),
            uptime=int(time.time() - psutil.boot_time())
        )
    
    def _get_os_version(self) -> str:
        """获取操作系统版本"""
        if sys.platform == 'darwin':
            import platform
            return platform.mac_ver()[0]
        elif sys.platform == 'linux':
            try:
                with open('/etc/os-release') as f:
                    for line in f:
                        if line.startswith('PRETTY_NAME='):
                            return line.split('=')[1].strip().strip('"')
            except:
                pass
            return 'Linux'
        elif sys.platform == 'win32':
            import platform
            return platform.win32_ver()[0]
        return 'Unknown'
    
    def detect_openclaw_processes(self) -> List[ProcessInfo]:
        """检测 OpenClaw 进程"""
        detected = []
        
        for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent', 'create_time', 'cmdline']):
            try:
                info = proc.info
                name = info['name'].lower() if info['name'] else ''
                cmdline = ' '.join(info['cmdline']) if info['cmdline'] else ''
                
                # 检查是否是 OpenClaw
                is_openclaw = False
                for pattern in self.OPENCLAW_PROCESS_NAMES:
                    if pattern in name or pattern in cmdline:
                        is_openclaw = True
                        break
                
                # 检查工作目录是否包含 OpenClaw 文件
                if not is_openclaw:
                    try:
                        cwd = proc.cwd()
                        for pattern in self.OPENCLAW_FILES:
                            if pattern in str(cwd).lower():
                                is_openclaw = True
                                break
                    except:
                        pass
                
                if is_openclaw:
                    detected.append(ProcessInfo(
                        pid=info['pid'],
                        name=info['name'],
                        status=info['status'],
                        cpu_percent=info['cpu_percent'] or 0,
                        memory_percent=info['memory_percent'] or 0,
                        create_time=datetime.fromtimestamp(info['create_time']).isoformat() if info['create_time'] else '',
                        cmdline=cmdline,
                        is_openclaw=True
                    ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return detected
    
    def detect_llm_connections(self) -> List[NetworkConnection]:
        """检测 LLM API 连接"""
        detected = []
        
        for conn in psutil.net_connections(kind='inet'):
            try:
                if conn.raddr:
                    # 检查是否是 LLM API
                    is_llm = False
                    for domain in self.LLM_DOMAINS:
                        if domain in conn.raddr.ip:
                            is_llm = True
                            break
                    
                    if is_llm:
                        detected.append(NetworkConnection(
                            pid=conn.pid or 0,
                            laddr=f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else '',
                            raddr=f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else '',
                            status=conn.status,
                            is_llm_call=True
                        ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return detected
    
    def check_policy_violations(self) -> List[Dict]:
        """检查策略违规"""
        violations = []
        
        # 检查是否有未授权的 OpenClaw 进程
        processes = self.detect_openclaw_processes()
        if processes:
            violations.append({
                'type': 'unauthorized_openclaw',
                'severity': 'high',
                'details': {
                    'processes': [p.dict() for p in processes]
                },
                'timestamp': datetime.now().isoformat()
            })
        
        # 检查 LLM 连接
        connections = self.detect_llm_connections()
        if connections:
            violations.append({
                'type': 'llm_call_detected',
                'severity': 'medium',
                'details': {
                    'connections': [c.dict() for c in connections]
                },
                'timestamp': datetime.now().isoformat()
            })
        
        return violations
    
    def kill_process(self, pid: int) -> bool:
        """终止进程"""
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=5)
            return True
        except:
            return False
    
    def block_port(self, port: int) -> bool:
        """阻断端口（需要 root）"""
        try:
            if sys.platform in ['linux', 'darwin']:
                subprocess.run(
                    ['sudo', 'iptables', '-A', 'OUTPUT', '-p', 'tcp', '--dport', str(port), '-j', 'DROP'],
                    capture_output=True,
                    timeout=5
                )
                return True
        except:
            return False
        return False


class AgentInstaller:
    """Agent 安装器"""
    
    @staticmethod
    def install(server_url: str, agent_id: str = None) -> bool:
        """安装 Agent"""
        try:
            # 生成 Agent ID
            if not agent_id:
                import uuid
                agent_id = str(uuid.uuid4())
            
            # 创建配置目录
            config_dir = Path.home() / '.openclaw-enterprise'
            config_dir.mkdir(exist_ok=True)
            
            # 保存配置
            config = {
                'server_url': server_url,
                'agent_id': agent_id,
                'check_interval': 30,
                'report_interval': 300,
                'auto_start': True
            }
            
            config_file = config_dir / 'agent-config.json'
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            # 创建启动脚本
            if sys.platform == 'win32':
                # Windows 启动脚本
                startup_script = config_dir / 'start-agent.bat'
                with open(startup_script, 'w') as f:
                    f.write(f'@echo off\npython agent_daemon.py --config "{config_file}"\n')
            else:
                # Linux/macOS 启动脚本
                startup_script = config_dir / 'start-agent.sh'
                with open(startup_script, 'w') as f:
                    f.write(f'#!/bin/bash\npython3 agent_daemon.py --config "{config_file}"\n')
                os.chmod(startup_script, 0o755)
            
            # 注册开机自启
            AgentInstaller._register_autostart(config_dir)
            
            return True
        except Exception as e:
            return False
    
    @staticmethod
    def _register_autostart(config_dir: Path):
        """注册开机自启"""
        if sys.platform == 'darwin':
            # macOS launchd
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.enterprise-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>{config_dir}/agent_daemon.py</string>
        <string>--config</string>
        <string>{config_dir}/agent-config.json</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
            plist_path = Path.home() / 'Library/LaunchAgents/com.openclaw.enterprise-agent.plist'
            with open(plist_path, 'w') as f:
                f.write(plist_content)
        
        elif sys.platform == 'linux':
            # Linux systemd
            service_content = f"""[Unit]
Description=OpenClaw Enterprise Agent
After=network.target

[Service]
Type=simple
User={os.getlogin()}
ExecStart=/usr/bin/python3 {config_dir}/agent_daemon.py --config {config_dir}/agent-config.json
Restart=always

[Install]
WantedBy=multi-user.target
"""
            service_path = Path.home() / '.config/systemd/user/openclaw-agent.service'
            service_path.parent.mkdir(exist_ok=True)
            with open(service_path, 'w') as f:
                f.write(service_content)
    
    @staticmethod
    def uninstall() -> bool:
        """卸载 Agent"""
        try:
            config_dir = Path.home() / '.openclaw-enterprise'
            if config_dir.exists():
                import shutil
                shutil.rmtree(config_dir)
            return True
        except:
            return False


# ==================== FastAPI 集成 ====================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# 全局 Agent 实例
agent: Optional[TerminalAgent] = None

class InstallRequest(BaseModel):
    server_url: str
    agent_id: Optional[str] = None

class KillRequest(BaseModel):
    pid: int

@router.post("/api/agent/install")
async def install_agent(request: InstallRequest):
    """安装 Agent"""
    success = AgentInstaller.install(request.server_url, request.agent_id)
    if success:
        return {"success": True, "message": "Agent 安装成功"}
    else:
        raise HTTPException(status_code=500, detail="安装失败")

@router.post("/api/agent/uninstall")
async def uninstall_agent():
    """卸载 Agent"""
    success = AgentInstaller.uninstall()
    return {"success": success}

@router.post("/api/agent/start")
async def start_agent():
    """启动 Agent"""
    global agent
    
    # 加载配置
    config_dir = Path.home() / '.openclaw-enterprise'
    config_file = config_dir / 'agent-config.json'
    
    if not config_file.exists():
        raise HTTPException(status_code=400, detail="请先安装 Agent")
    
    with open(config_file) as f:
        config_data = json.load(f)
    
    config = AgentConfig(**config_data)
    agent = TerminalAgent(config)
    agent.start()
    
    return {"success": True, "message": "Agent 已启动"}

@router.post("/api/agent/stop")
async def stop_agent():
    """停止 Agent"""
    global agent
    
    if agent:
        agent.stop()
        agent = None
        return {"success": True, "message": "Agent 已停止"}
    else:
        return {"success": False, "message": "Agent 未运行"}

@router.get("/api/agent/status")
async def get_agent_status():
    """获取 Agent 状态"""
    global agent
    
    if agent:
        status = agent.get_status()
        return status.dict()
    else:
        return {"running": False, "message": "Agent 未运行"}

@router.get("/api/agent/processes")
async def detect_processes():
    """检测 OpenClaw 进程"""
    global agent
    
    if agent:
        processes = agent.detect_openclaw_processes()
        return [p.dict() for p in processes]
    else:
        return []

@router.get("/api/agent/connections")
async def detect_connections():
    """检测 LLM 连接"""
    global agent
    
    if agent:
        connections = agent.detect_llm_connections()
        return [c.dict() for c in connections]
    else:
        return []

@router.post("/api/agent/kill")
async def kill_process(request: KillRequest):
    """终止进程"""
    global agent
    
    if agent:
        success = agent.kill_process(request.pid)
        return {"success": success}
    else:
        raise HTTPException(status_code=400, detail="Agent 未运行")

@router.get("/api/agent/violations")
async def get_violations():
    """获取策略违规"""
    global agent
    
    if agent:
        violations = agent.check_policy_violations()
        return violations
    else:
        return []
