"""
OpenClaw Enterprise - 外置日志中心
通过 syslog/rsyslog 接收系统日志
"""
import socket
import threading
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, Index
from sqlalchemy.orm import Session, relationship

from database import Base, engine, SessionLocal, get_db
from auth import get_current_user
from models import User
from tenant_filter import get_tenant_filter
from rbac import require_role


# ==================== 数据库模型 ====================

class SyslogEntry(Base):
    """系统日志条目"""
    __tablename__ = "syslog_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True, default=datetime.now)
    facility = Column(String(50))  # 设施：kern, user, mail, daemon, auth, syslog, lpr, news, uucp, cron, authpriv, ftp, local0-7
    severity = Column(String(50))  # 严重性：emerg, alert, crit, err, warning, notice, info, debug
    hostname = Column(String(255), index=True)
    app_name = Column(String(255), index=True)
    process_id = Column(Integer)
    message = Column(Text)
    raw_message = Column(Text)
    source_ip = Column(String(50))
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)
    
    # 索引
    __table_args__ = (
        Index('idx_syslog_time_host', 'timestamp', 'hostname'),
        Index('idx_syslog_severity', 'severity'),
    )


# 创建表
Base.metadata.create_all(bind=engine)


# ==================== Pydantic 模型 ====================

class SyslogEntryCreate(BaseModel):
    facility: str
    severity: str
    hostname: str
    app_name: Optional[str] = None
    process_id: Optional[int] = None
    message: str
    source_ip: Optional[str] = None


class SyslogEntryResponse(BaseModel):
    id: int
    timestamp: datetime
    facility: str
    severity: str
    hostname: str
    app_name: Optional[str]
    process_id: Optional[int]
    message: str
    source_ip: Optional[str]
    
    class Config:
        from_attributes = True


class SyslogStats(BaseModel):
    total_entries: int
    entries_24h: int
    by_severity: Dict[str, int]
    by_facility: Dict[str, int]
    top_hosts: List[Dict]


# ==================== Syslog 服务器 ====================

