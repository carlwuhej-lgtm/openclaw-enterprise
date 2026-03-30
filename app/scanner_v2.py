"""
OpenClaw Enterprise - 高级网络扫描模块 v2
支持多端口、指纹识别、被动监听
"""
import socket
import threading
import httpx
import ipaddress
import re
import time
from datetime import datetime
from typing import List, Dict, Optional, Callable
from pydantic import BaseModel
from collections import defaultdict


class DeviceInfo(BaseModel):
    """发现的设备信息"""
    ip: str
    hostname: str
    port: int
    version: Optional[str] = None
    status: str = "online"
    confidence: int = 100  # 置信度 0-100
    fingerprints: List[str] = []
    discovered_at: datetime = datetime.now()
    response_time: Optional[float] = None


class ScanConfig(BaseModel):
    """扫描配置"""
    ports: List[int] = [8000, 8080, 3000, 80, 443]
    timeout: float = 2.0
    max_workers: int = 500
    fingerprint_check: bool = True
    passive_mode: bool = False


class AdvancedScanner:
    """高级网络扫描器"""
    
    # OpenClaw 指纹特征
    OPENCLAW_FINGERPRINTS = {
        'api_status': '/api/status',
        'api_conversation': '/api/conversation',
        'api_skills': '/api/skills',
        'x_openclaw_header': 'X-OpenClaw',
        'server_header': 'OpenClaw',
        'html_title': 'OpenClaw',
        'clawdbot': 'Clawdbot',
        'moltbot': 'Moltbot',
    }
    
    # HTTP 响应特征
    HTTP_SIGNATURES = [
        b'openclaw',
        b'clawdbot',
        b'moltbot',
        b'X-OpenClaw',
        b'/api/conversation',
        b'/api/skills',
        b'agentId',
        b'sessionKey',
        b'openclaw control',
        b'openclaw-gateway',
    ]
    
    def __init__(self, config: ScanConfig = None):
        self.config = config or ScanConfig()
        self.results: List[DeviceInfo] = []
        self.lock = threading.Lock()
        self.stats = {
            'scanned': 0,
            'found': 0,
            'failed': 0,
            'start_time': None,
            'end_time': None
        }
        self.http_client = httpx.Client(proxy=None,
            timeout=self.config.timeout,
            follow_redirects=True,
            verify=False
        )
    
    def scan_port(self, ip: str, port: int) -> Optional[DeviceInfo]:
        """扫描单个 IP 的指定端口"""
        try:
            # TCP 连接测试
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.config.timeout)
            start_time = time.time()
            result = sock.connect_ex((ip, port))
            response_time = (time.time() - start_time) * 1000  # ms
            sock.close()
            
            if result == 0:
                # 端口开放，检查是否是 OpenClaw
                device = self._check_openclaw(ip, port, response_time)
                if device:
                    # 置信度>=50 确认是 OpenClaw，<50 标记为未知服务
                    if device.confidence >= 50:
                        device.status = "online"
                    else:
                        device.status = "unknown"  # 端口开放但服务未知
                        device.hostname = f"unknown-service-{port}"
                    return device
            return None
        except Exception as e:
            return None
    
    def _check_openclaw(self, ip: str, port: int, response_time: float) -> Optional[DeviceInfo]:
        """检查是否是 OpenClaw 实例"""
        device = DeviceInfo(
            ip=ip,
            hostname=ip,
            port=port,
            confidence=0,
            response_time=response_time
        )
        
        # 获取主机名
        try:
            device.hostname = socket.gethostbyaddr(ip)[0]
        except:
            pass
        
        # HTTP 指纹检查
        if self.config.fingerprint_check:
            fingerprints = self._get_http_fingerprints(ip, port)
            device.fingerprints = fingerprints
            device.confidence = min(100, len(fingerprints) * 30 + 10)
            
            # 尝试获取版本信息
            version = self._get_version(ip, port)
            if version:
                device.version = version
                device.confidence = min(100, device.confidence + 20)
            
            # 如果没有指纹但端口开放，给基础置信度
            if len(fingerprints) == 0:
                device.confidence = 20  # 端口开放但无法确认
        else:
            # 无指纹检查，仅端口开放
            device.confidence = 30
        
        return device
    
    def _get_http_fingerprints(self, ip: str, port: int) -> List[str]:
        """获取 HTTP 指纹（使用 urllib 绕过系统代理）"""
        import urllib.request
        fingerprints = []
        urls_to_check = [
            f"http://{ip}:{port}/",
            f"http://{ip}:{port}/api/status",
        ]
        
        # 不走代理
        no_proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(no_proxy_handler)
        
        for url in urls_to_check:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'OpenClaw-Scanner/1.0'})
                resp = opener.open(req, timeout=2)
                response_text = resp.read().decode(errors='ignore').lower()
                
                # 检查响应内容中的 OpenClaw 特征
                for sig in self.HTTP_SIGNATURES:
                    if sig.decode().lower() in response_text:
                        fingerprints.append(f"body:{sig.decode()}")
                
            except Exception:
                continue
        
        # 去重
        return list(set(fingerprints))
    
    def _get_version(self, ip: str, port: int) -> Optional[str]:
        """获取 OpenClaw 版本（使用 urllib 绕过代理）"""
        import urllib.request, json as _json
        try:
            no_proxy = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(no_proxy)
            req = urllib.request.Request(f"http://{ip}:{port}/api/status", headers={'User-Agent': 'OpenClaw-Scanner/1.0'})
            resp = opener.open(req, timeout=2)
            if resp.status == 200:
                data = _json.loads(resp.read().decode())
                return data.get("version", "unknown")
        except:
            pass
        return None
    
    def scan_subnet(self, subnet: str) -> List[DeviceInfo]:
        """扫描整个子网"""
        self.results = []
        self.stats = {
            'scanned': 0,
            'found': 0,
            'failed': 0,
            'start_time': datetime.now(),
            'end_time': None
        }
        
        network = ipaddress.ip_network(subnet, strict=False)
        hosts = list(network.hosts())
        
        # 限制扫描的 IP 数量（避免扫描整个大子网）
        max_hosts = min(len(hosts), 256)  # 最多扫描 256 个 IP
        
        # 多线程扫描
        threads = []
        for port in self.config.ports:
            for i, host in enumerate(hosts[:max_hosts]):
                t = threading.Thread(
                    target=self._scan_and_store,
                    args=(str(host), port)
                )
                threads.append(t)
                t.start()
                
                # 控制并发数
                if len(threads) >= self.config.max_workers:
                    for t in threads:
                        t.join()
                    threads = []
        
        # 等待剩余线程
        for t in threads:
            t.join()
        
        self.stats['end_time'] = datetime.now()
        self.stats['found'] = len(self.results)
        
        return self.results
    
    def _scan_and_store(self, ip: str, port: int):
        """扫描并存储结果"""
        device = self.scan_port(ip, port)
        with self.lock:
            self.stats['scanned'] += 1
            if device:
                self.results.append(device)
                self.stats['found'] += 1
            else:
                self.stats['failed'] += 1
    
    def scan_range(self, start_ip: str, end_ip: str) -> List[DeviceInfo]:
        """扫描 IP 范围"""
        self.results = []
        start = ipaddress.IPv4Address(start_ip)
        end = ipaddress.IPv4Address(end_ip)
        
        threads = []
        current = int(start)
        while current <= int(end):
            ip = str(ipaddress.IPv4Address(current))
            for port in self.config.ports:
                t = threading.Thread(
                    target=self._scan_and_store,
                    args=(ip, port)
                )
                threads.append(t)
                t.start()
                
                if len(threads) >= self.config.max_workers:
                    for t in threads:
                        t.join()
                    threads = []
            
            current += 1
        
        for t in threads:
            t.join()
        
        return self.results
    
    def quick_scan(self, subnet: str = "192.168.1.0/24") -> List[DeviceInfo]:
        """快速扫描（仅扫描常见端口）"""
        self.config.ports = [18789, 8000, 8080, 3000]
        self.config.max_workers = 1000
        return self.scan_subnet(subnet)
    
    def deep_scan(self, subnet: str) -> List[DeviceInfo]:
        """深度扫描（全端口 + 详细指纹）"""
        self.config.ports = list(range(1, 1024)) + [8000, 8080, 3000]
        self.config.max_workers = 200
        self.config.fingerprint_check = True
        return self.scan_subnet(subnet)
    
    def get_stats(self) -> Dict:
        """获取扫描统计"""
        if self.stats['start_time']:
            duration = (self.stats['end_time'] or datetime.now()) - self.stats['start_time']
            return {
                'scanned': self.stats['scanned'],
                'found': self.stats['found'],
                'failed': self.stats['failed'],
                'duration_seconds': duration.total_seconds(),
                'success_rate': self.stats['found'] / max(1, self.stats['scanned']) * 100
            }
        return {}


