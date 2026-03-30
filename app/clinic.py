"""
OpenClaw Enterprise - 急救室模块
自动诊断和修复 OpenClaw 启动问题
"""
import os
import json
import plistlib
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class CheckStatus(Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    FIXED = "fixed"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    fix_action: Optional[str] = None
    details: Optional[Dict] = None


class OpenClawClinic:
    """OpenClaw 急救室"""
    
    def __init__(self):
        self.home = Path.home()
        self.openclaw_dir = self.home / ".openclaw"
        self.env_file = self.openclaw_dir / ".env"
        self.config_file = self.openclaw_dir / "openclaw.json"
        self.plist_file = self.home / "Library" / "LaunchAgents" / "ai.openclaw.gateway.plist"
        self.logs_dir = self.openclaw_dir / "logs"
        
        # 需要同步的环境变量列表
        self.env_keys = [
            "ALIYUN_API_KEY",
            "TAVILY_API_KEY",
            "OPENROUTER_API_KEY",
            "FEISHU_SECURITY_APP_ID",
            "FEISHU_SECURITY_APP_SECRET",
            "FEISHU_DAILY_APP_ID",
            "FEISHU_DAILY_APP_SECRET",
            "FEISHU_ADMIN_APP_ID",
            "FEISHU_ADMIN_APP_SECRET",
            "OPENCLAW_GATEWAY_TOKEN",
        ]
    
    def run_full_check(self) -> List[CheckResult]:
        """运行完整诊断"""
        results = []
        
        # 1. 检查 .env 文件
        results.append(self._check_env_file())
        
        # 2. 检查 openclaw.json
        results.append(self._check_config_file())
        
        # 3. 检查 launchd 服务
        results.append(self._check_launchd_service())
        
        # 4. 检查环境变量同步
        results.append(self._check_env_sync())
        
        # 5. 检查 Gateway 状态
        results.append(self._check_gateway_status())
        
        # 6. 检查日志目录
        results.append(self._check_logs_dir())
        
        return results
    
    def _check_env_file(self) -> CheckResult:
        """检查 .env 文件"""
        if not self.env_file.exists():
            return CheckResult(
                name=".env 文件",
                status=CheckStatus.ERROR,
                message=".env 文件不存在",
                fix_action="创建 .env 文件"
            )
        
        try:
            content = self.env_file.read_text()
            env_vars = {}
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
            
            missing_keys = [k for k in self.env_keys if k not in env_vars]
            if missing_keys:
                return CheckResult(
                    name=".env 文件",
                    status=CheckStatus.WARNING,
                    message=f"缺少 {len(missing_keys)} 个环境变量",
                    fix_action=f"添加缺失的变量：{', '.join(missing_keys)}",
                    details={"missing": missing_keys}
                )
            
            return CheckResult(
                name=".env 文件",
                status=CheckStatus.OK,
                message=f"已配置 {len(env_vars)} 个环境变量"
            )
        except Exception as e:
            return CheckResult(
                name=".env 文件",
                status=CheckStatus.ERROR,
                message=f"读取失败：{str(e)}",
                fix_action="检查文件权限"
            )
    
    def _check_config_file(self) -> CheckResult:
        """检查 openclaw.json 配置"""
        if not self.config_file.exists():
            return CheckResult(
                name="openclaw.json",
                status=CheckStatus.ERROR,
                message="配置文件不存在",
                fix_action="运行 openclaw init"
            )
        
        try:
            with open(self.config_file) as f:
                config = json.load(f)
            
            # 检查是否有硬编码的 API Key（应该用变量引用）
            issues = []
            if "models" in config and "providers" in config["models"]:
                for provider_name, provider_config in config["models"]["providers"].items():
                    if isinstance(provider_config, dict):
                        api_key = provider_config.get("apiKey", "")
                        if api_key and not api_key.startswith("${") and len(api_key) > 20:
                            issues.append(f"{provider_name}.apiKey 应该使用 ${{VAR}} 格式")
            
            if issues:
                return CheckResult(
                    name="openclaw.json",
                    status=CheckStatus.WARNING,
                    message="发现硬编码的 API Key",
                    fix_action="改为变量引用格式",
                    details={"issues": issues}
                )
            
            return CheckResult(
                name="openclaw.json",
                status=CheckStatus.OK,
                message="配置文件正常"
            )
        except json.JSONDecodeError as e:
            return CheckResult(
                name="openclaw.json",
                status=CheckStatus.ERROR,
                message=f"JSON 格式错误：{str(e)}",
                fix_action="修复 JSON 格式"
            )
        except Exception as e:
            return CheckResult(
                name="openclaw.json",
                status=CheckStatus.ERROR,
                message=f"读取失败：{str(e)}",
                fix_action="检查文件权限"
            )
    
    def _check_launchd_service(self) -> CheckResult:
        """检查 launchd 服务"""
        if not self.plist_file.exists():
            return CheckResult(
                name="launchd 服务",
                status=CheckStatus.ERROR,
                message="服务文件不存在",
                fix_action="运行 openclaw gateway install"
            )
        
        try:
            with open(self.plist_file, 'rb') as f:
                plist = plistlib.load(f)
            
            # 检查服务是否已加载
            result = subprocess.run(
                ["launchctl", "list", "|", "grep", "openclaw"],
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return CheckResult(
                    name="launchd 服务",
                    status=CheckStatus.WARNING,
                    message="服务未加载",
                    fix_action="运行 launchctl load"
                )
            
            return CheckResult(
                name="launchd 服务",
                status=CheckStatus.OK,
                message="服务已注册并运行"
            )
        except Exception as e:
            return CheckResult(
                name="launchd 服务",
                status=CheckStatus.ERROR,
                message=f"检查失败：{str(e)}",
                fix_action="重新安装服务"
            )
    
    def _check_env_sync(self) -> CheckResult:
        """检查环境变量同步"""
        if not self.plist_file.exists():
            return CheckResult(
                name="环境变量同步",
                status=CheckStatus.ERROR,
                message="plist 文件不存在",
                fix_action="运行 openclaw gateway install"
            )
        
        try:
            with open(self.plist_file, 'rb') as f:
                plist = plistlib.load(f)
            
            plist_env = plist.get('EnvironmentVariables', {})
            env_vars = self._load_env_file()
            
            missing_in_plist = []
            for key in self.env_keys:
                if key in env_vars and key not in plist_env:
                    missing_in_plist.append(key)
            
            if missing_in_plist:
                return CheckResult(
                    name="环境变量同步",
                    status=CheckStatus.ERROR,
                    message=f"{len(missing_in_plist)} 个环境变量未同步到 launchd",
                    fix_action="同步环境变量到 plist",
                    details={"missing": missing_in_plist}
                )
            
            return CheckResult(
                name="环境变量同步",
                status=CheckStatus.OK,
                message="环境变量已同步"
            )
        except Exception as e:
            return CheckResult(
                name="环境变量同步",
                status=CheckStatus.ERROR,
                message=f"检查失败：{str(e)}",
                fix_action="手动同步环境变量"
            )
    
    def _check_gateway_status(self) -> CheckResult:
        """检查 Gateway 状态"""
        import socket
        
        try:
            # 使用 socket 检查端口，而不是 lsof
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', 18789))
            sock.close()
            
            if result == 0:
                return CheckResult(
                    name="Gateway 状态",
                    status=CheckStatus.OK,
                    message="Gateway 正在运行 (端口 18789)"
                )
            else:
                return CheckResult(
                    name="Gateway 状态",
                    status=CheckStatus.ERROR,
                    message="Gateway 未运行",
                    fix_action="启动 Gateway"
                )
        except Exception as e:
            return CheckResult(
                name="Gateway 状态",
                status=CheckStatus.ERROR,
                message=f"检查失败：{str(e)}",
                fix_action="手动启动 Gateway"
            )
    
    def _check_logs_dir(self) -> CheckResult:
        """检查日志目录"""
        if not self.logs_dir.exists():
            return CheckResult(
                name="日志目录",
                status=CheckStatus.WARNING,
                message="日志目录不存在",
                fix_action="创建日志目录"
            )
        
        return CheckResult(
            name="日志目录",
            status=CheckStatus.OK,
            message=f"日志目录：{self.logs_dir}"
        )
    
    def _load_env_file(self) -> Dict[str, str]:
        """加载 .env 文件"""
        env_vars = {}
        if self.env_file.exists():
            content = self.env_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
        return env_vars
    
    def fix_all(self) -> List[CheckResult]:
        """修复所有问题"""
        results = []
        
        # 1. 备份当前配置
        backup_result = self._backup_configs()
        results.append(backup_result)
        
        # 2. 同步环境变量到 plist
        sync_result = self._sync_env_to_plist()
        results.append(sync_result)
        
        # 3. 修复 openclaw.json 变量引用
        config_result = self._fix_config_vars()
        results.append(config_result)
        
        # 4. 重新加载 launchd 服务
        reload_result = self._reload_launchd()
        results.append(reload_result)
        
        # 5. 重启 Gateway
        restart_result = self._restart_gateway()
        results.append(restart_result)
        
        return results
    
    def _backup_configs(self) -> CheckResult:
        """备份配置文件"""
        try:
            backup_dir = self.openclaw_dir / "backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            files_to_backup = [
                self.env_file,
                self.config_file,
                self.plist_file,
            ]
            
            for src in files_to_backup:
                if src.exists():
                    dst = backup_dir / src.name
                    shutil.copy2(src, dst)
            
            return CheckResult(
                name="备份配置",
                status=CheckStatus.FIXED,
                message=f"已备份到 {backup_dir}",
                details={"backup_dir": str(backup_dir)}
            )
        except Exception as e:
            return CheckResult(
                name="备份配置",
                status=CheckStatus.ERROR,
                message=f"备份失败：{str(e)}"
            )
    
    def _sync_env_to_plist(self) -> CheckResult:
        """同步环境变量到 plist"""
        try:
            env_vars = self._load_env_file()
            
            if not self.plist_file.exists():
                return CheckResult(
                    name="同步环境变量",
                    status=CheckStatus.ERROR,
                    message="plist 文件不存在"
                )
            
            with open(self.plist_file, 'rb') as f:
                plist = plistlib.load(f)
            
            if 'EnvironmentVariables' not in plist:
                plist['EnvironmentVariables'] = {}
            
            # 添加环境变量
            for key in self.env_keys:
                if key in env_vars:
                    plist['EnvironmentVariables'][key] = env_vars[key]
            
            # 写回 plist
            with open(self.plist_file, 'wb') as f:
                plistlib.dump(plist, f)
            
            return CheckResult(
                name="同步环境变量",
                status=CheckStatus.FIXED,
                message=f"已同步 {len(env_vars)} 个环境变量到 plist"
            )
        except Exception as e:
            return CheckResult(
                name="同步环境变量",
                status=CheckStatus.ERROR,
                message=f"同步失败：{str(e)}"
            )
    
    def _fix_config_vars(self) -> CheckResult:
        """修复 openclaw.json 变量引用"""
        try:
            if not self.config_file.exists():
                return CheckResult(
                    name="修复配置",
                    status=CheckStatus.ERROR,
                    message="配置文件不存在"
                )
            
            with open(self.config_file) as f:
                config = json.load(f)
            
            modified = False
            
            # 替换硬编码的 API Key 为变量引用
            if "models" in config and "providers" in config["models"]:
                for provider_name, provider_config in config["models"]["providers"].items():
                    if isinstance(provider_config, dict):
                        api_key = provider_config.get("apiKey", "")
                        if api_key and not api_key.startswith("${") and len(api_key) > 20:
                            # 推断变量名
                            var_name = f"{provider_name.upper()}_API_KEY"
                            provider_config["apiKey"] = f"${{{var_name}}}"
                            modified = True
            
            if modified:
                with open(self.config_file, 'w') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                return CheckResult(
                    name="修复配置",
                    status=CheckStatus.FIXED,
                    message="已将硬编码 Key 改为变量引用"
                )
            else:
                return CheckResult(
                    name="修复配置",
                    status=CheckStatus.OK,
                    message="配置已经是变量引用格式"
                )
        except Exception as e:
            return CheckResult(
                name="修复配置",
                status=CheckStatus.ERROR,
                message=f"修复失败：{str(e)}"
            )
    
    def _reload_launchd(self) -> CheckResult:
        """重新加载 launchd 服务"""
        try:
            # unload
            subprocess.run(
                ["launchctl", "unload", str(self.plist_file)],
                capture_output=True,
                timeout=5
            )
            
            # 等待一下
            import time
            time.sleep(1)
            
            # load
            result = subprocess.run(
                ["launchctl", "load", str(self.plist_file)],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return CheckResult(
                    name="重新加载服务",
                    status=CheckStatus.FIXED,
                    message="launchd 服务已重新加载"
                )
            else:
                return CheckResult(
                    name="重新加载服务",
                    status=CheckStatus.ERROR,
                    message=f"load 失败：{result.stderr}"
                )
        except Exception as e:
            return CheckResult(
                name="重新加载服务",
                status=CheckStatus.ERROR,
                message=f"操作失败：{str(e)}"
            )
    
    def _restart_gateway(self) -> CheckResult:
        """重启 Gateway"""
        try:
            # 尝试用 openclaw 命令重启
            result = subprocess.run(
                ["openclaw", "gateway", "restart"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return CheckResult(
                    name="重启 Gateway",
                    status=CheckStatus.FIXED,
                    message="Gateway 已重启"
                )
            else:
                # 尝试手动重启
                subprocess.run(
                    ["openclaw", "gateway", "stop"],
                    capture_output=True,
                    timeout=5
                )
                import time
                time.sleep(1)
                subprocess.run(
                    ["openclaw", "gateway", "start"],
                    capture_output=True,
                    timeout=5
                )
                
                return CheckResult(
                    name="重启 Gateway",
                    status=CheckStatus.FIXED,
                    message="Gateway 已手动重启"
                )
        except Exception as e:
            return CheckResult(
                name="重启 Gateway",
                status=CheckStatus.ERROR,
                message=f"重启失败：{str(e)}",
                fix_action="手动执行 openclaw gateway restart"
            )


# 单例
clinic = OpenClawClinic()