class SyslogServer:
    """Syslog 服务器（UDP + TCP）"""
    
    # Syslog 设施映射
    FACILITY_MAP = {
        '0': 'kern', '1': 'user', '2': 'mail', '3': 'daemon',
        '4': 'auth', '5': 'syslog', '6': 'lpr', '7': 'news',
        '8': 'uucp', '9': 'cron', '10': 'authpriv', '11': 'ftp',
        '16': 'local0', '17': 'local1', '18': 'local2', '19': 'local3',
        '20': 'local4', '21': 'local5', '22': 'local6', '23': 'local7',
    }
    
    # Syslog 严重性映射
    SEVERITY_MAP = {
        '0': 'emerg', '1': 'alert', '2': 'crit', '3': 'err',
        '4': 'warning', '5': 'notice', '6': 'info', '7': 'debug',
    }
    
    def __init__(self, udp_port: int = 514, tcp_port: int = 514):
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.running = False
        self.udp_socket = None
        self.tcp_socket = None
        self.udp_thread = None
        self.tcp_thread = None
        self.db = None
    
    def parse_syslog_message(self, data: bytes, source_ip: str) -> Optional[SyslogEntryCreate]:
        """解析 syslog 消息"""
        try:
            message = data.decode('utf-8', errors='ignore').strip()
            
            # RFC 3164 格式：<PRI>TIMESTAMP HOSTNAME TAG: MSG
            # RFC 5424 格式：<PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
            
            pri_match = re.match(r'^<(\d+)>(.*)', message)
            if not pri_match:
                # 无 PRI 头，尝试直接解析
                return SyslogEntryCreate(
                    facility='user',
                    severity='info',
                    hostname=source_ip,
                    app_name='unknown',
                    message=message,
                    source_ip=source_ip
                )
            
            pri = int(pri_match.group(1))
            remainder = pri_match.group(2)
            
            facility_num = (pri >> 3) & 0x1F
            severity_num = pri & 0x07
            
            facility = self.FACILITY_MAP.get(str(facility_num * 8), f'facility{facility_num}')
            severity = self.SEVERITY_MAP.get(str(severity_num), f'severity{severity_num}')
            
            # 解析剩余部分
            parts = remainder.split(' ', 3)
            
            hostname = parts[1] if len(parts) > 1 else source_ip
            tag = parts[2] if len(parts) > 2 else 'unknown'
            msg = parts[3] if len(parts) > 3 else ''
            
            # 提取进程 ID
            pid = None
            app_name = tag
            if ':' in tag:
                app_name, pid_str = tag.split(':', 1)
                pid_match = re.match(r'(\d+)', pid_str)
                if pid_match:
                    pid = int(pid_match.group(1))
            
            return SyslogEntryCreate(
                facility=facility,
                severity=severity,
                hostname=hostname,
                app_name=app_name,
                process_id=pid,
                message=msg,
                source_ip=source_ip
            )
        except Exception as e:
            print(f"Syslog parse error: {e}")
            return None
    
    def save_entry(self, entry: SyslogEntryCreate):
        """保存日志条目到数据库"""
        try:
            if self.db is None:
                self.db = SessionLocal()
            
            db_entry = SyslogEntry(**entry.dict())
            self.db.add(db_entry)
            self.db.commit()
        except Exception as e:
            print(f"Syslog save error: {e}")
            if self.db:
                self.db.rollback()
    
    def start_udp_server(self):
        """启动 UDP syslog 服务器"""
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.bind(('0.0.0.0', self.udp_port))
        self.udp_socket.settimeout(1.0)
        
        print(f"📡 Syslog UDP server started on port {self.udp_port}")
        
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(65535)
                source_ip = addr[0]
                
                entry = self.parse_syslog_message(data, source_ip)
                if entry:
                    self.save_entry(entry)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"UDP syslog error: {e}")
    
    def start_tcp_server(self):
        """启动 TCP syslog 服务器"""
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_socket.bind(('0.0.0.0', self.tcp_port))
        self.tcp_socket.listen(5)
        self.tcp_socket.settimeout(1.0)
        
        print(f"📡 Syslog TCP server started on port {self.tcp_port}")
        
        while self.running:
            try:
                conn, addr = self.tcp_socket.accept()
                threading.Thread(
                    target=self.handle_tcp_client,
                    args=(conn, addr),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"TCP syslog accept error: {e}")
    
    def handle_tcp_client(self, conn: socket.socket, addr: tuple):
        """处理 TCP syslog 客户端"""
        source_ip = addr[0]
        buffer = b''
        
        try:
            conn.settimeout(30.0)
            while self.running:
                data = conn.recv(4096)
                if not data:
                    break
                
                buffer += data
                
                # 按行处理
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line.strip():
                        entry = self.parse_syslog_message(line, source_ip)
                        if entry:
                            self.save_entry(entry)
        except Exception as e:
            print(f"TCP client error: {e}")
        finally:
            conn.close()
    
    def start(self):
        """启动 syslog 服务器"""
        self.running = True
        
        # 启动 UDP 服务器
        self.udp_thread = threading.Thread(target=self.start_udp_server, daemon=True)
        self.udp_thread.start()
        
        # 启动 TCP 服务器
        self.tcp_thread = threading.Thread(target=self.start_tcp_server, daemon=True)
        self.tcp_thread.start()
        
        print("✅ Syslog server started (UDP + TCP)")
    
    def stop(self):
        """停止 syslog 服务器"""
        self.running = False
        if self.udp_socket:
            self.udp_socket.close()
        if self.tcp_socket:
            self.tcp_socket.close()
        if self.db:
            self.db.close()
        print("🛑 Syslog server stopped")


# 全局 syslog 服务器实例（使用高端口，不需要 root）
syslog_server = SyslogServer(udp_port=1514, tcp_port=1514)