class PassiveListener:
    """被动监听器 - 监听网络流量中的 OpenClaw 特征"""
    
    def __init__(self, interface: str = None):
        self.interface = interface
        self.detected_devices: Dict[str, DeviceInfo] = {}
        self.running = False
        self.lock = threading.Lock()
    
    def start(self, callback: Callable = None):
        """开始被动监听"""
        self.running = True
        # 实际实现需要 socket 原始套接字
        # 这里提供框架接口
        pass
    
    def stop(self):
        """停止监听"""
        self.running = False
    
    def analyze_packet(self, src_ip: str, dst_ip: str, payload: bytes) -> Optional[DeviceInfo]:
        """分析网络包"""
        # 检查是否包含 OpenClaw 特征
        for sig in AdvancedScanner.HTTP_SIGNATURES:
            if sig.lower() in payload.lower():
                device = DeviceInfo(
                    ip=src_ip,
                    hostname=src_ip,
                    port=8000,
                    confidence=80,
                    fingerprints=[f"passive:{sig.decode()}"],
                    status="detected"
                )
                
                with self.lock:
                    self.detected_devices[src_ip] = device
                
                return device
        return None


# ==================== FastAPI 集成 ====================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class ScanRequest(BaseModel):
    subnet: Optional[str] = None
    start_ip: Optional[str] = None
    end_ip: Optional[str] = None
    ports: Optional[List[int]] = [8000, 8080, 3000]
    mode: str = "quick"  # quick, standard, deep

