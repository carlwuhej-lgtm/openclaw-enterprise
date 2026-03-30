"""
OpenClaw Enterprise - 急救室 API 路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from clinic import clinic, CheckResult, CheckStatus


router = APIRouter(tags=["急救室"])


class CheckResponse(BaseModel):
    timestamp: str
    total_checks: int
    ok_count: int
    warning_count: int
    error_count: int
    results: List[Dict]


class FixResponse(BaseModel):
    timestamp: str
    total_actions: int
    success_count: int
    error_count: int
    results: List[Dict]
    backup_location: Optional[str] = None


@router.get("/api/clinic/check", response_model=CheckResponse)
async def clinic_check():
    """
    诊断 OpenClaw 问题
    """
    results = clinic.run_full_check()
    
    ok_count = sum(1 for r in results if r.status == CheckStatus.OK)
    warning_count = sum(1 for r in results if r.status == CheckStatus.WARNING)
    error_count = sum(1 for r in results if r.status == CheckStatus.ERROR)
    
    return CheckResponse(
        timestamp=datetime.now().isoformat(),
        total_checks=len(results),
        ok_count=ok_count,
        warning_count=warning_count,
        error_count=error_count,
        results=[
            {
                "name": r.name,
                "status": r.status.value,
                "message": r.message,
                "fix_action": r.fix_action,
                "details": r.details,
            }
            for r in results
        ]
    )


@router.post("/api/clinic/fix", response_model=FixResponse)
async def clinic_fix():
    """
    一键修复 OpenClaw 问题
    """
    results = clinic.fix_all()
    
    success_count = sum(1 for r in results if r.status == CheckStatus.FIXED or r.status == CheckStatus.OK)
    error_count = sum(1 for r in results if r.status == CheckStatus.ERROR)
    
    backup_location = None
    for r in results:
        if r.name == "备份配置" and r.details:
            backup_location = r.details.get("backup_dir")
    
    return FixResponse(
        timestamp=datetime.now().isoformat(),
        total_actions=len(results),
        success_count=success_count,
        error_count=error_count,
        results=[
            {
                "name": r.name,
                "status": r.status.value,
                "message": r.message,
            }
            for r in results
        ],
        backup_location=backup_location
    )


@router.get("/api/clinic/status")
async def clinic_status():
    """
    快速检查 Gateway 状态
    """
    import subprocess
    import socket
    
    # 检查端口（使用 socket 而不是 lsof）
    gateway_running = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 18789))
        gateway_running = (result == 0)
        sock.close()
    except:
        pass
    
    # 检查进程
    process_check = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    
    process_running = "openclaw-gateway" in process_check.stdout or "openclaw gateway" in process_check.stdout
    
    # 检查 launchd
    launchd_check = subprocess.run(
        ["launchctl", "list"],
        capture_output=True,
        text=True
    )
    
    launchd_loaded = "openclaw" in launchd_check.stdout
    
    return {
        "gateway_running": gateway_running,
        "process_running": process_running,
        "launchd_loaded": launchd_loaded,
        "port": 18789,
        "dashboard": "http://127.0.0.1:18789/" if gateway_running else None,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/api/clinic/logs")
async def clinic_logs(lines: int = 50):
    """
    查看 Gateway 日志
    """
    import subprocess
    
    log_file = "/tmp/openclaw/openclaw-{}.log".format(datetime.now().strftime("%Y-%m-%d"))
    
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), log_file],
            capture_output=True,
            text=True
        )
        
        return {
            "log_file": log_file,
            "lines": lines,
            "content": result.stdout,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败：{str(e)}")


@router.post("/api/clinic/restart")
async def clinic_restart():
    """
    重启 Gateway 服务
    """
    import subprocess
    
    try:
        # stop
        subprocess.run(
            ["openclaw", "gateway", "stop"],
            capture_output=True,
            timeout=10
        )
        
        import time
        time.sleep(2)
        
        # start
        result = subprocess.run(
            ["openclaw", "gateway", "start"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        return {
            "success": result.returncode == 0,
            "message": "Gateway 已重启" if result.returncode == 0 else f"重启失败：{result.stderr}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重启失败：{str(e)}")