# ==================== 日志转发配置 ====================

class LogForwardTarget(BaseModel):
    """日志转发目标配置"""
    id: int
    name: str
    host: str
    port: int
    protocol: str  # udp/tcp
    enabled: bool
    facility: Optional[str] = None  # 转发特定设施
    severity_min: Optional[str] = None  # 最小严重性
    created_at: datetime


# 日志转发目标（存数据库）
class LogForwardTargetDB(Base):
    __tablename__ = "log_forward_targets"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    host = Column(String(255))
    port = Column(Integer)
    protocol = Column(String(10))  # udp/tcp
    enabled = Column(Boolean, default=True)
    facility = Column(String(50), nullable=True)
    severity_min = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

Base.metadata.create_all(bind=engine)

# 内存存储转发器
forwarders: Dict[int, socket.socket] = {}


# ==================== FastAPI 路由 ====================

router = APIRouter(tags=["日志中心"])


@router.post("/api/syslog/start")
async def start_syslog_server(current_user: User = require_role("admin")):
    """启动 syslog 服务器"""
    try:
        syslog_server.start()
        return {"success": True, "message": "Syslog 服务器已启动", "ports": {"udp": 514, "tcp": 514}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动失败：{str(e)}")


@router.post("/api/syslog/stop")
async def stop_syslog_server(current_user: User = require_role("admin")):
    """停止 syslog 服务器"""
    syslog_server.stop()
    return {"success": True, "message": "Syslog 服务器已停止"}


@router.get("/api/syslog/status")
async def get_syslog_status(current_user: User = require_role("viewer")):
    """获取 syslog 服务器状态"""
    return {
        "running": syslog_server.running,
        "udp_port": syslog_server.udp_port,
        "tcp_port": syslog_server.tcp_port,
    }


@router.get("/api/syslog/entries/{entry_id}")
async def get_syslog_entry(
    entry_id: int,
    current_user: User = require_role("viewer"),
    db: Session = Depends(get_db)
):
    """获取单条日志详情"""
    entry = db.query(SyslogEntry).filter(SyslogEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="日志不存在")
    return entry


@router.get("/api/syslog/entries")
async def get_syslog_entries(
    page: int = 1,
    page_size: int = 50,
    hostname: Optional[str] = None,
    severity: Optional[str] = None,
    facility: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = require_role("viewer"),
    db: Session = Depends(get_db)
):
    """获取 syslog 条目（分页 + 过滤）"""
    query = db.query(SyslogEntry)
    
    # 租户隔离
    tenant_id = get_tenant_filter(current_user)
    if tenant_id is not None:
        query = query.filter(SyslogEntry.tenant_id == tenant_id)
    
    # 过滤
    if hostname:
        query = query.filter(SyslogEntry.hostname == hostname)
    if severity:
        query = query.filter(SyslogEntry.severity == severity)
    if facility:
        query = query.filter(SyslogEntry.facility == facility)
    if search:
        query = query.filter(SyslogEntry.message.contains(search))
    
    # 分页
    total = query.count()
    items = query.order_by(SyslogEntry.timestamp.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/syslog/stats")
async def get_syslog_stats(current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取 syslog 统计信息"""
    from sqlalchemy import func
    
    # 租户隔离
    tenant_id = get_tenant_filter(current_user)
    base_query = db.query(SyslogEntry)
    if tenant_id is not None:
        base_query = base_query.filter(SyslogEntry.tenant_id == tenant_id)
    
    # 总数
    total = base_query.count()
    
    # 24 小时数量
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(hours=24)
    entries_24h = base_query.filter(SyslogEntry.timestamp >= cutoff).count()
    
    # 按严重性统计
    by_severity = dict(base_query.with_entities(
        SyslogEntry.severity, func.count(SyslogEntry.id)
    ).group_by(SyslogEntry.severity).all())
    
    # 按设施统计
    by_facility = dict(base_query.with_entities(
        SyslogEntry.facility, func.count(SyslogEntry.id)
    ).group_by(SyslogEntry.facility).all())
    
    # Top 主机
    top_hosts = base_query.with_entities(
        SyslogEntry.hostname, func.count(SyslogEntry.id).label('count')
    ).group_by(SyslogEntry.hostname).order_by(
        func.count(SyslogEntry.id).desc()
    ).limit(10).all()
    
    return {
        "total_entries": total,
        "entries_24h": entries_24h,
        "by_severity": by_severity,
        "by_facility": by_facility,
        "top_hosts": [{"hostname": h[0], "count": h[1]} for h in top_hosts],
    }


@router.delete("/api/syslog/clear")
async def clear_syslog_entries(
    days: int = 30,
    current_user: User = require_role("admin"),
    db: Session = Depends(get_db)
):
    """清理旧日志（保留最近 N 天）"""
    from datetime import timedelta
    
    cutoff = datetime.now() - timedelta(days=days)
    
    # 租户隔离
    tenant_id = get_tenant_filter(current_user)
    query = db.query(SyslogEntry).filter(SyslogEntry.timestamp < cutoff)
    if tenant_id is not None:
        query = query.filter(SyslogEntry.tenant_id == tenant_id)
    
    count = query.delete(synchronize_session=False)
    db.commit()
    
    return {"success": True, "message": f"已清理 {count} 条旧日志", "deleted": count}


# ==================== 远程日志源管理 ====================

@router.get("/api/syslog/forward-targets")
async def get_forward_targets(current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取日志转发目标列表"""
    targets = db.query(LogForwardTargetDB).order_by(LogForwardTargetDB.created_at.desc()).all()
    return {"targets": targets}


@router.post("/api/syslog/forward-targets")
async def create_forward_target(
    target: dict,
    current_user: User = require_role("admin"),
    db: Session = Depends(get_db)
):
    """添加日志转发目标"""
    db_target = LogForwardTargetDB(
        name=target.get('name', 'Unknown'),
        host=target.get('host'),
        port=target.get('port', 514),
        protocol=target.get('protocol', 'udp'),
        enabled=target.get('enabled', True),
        facility=target.get('facility'),
        severity_min=target.get('severity_min')
    )
    db.add(db_target)
    db.commit()
    db.refresh(db_target)
    
    print(f"📡 添加日志转发目标：{db_target.name} ({db_target.host}:{db_target.port})")
    
    return {"success": True, "message": f"已添加转发目标：{db_target.name}", "id": db_target.id}


@router.delete("/api/syslog/forward-targets/{target_id}")
async def delete_forward_target(
    target_id: int,
    current_user: User = require_role("admin"),
    db: Session = Depends(get_db)
):
    """删除日志转发目标"""
    target = db.query(LogForwardTargetDB).filter(LogForwardTargetDB.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    # 关闭连接
    if target_id in forwarders:
        forwarders[target_id].close()
        del forwarders[target_id]
    
    db.delete(target)
    db.commit()
    
    return {"success": True, "message": "已删除转发目标"}


@router.post("/api/syslog/forward-targets/{target_id}/toggle")
async def toggle_forward_target(
    target_id: int,
    current_user: User = require_role("admin"),
    db: Session = Depends(get_db)
):
    """切换转发目标状态"""
    target = db.query(LogForwardTargetDB).filter(LogForwardTargetDB.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    target.enabled = not target.enabled
    db.commit()
    
    return {"success": True, "enabled": target.enabled}


@router.post("/api/syslog/forward-targets/{target_id}/test")
async def test_forward_target(
    target_id: int,
    current_user: User = require_role("admin"),
    db: Session = Depends(get_db)
):
    """测试转发目标连接"""
    target = db.query(LogForwardTargetDB).filter(LogForwardTargetDB.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM if target.protocol == 'tcp' else socket.SOCK_DGRAM)
        sock.settimeout(3)
        if target.protocol == 'tcp':
            sock.connect((target.host, target.port))
        else:
            sock.connect((target.host, target.port))
        sock.close()
        return {"success": True, "message": f"连接 {target.host}:{target.port} 成功"}
    except Exception as e:
        return {"success": False, "message": f"连接失败：{str(e)}"}


@router.post("/api/syslog/test")
async def send_test_syslog(
    data: dict,
    current_user: User = require_role("user"),
    db: Session = Depends(get_db)
):
    """发送测试日志"""
    entry = SyslogEntry(
        facility='user',
        severity=data.get('severity', 'info'),
        hostname='localhost',
        app_name='OpenClaw-Test',
        message=data.get('message', '测试日志'),
        source_ip='127.0.0.1'
    )
    db.add(entry)
    db.commit()
    
    # 如果有转发配置，同时转发
    await forward_syslog_entry(entry)
    
    return {"success": True, "message": "测试日志已发送", "id": entry.id}


# ==================== 日志转发功能 ====================

SEVERITY_LEVELS = {'debug': 7, 'info': 6, 'notice': 5, 'warning': 4, 'err': 3, 'crit': 2, 'alert': 1, 'emerg': 0}

def get_forward_socket(target: LogForwardTargetDB) -> Optional[socket.socket]:
    """获取或创建转发 socket"""
    if target.id in forwarders:
        return forwarders[target.id]
    
    try:
        if target.protocol == 'udp':
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect((target.host, target.port))
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((target.host, target.port))
        
        forwarders[target.id] = sock
        return sock
    except Exception as e:
        print(f"Forward socket error: {e}")
        return None


async def forward_syslog_entry(entry: SyslogEntry):
    """转发日志到所有启用的目标"""
    db = SessionLocal()
    try:
        targets = db.query(LogForwardTargetDB).filter(LogForwardTargetDB.enabled == True).all()
        
        for target in targets:
            # 检查严重性过滤
            if target.severity_min:
                entry_level = SEVERITY_LEVELS.get(entry.severity, 6)
                min_level = SEVERITY_LEVELS.get(target.severity_min, 6)
                if entry_level > min_level:
                    continue
            
            # 检查设施过滤
            if target.facility and entry.facility != target.facility:
                continue
            
            # 构建 syslog 消息
            pri = (3 << 3) | SEVERITY_LEVELS.get(entry.severity, 6)  # user facility
            timestamp = entry.timestamp.strftime('%b %d %H:%M:%S') if entry.timestamp else datetime.now().strftime('%b %d %H:%M:%S')
            msg = f"<{pri}>{timestamp} {entry.hostname} {entry.app_name or 'unknown'}: {entry.message}"
            
            # 发送
            sock = get_forward_socket(target)
            if sock:
                try:
                    if target.protocol == 'udp':
                        sock.sendto(msg.encode(), (target.host, target.port))
                    else:
                        sock.sendall(msg.encode() + b'\n')
                except Exception as e:
                    print(f"Forward send error: {e}")
                    if target.id in forwarders:
                        forwarders[target.id].close()
                        del forwarders[target.id]
    finally:
        db.close()


# 在保存日志时自动转发
from sqlalchemy import event

@event.listens_for(SyslogEntry, "after_insert")
def receive_after_insert(mapper, connection, target):
    """日志插入后自动转发"""
    # 注意：这里不能直接用 async，实际项目应该用消息队列
    pass


# ==================== 自动启动 ====================

def auto_start_syslog():
    """自动启动 syslog 服务器"""
    try:
        # 检查端口是否被占用
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp_sock.bind(('0.0.0.0', 514))
            udp_sock.close()
            # 端口可用，启动服务器
            syslog_server.start()
        except OSError:
            print("⚠️ Syslog port 514 already in use, skipping auto-start")
    except Exception as e:
        print(f"Syslog auto-start error: {e}")