class ScanResponse(BaseModel):
    success: bool
    devices: List[DeviceInfo]
    stats: Dict
    message: str

@router.post("/api/scan/v2", response_model=ScanResponse)
async def scan_network_v2(request: ScanRequest):
    """高级网络扫描（v2）"""
    config = ScanConfig(
        ports=request.ports or [18789, 8000, 8080, 3000],
        timeout=2.0,
        max_workers=500 if request.mode == "quick" else 200,
        fingerprint_check=True
    )
    
    scanner = AdvancedScanner(config)
    
    try:
        if request.mode == "quick":
            devices = scanner.quick_scan(request.subnet or "192.168.1.0/24")
        elif request.mode == "deep":
            devices = scanner.deep_scan(request.subnet or "192.168.1.0/24")
        else:
            if request.subnet:
                devices = scanner.scan_subnet(request.subnet)
            elif request.start_ip and request.end_ip:
                devices = scanner.scan_range(request.start_ip, request.end_ip)
            else:
                devices = scanner.quick_scan()
        
        return ScanResponse(
            success=True,
            devices=devices,
            stats=scanner.get_stats(),
            message=f"发现 {len(devices)} 台设备"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/scan/v2/auto-register")
async def scan_and_register(request: ScanRequest):
    """扫描并自动将发现的 OpenClaw 实例注册到设备表（去重：IP 或主机名匹配即更新），同时同步 Agent 信息"""
    from database import SessionLocal
    from models import Device
    from agent_manager import Agent
    import httpx

    config = ScanConfig(
        ports=request.ports or [18789, 8000, 8080, 3000],
        timeout=2.0,
        max_workers=500,
        fingerprint_check=True
    )
    scanner = AdvancedScanner(config)
    devices = scanner.scan_subnet(request.subnet or "192.168.1.0/24")

    db = SessionLocal()
    registered = 0
    updated = 0
    agents_synced = 0
    try:
        for dev in devices:
            if dev.confidence < 50:
                continue  # 置信度太低，跳过
            
            # 去重逻辑：先查 IP，再查主机名（避免重复注册）
            existing = db.query(Device).filter(
                (Device.ip_address == dev.ip) | 
                (Device.hostname == dev.hostname)
            ).first()
            
            if existing:
                # 更新现有设备
                existing.status = "online"
                existing.last_active = datetime.now()
                if dev.version and dev.version != "unknown":
                    existing.version = dev.version
                # 如果 IP 不同但主机名匹配，更新 IP（设备可能换了网络）
                if existing.ip_address != dev.ip:
                    existing.ip_address = dev.ip
                updated += 1
            else:
                # 新设备，创建记录
                new_device = Device(
                    name=dev.hostname or dev.ip,
                    hostname=dev.hostname or dev.ip,
                    ip_address=dev.ip,
                    version=dev.version or "unknown",
                    status="online",
                    risk_level="low",
                    risk_score=0,
                    last_active=datetime.now(),
                    created_at=datetime.now(),
                )
                db.add(new_device)
                db.commit()  # 先提交获取 ID
                db.refresh(new_device)
                existing = new_device
                registered += 1
            
            # 同步该设备上的 Agent 信息（调用远程设备的 /api/agents 接口）
            try:
                # 尝试通过 OpenClaw Gateway 端口访问
                base_url = f"http://{dev.ip}:{dev.port}"
                async with httpx.AsyncClient(timeout=2.0, proxy=None) as client:
                    resp = await client.get(f"{base_url}/api/agents")
                    if resp.status_code == 200:
                        agents_data = resp.json()
                        for ag in agents_data.get('items', []):
                            # 检查是否已存在
                            existing_agent = db.query(Agent).filter(
                                (Agent.agent_id == ag.get('id')) & 
                                (Agent.device_id == existing.id)
                            ).first()
                            if existing_agent:
                                existing_agent.name = ag.get('name', ag.get('id'))
                                existing_agent.model = ag.get('model', '')
                                existing_agent.status = 'running'
                                existing_agent.updated_at = datetime.now()
                            else:
                                new_agent = Agent(
                                    agent_id=ag.get('id', ''),
                                    name=ag.get('name', ag.get('id')),
                                    device_id=existing.id,
                                    model=ag.get('model', ''),
                                    workspace=ag.get('workspace', ''),
                                    agent_dir=ag.get('agent_dir', ''),
                                    status='running',
                                    description=ag.get('description', ''),
                                )
                                db.add(new_agent)
                            agents_synced += 1
            except Exception as e:
                # 远程设备可能没有 /api/agents 接口，跳过
                pass
        
        db.commit()
    finally:
        db.close()

    return {
        "success": True,
        "scanned": scanner.get_stats(),
        "registered": registered,
        "updated": updated,
        "agents_synced": agents_synced,
        "total_found": len(devices),
        "message": f"发现 {len(devices)} 台，新注册 {registered} 台，更新 {updated} 台，同步 {agents_synced} 个 Agent"
    }


@router.get("/api/scan/coverage")
async def get_scan_coverage():
    """获取 agent-client 覆盖率：已注册设备中有多少在持续上报"""
    from database import SessionLocal
    from models import Device

    db = SessionLocal()
    try:
        total = db.query(Device).count()
        # 5 分钟内有上报的视为在线
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(minutes=5)
        active = db.query(Device).filter(Device.last_active >= cutoff).count()
        stale = total - active

        return {
            "total_devices": total,
            "active_reporting": active,
            "stale": stale,
            "coverage_percent": round(active / max(total, 1) * 100, 1),
            "message": f"{active}/{total} 台设备在线上报中"
        }
    finally:
        db.close()


@router.get("/api/scan/stats")
async def get_scan_stats():
    """获取扫描统计"""
    return {
        "status": "ready",
        "supported_ports": [18789, 8000, 8080, 3000, 80, 443],
        "scan_modes": ["quick", "standard", "deep"],
        "max_concurrent": 500
    }

@router.get("/api/scan/fingerprints")
async def get_fingerprints():
    """获取 OpenClaw 指纹列表"""
    return {
        "urls": list(AdvancedScanner.OPENCLAW_FINGERPRINTS.values()),
        "signatures": [s.decode() for s in AdvancedScanner.HTTP_SIGNATURES]
    }
