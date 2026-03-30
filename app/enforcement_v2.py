"""
OpenClaw Enterprise - 高级管控执行模块 v2
支持提权、双向阻断、进程深度检测、持久化管控
"""
import subprocess
import httpx
import os
import sys
import platform
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
from pydantic import BaseModel
from pathlib import Path


class BlockRule(BaseModel):
    """阻断规则"""
    id: int
    name: str
    target_type: str  # ip, domain, port, process, url
    target_value: str
    action: str  # block, limit, monitor, kill
    is_enabled: bool = True
    priority: int = 100  # 优先级 1-1000
    schedule: Optional[str] = None  # cron 表达式
    created_at: datetime = datetime.now()
    expires_at: Optional[datetime] = None


class EnforcementResult(BaseModel):
    """执行结果"""
    success: bool
    method: str
    message: str
    details: Optional[Dict] = None
    timestamp: datetime = datetime.now()


class AdvancedEnforcementEngine:
    """高级策略执行引擎"""
    
    def __init__(self):
        self.active_rules: List[BlockRule] = []
        self.execution_log: List[EnforcementResult] = []
        self.sudo_available = self._check_sudo()
        self.system = platform.system()
    
    def _check_sudo(self) -> bool:
        """检查是否有 sudo 权限"""
        try:
            result = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def request_sudo(self) -> bool:
        """申请 sudo 权限"""
        if self.system == "Windows":
            return self._request_admin_windows()
        else:
            return self._request_sudo_unix()
    
    def _request_sudo_unix(self) -> bool:
        """Unix 系统申请 sudo"""
        try:
            # 测试 sudo 权限
            result = subprocess.run(
                ["sudo", "-v"],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                self.sudo_available = True
                return True
            return False
        except:
            return False
    
    def _request_admin_windows(self) -> bool:
        """Windows 申请管理员权限"""
        try:
            result = subprocess.run(
                ["net", "session"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def execute_block(self, target_ip: str, target_port: int = 8000, method: str = "auto") -> EnforcementResult:
        """执行阻断操作"""
        
        if method == "auto":
            # 自动选择最佳方法
            if self.system == "Linux":
                method = "iptables"
            elif self.system == "Darwin":
                method = "pfctl"
            elif self.system == "Windows":
                method = "windows_firewall"
            else:
                method = "hosts"
        
        methods = {
            "iptables": self._block_iptables,
            "pfctl": self._block_pfctl,
            "windows_firewall": self._block_windows,
            "hosts": self._block_hosts,
            "process": self._block_process
        }
        
        try:
            if method in methods:
                result = methods[method](target_ip, target_port)
            else:
                result = EnforcementResult(
                    success=False,
                    method=method,
                    message=f"未知的阻断方法：{method}"
                )
            
            # 记录执行日志
            self.execution_log.append(result)
            return result
            
        except Exception as e:
            return EnforcementResult(
                success=False,
                method=method,
                message=f"阻断失败：{str(e)}"
            )
    
    def _block_iptables(self, ip: str, port: int) -> EnforcementResult:
        """Linux iptables 阻断"""
        if not self.sudo_available:
            return EnforcementResult(
                success=False,
                method="iptables",
                message="需要 sudo 权限，请先执行 sudo -v"
            )
        
        try:
            # 双向阻断（OUTPUT + INPUT）
            subprocess.run(
                ["sudo", "iptables", "-A", "OUTPUT", "-d", ip, "-p", "tcp", "--dport", str(port), "-j", "DROP"],
                capture_output=True,
                timeout=5,
                check=True
            )
            subprocess.run(
                ["sudo", "iptables", "-A", "INPUT", "-s", ip, "-p", "tcp", "--sport", str(port), "-j", "DROP"],
                capture_output=True,
                timeout=5,
                check=True
            )
            
            return EnforcementResult(
                success=True,
                method="iptables",
                message=f"已双向阻断 {ip}:{port}",
                details={"rules": ["OUTPUT", "INPUT"]}
            )
        except subprocess.CalledProcessError as e:
            return EnforcementResult(
                success=False,
                method="iptables",
                message=f"iptables 执行失败：{e.stderr.decode() if e.stderr else str(e)}"
            )
    
    def _block_pfctl(self, ip: str, port: int) -> EnforcementResult:
        """macOS pfctl 阻断"""
        if not self.sudo_available:
            return EnforcementResult(
                success=False,
                method="pfctl",
                message="需要 sudo 权限"
            )
        
        try:
            # 创建 pf 规则
            pf_rule = f"block drop out proto tcp from any to {ip} port {port}\n"
            pf_rule += f"block drop in proto tcp from {ip} port {port} to any\n"
            
            # 写入临时文件
            pf_conf = "/tmp/pf_block.conf"
            with open(pf_conf, "w") as f:
                f.write(pf_rule)
            
            # 加载规则
            subprocess.run(
                ["sudo", "pfctl", "-f", pf_conf],
                capture_output=True,
                timeout=5,
                check=True
            )
            
            # 启用 pf（如果未启用）
            subprocess.run(
                ["sudo", "pfctl", "-e"],
                capture_output=True,
                timeout=5
            )
            
            return EnforcementResult(
                success=True,
                method="pfctl",
                message=f"已双向阻断 {ip}:{port}",
                details={"config": pf_conf}
            )
        except subprocess.CalledProcessError as e:
            return EnforcementResult(
                success=False,
                method="pfctl",
                message=f"pfctl 执行失败：{e.stderr.decode() if e.stderr else str(e)}"
            )
    
    def _block_windows(self, ip: str, port: int) -> EnforcementResult:
        """Windows 防火墙阻断"""
        try:
            rule_name = f"OpenClaw_Block_{ip}_{port}"
            
            # 添加入站规则
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={rule_name}_in",
                 "dir=in", "action=block",
                 f"remoteip={ip}",
                 f"remoteport={port}",
                 "protocol=TCP"],
                capture_output=True,
                timeout=5,
                shell=True
            )
            
            # 添加出站规则
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={rule_name}_out",
                 "dir=out", "action=block",
                 f"remoteip={ip}",
                 f"remoteport={port}",
                 "protocol=TCP"],
                capture_output=True,
                timeout=5,
                shell=True
            )
            
            return EnforcementResult(
                success=True,
                method="windows_firewall",
                message=f"已双向阻断 {ip}:{port}",
                details={"rule_name": rule_name}
            )
        except Exception as e:
            return EnforcementResult(
                success=False,
                method="windows_firewall",
                message=f"Windows 防火墙执行失败：{str(e)}"
            )
    
    def _block_hosts(self, ip: str, port: int) -> EnforcementResult:
        """修改 hosts 文件阻断（备用方案）"""
        try:
            hosts_file = "/etc/hosts"
            if self.system == "Windows":
                hosts_file = r"C:\Windows\System32\drivers\etc\hosts"
            
            # 检查是否已有记录
            with open(hosts_file, "r") as f:
                content = f.read()
                if ip in content:
                    return EnforcementResult(
                        success=False,
                        method="hosts",
                        message=f"IP {ip} 已在 hosts 中"
                    )
            
            # 添加阻断记录
            with open(hosts_file, "a") as f:
                f.write(f"\n{ip} openclaw.local # Blocked by OpenClaw Enterprise\n")
            
            return EnforcementResult(
                success=True,
                method="hosts",
                message=f"已在 hosts 中阻断 {ip}",
                details={"file": hosts_file}
            )
        except PermissionError:
            return EnforcementResult(
                success=False,
                method="hosts",
                message="修改 hosts 需要管理员权限"
            )
    
    def _block_process(self, ip: str, port: int) -> EnforcementResult:
        """终止相关进程"""
        # 查找占用端口的进程
        try:
            if self.system == "Linux":
                result = subprocess.run(
                    ["lsof", "-i", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                for line in result.stdout.split("\n"):
                    if "openclaw" in line.lower() or "node" in line.lower():
                        parts = line.split()
                        if len(parts) > 1:
                            pid = parts[1]
                            subprocess.run(["sudo", "kill", "-9", pid], capture_output=True)
                
                return EnforcementResult(
                    success=True,
                    method="process",
                    message=f"已终止占用端口 {port} 的进程"
                )
            else:
                return EnforcementResult(
                    success=False,
                    method="process",
                    message="进程阻断仅支持 Linux"
                )
        except:
            return EnforcementResult(
                success=False,
                method="process",
                message="进程阻断失败"
            )
    
    def execute_unblock(self, target_ip: str, target_port: int = 8000) -> EnforcementResult:
        """解除阻断"""
        try:
            if self.system == "Linux":
                # iptables 解除
                subprocess.run(
                    ["sudo", "iptables", "-D", "OUTPUT", "-d", target_ip, "-p", "tcp", "--dport", str(target_port), "-j", "DROP"],
                    capture_output=True,
                    timeout=5
                )
                subprocess.run(
                    ["sudo", "iptables", "-D", "INPUT", "-s", target_ip, "-p", "tcp", "--sport", str(target_port), "-j", "DROP"],
                    capture_output=True,
                    timeout=5
                )
                return EnforcementResult(
                    success=True,
                    method="iptables",
                    message=f"已解除阻断 {target_ip}:{target_port}"
                )
            elif self.system == "Darwin":
                # pfctl 禁用
                subprocess.run(["sudo", "pfctl", "-d"], capture_output=True, timeout=5)
                return EnforcementResult(
                    success=True,
                    method="pfctl",
                    message=f"已解除阻断 {target_ip}:{target_port}"
                )
            else:
                return EnforcementResult(
                    success=False,
                    method="unknown",
                    message="不支持的系统"
                )
        except Exception as e:
            return EnforcementResult(
                success=False,
                method="unblock",
                message=f"解除阻断失败：{str(e)}"
            )
    
    def add_rule(self, rule: BlockRule):
        """添加阻断规则"""
        self.active_rules.append(rule)
    
    def remove_rule(self, rule_id: int):
        """移除阻断规则"""
        self.active_rules = [r for r in self.active_rules if r.id != rule_id]
    
    def get_execution_log(self, limit: int = 100) -> List[EnforcementResult]:
        """获取执行日志"""
        return self.execution_log[-limit:]


class DeepProcessMonitor:
    """深度进程监控"""
    
    OPENCLAW_PROCESS_PATTERNS = [
        "openclaw",
        "clawdbot",
        "moltbot",
        "molty",
    ]
    
    OPENCLAW_ENV_PATTERNS = [
        "OPENCLAW",
        "CLAWDBOT",
        "MOLTBOT",
    ]
    
    def __init__(self):
        self.detected_processes: List[Dict] = []
    
    def scan_processes(self) -> List[Dict]:
        """扫描系统中的 OpenClaw 进程"""
        detected = []
        
        try:
            if platform.system() in ["Linux", "Darwin"]:
                # ps aux 扫描
                result = subprocess.run(
                    ["ps", "aux"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                for line in result.stdout.split("\n"):
                    line_lower = line.lower()
                    
                    # 检查进程名
                    for pattern in self.OPENCLAW_PROCESS_PATTERNS:
                        if pattern in line_lower:
                            parts = line.split()
                            if len(parts) >= 11:
                                detected.append({
                                    "pid": parts[1],
                                    "user": parts[0],
                                    "cpu": parts[2],
                                    "memory": parts[3],
                                    "command": " ".join(parts[10:]),
                                    "detected_at": datetime.now().isoformat(),
                                    "confidence": 90
                                })
                            break
                    
                    # 检查环境变量
                    for pattern in self.OPENCLAW_ENV_PATTERNS:
                        if pattern in line:
                            parts = line.split()
                            if len(parts) >= 11:
                                detected.append({
                                    "pid": parts[1],
                                    "user": parts[0],
                                    "cpu": parts[2],
                                    "memory": parts[3],
                                    "command": " ".join(parts[10:]),
                                    "detected_at": datetime.now().isoformat(),
                                    "confidence": 70
                                })
                            break
        except Exception as e:
            pass
        
        self.detected_processes = detected
        return detected
    
    def kill_process(self, pid: int, force: bool = True) -> EnforcementResult:
        """终止进程"""
        try:
            signal = "-9" if force else "-15"
            subprocess.run(
                ["sudo", "kill", signal, str(pid)],
                capture_output=True,
                timeout=5
            )
            return EnforcementResult(
                success=True,
                method="kill",
                message=f"已终止进程 {pid}"
            )
        except Exception as e:
            return EnforcementResult(
                success=False,
                method="kill",
                message=f"终止失败：{str(e)}"
            )
    
    def kill_all_openclaw(self) -> Dict:
        """终止所有 OpenClaw 进程"""
        results = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "details": []
        }
        
        processes = self.scan_processes()
        results["total"] = len(processes)
        
        for proc in processes:
            result = self.kill_process(int(proc["pid"]))
            results["details"].append({
                "pid": proc["pid"],
                "success": result.success
            })
            if result.success:
                results["success"] += 1
            else:
                results["failed"] += 1
        
        return results


class PersistenceManager:
    """持久化管理器"""
    
    def __init__(self):
        self.system = platform.system()
    
    def install_service(self) -> EnforcementResult:
        """安装系统服务（开机自启）"""
        if self.system == "Linux":
            return self._install_systemd()
        elif self.system == "Darwin":
            return self._install_launchd()
        elif self.system == "Windows":
            return self._install_windows_service()
        else:
            return EnforcementResult(
                success=False,
                method="install",
                message=f"不支持的系统：{self.system}"
            )
    
    def _install_systemd(self) -> EnforcementResult:
        """Linux systemd 服务"""
        service_content = """[Unit]
Description=OpenClaw Enterprise Enforcement
After=network.target

[Service]
Type=simple
User=root
ExecStart=/opt/openclaw-enterprise/backend/venv/bin/python /opt/openclaw-enterprise/backend/app/enforcement_daemon.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
        try:
            # 写入服务文件
            service_path = "/etc/systemd/system/openclaw-enforcement.service"
            with open(service_path, "w") as f:
                f.write(service_content)
            
            # 重载 systemd
            subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True, timeout=5)
            
            # 启用服务
            subprocess.run(["sudo", "systemctl", "enable", "openclaw-enforcement"], capture_output=True, timeout=5)
            
            # 启动服务
            subprocess.run(["sudo", "systemctl", "start", "openclaw-enforcement"], capture_output=True, timeout=5)
            
            return EnforcementResult(
                success=True,
                method="systemd",
                message="systemd 服务已安装并启动",
                details={"service": service_path}
            )
        except Exception as e:
            return EnforcementResult(
                success=False,
                method="systemd",
                message=f"安装失败：{str(e)}"
            )
    
    def _install_launchd(self) -> EnforcementResult:
        """macOS launchd 服务"""
        plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.enforcement</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/openclaw-enterprise/backend/venv/bin/python</string>
        <string>/opt/openclaw-enterprise/backend/app/enforcement_daemon.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""
        try:
            plist_path = "/Library/LaunchDaemons/com.openclaw.enforcement.plist"
            with open(plist_path, "w") as f:
                f.write(plist_content)
            
            # 加载服务
            subprocess.run(["sudo", "launchctl", "load", "-w", plist_path], capture_output=True, timeout=5)
            
            return EnforcementResult(
                success=True,
                method="launchd",
                message="launchd 服务已安装",
                details={"plist": plist_path}
            )
        except Exception as e:
            return EnforcementResult(
                success=False,
                method="launchd",
                message=f"安装失败：{str(e)}"
            )
    
    def _install_windows_service(self) -> EnforcementResult:
        """Windows 服务"""
        return EnforcementResult(
            success=False,
            method="windows_service",
            message="Windows 服务安装需要额外依赖（pywin32）"
        )


# ==================== FastAPI 集成 ====================

from fastapi import APIRouter, HTTPException

router = APIRouter()

enforcement = AdvancedEnforcementEngine()
process_monitor = DeepProcessMonitor()
persistence = PersistenceManager()

@router.post("/api/enforcement/v2/block")
async def block_device_v2(ip: str, port: int = 8000, method: str = "auto"):
    """高级阻断（v2）"""
    result = enforcement.execute_block(ip, port, method)
    return result

@router.post("/api/enforcement/v2/unblock")
async def unblock_device_v2(ip: str, port: int = 8000):
    """解除阻断（v2）"""
    result = enforcement.execute_unblock(ip, port)
    return result

@router.get("/api/enforcement/v2/status")
async def get_enforcement_status():
    """获取管控状态"""
    return {
        "sudo_available": enforcement.sudo_available,
        "system": enforcement.system,
        "active_rules": len(enforcement.active_rules),
        "execution_log_count": len(enforcement.execution_log)
    }

@router.get("/api/process/scan")
async def scan_processes():
    """扫描 OpenClaw 进程"""
    return process_monitor.scan_processes()

@router.post("/api/process/kill")
async def kill_process(pid: int, force: bool = True):
    """终止进程"""
    return process_monitor.kill_process(pid, force)

@router.post("/api/process/kill-all")
async def kill_all_openclaw():
    """终止所有 OpenClaw 进程"""
    return process_monitor.kill_all_openclaw()

@router.post("/api/persistence/install")
async def install_service():
    """安装系统服务"""
    return persistence.install_service()

@router.get("/api/enforcement/v2/rules")
async def get_rules():
    """获取阻断规则"""
    return enforcement.active_rules

@router.post("/api/enforcement/v2/rules")
async def add_rule(rule: BlockRule):
    """添加阻断规则"""
    enforcement.add_rule(rule)
    return {"success": True, "rule": rule}

@router.get("/api/enforcement/v2/log")
async def get_log(limit: int = 100):
    """获取执行日志"""
    return enforcement.get_execution_log(limit)
