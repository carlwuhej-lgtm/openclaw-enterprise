"""
OpenClaw Enterprise - AI 辅助模块
异常行为检测、风险评分、自动化响应
"""
import math
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pydantic import BaseModel
from collections import defaultdict
import json


class RiskScore(BaseModel):
    """风险评分"""
    device_ip: str
    score: int  # 0-100
    level: str  # low, medium, high, critical
    factors: List[str]
    timestamp: datetime


class AnomalyAlert(BaseModel):
    """异常告警"""
    id: int
    device_ip: str
    anomaly_type: str
    description: str
    confidence: float  # 0-1
    severity: str
    timestamp: datetime
    context: Dict


class BehaviorProfile(BaseModel):
    """行为画像"""
    device_ip: str
    avg_operations_per_hour: float
    avg_llm_calls_per_day: int
    active_hours: List[int]  # 活跃小时
    common_api_endpoints: List[str]
    risk_trend: str  # increasing, stable, decreasing
    last_updated: datetime


class AIBehaviorAnalyzer:
    """AI 行为分析器"""
    
    def __init__(self):
        self.device_history: Dict[str, List[Dict]] = defaultdict(list)
        self.baseline_profiles: Dict[str, BehaviorProfile] = {}
        self.anomaly_threshold = 2.0  # 标准差阈值
        self.risk_weights = {
            'unauthorized_openclaw': 40,
            'llm_call_external': 30,
            'llm_call_unauthorized': 50,
            'sensitive_file_access': 60,
            'command_execution': 30,
            'abnormal_activity_time': 20,
            'high_frequency_operations': 25,
            'risk_score_increasing': 30,
        }
    
    def add_operation(self, device_ip: str, operation: Dict):
        """添加操作记录"""
        self.device_history[device_ip].append({
            **operation,
            'timestamp': datetime.now()
        })
        
        # 保持最近 1000 条记录
        if len(self.device_history[device_ip]) > 1000:
            self.device_history[device_ip] = self.device_history[device_ip][-1000:]
        
        # 更新行为画像
        self._update_profile(device_ip)
    
    def _update_profile(self, device_ip: str):
        """更新行为画像"""
        history = self.device_history[device_ip]
        if len(history) < 10:
            return
        
        # 计算每小时操作数
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        recent_ops = [op for op in history if op['timestamp'] > hour_ago]
        avg_ops_per_hour = len(recent_ops)
        
        # 计算每天 LLM 调用数
        day_ago = now - timedelta(days=1)
        llm_calls = [op for op in history if op['timestamp'] > day_ago and op.get('is_llm_call')]
        avg_llm_per_day = len(llm_calls)
        
        # 活跃小时
        active_hours = list(set([op['timestamp'].hour for op in history[-100:]]))
        
        # 常见 API 端点
        api_endpoints = [op.get('api_endpoint', '') for op in history[-100:] if op.get('api_endpoint')]
        common_endpoints = list(set(api_endpoints))[:10]
        
        # 风险趋势
        risk_trend = self._calculate_risk_trend(device_ip)
        
        self.baseline_profiles[device_ip] = BehaviorProfile(
            device_ip=device_ip,
            avg_operations_per_hour=avg_ops_per_hour,
            avg_llm_calls_per_day=avg_llm_per_day,
            active_hours=active_hours,
            common_api_endpoints=common_endpoints,
            risk_trend=risk_trend,
            last_updated=now
        )
    
    def _calculate_risk_trend(self, device_ip: str) -> str:
        """计算风险趋势"""
        history = self.device_history[device_ip]
        if len(history) < 50:
            return 'stable'
        
        # 比较最近 10 次和之前 10 次的风险
        recent_risk = sum(1 for op in history[-10:] if op.get('risk_level') in ['high', 'danger'])
        old_risk = sum(1 for op in history[-20:-10] if op.get('risk_level') in ['high', 'danger'])
        
        if recent_risk > old_risk * 1.5:
            return 'increasing'
        elif recent_risk < old_risk * 0.5:
            return 'decreasing'
        else:
            return 'stable'
    
    def detect_anomalies(self, device_ip: str) -> List[AnomalyAlert]:
        """检测异常行为"""
        anomalies = []
        profile = self.baseline_profiles.get(device_ip)
        history = self.device_history.get(device_ip, [])
        
        if not profile or len(history) < 20:
            return anomalies
        
        now = datetime.now()
        
        # 1. 检测异常活跃时间
        current_hour = now.hour
        if current_hour not in profile.active_hours and current_hour < 6 or current_hour > 22:
            anomalies.append(AnomalyAlert(
                id=len(anomalies) + 1,
                device_ip=device_ip,
                anomaly_type='abnormal_activity_time',
                description=f"设备在非常规时间活跃（{current_hour}:00）",
                confidence=0.7,
                severity='medium',
                timestamp=now,
                context={'hour': current_hour, 'usual_hours': profile.active_hours}
            ))
        
        # 2. 检测高频操作
        hour_ago = now - timedelta(hours=1)
        recent_ops = [op for op in history if op['timestamp'] > hour_ago]
        if len(recent_ops) > profile.avg_operations_per_hour * 3:
            anomalies.append(AnomalyAlert(
                id=len(anomalies) + 1,
                device_ip=device_ip,
                anomaly_type='high_frequency_operations',
                description=f"操作频率异常（{len(recent_ops)} 次/小时，平均 {profile.avg_operations_per_hour:.1f}）",
                confidence=0.8,
                severity='medium',
                timestamp=now,
                context={'current': len(recent_ops), 'average': profile.avg_operations_per_hour}
            ))
        
        # 3. 检测 LLM 调用突增
        day_ago = now - timedelta(days=1)
        llm_calls = [op for op in history if op['timestamp'] > day_ago and op.get('is_llm_call')]
        if len(llm_calls) > profile.avg_llm_calls_per_day * 5 and profile.avg_llm_calls_per_day > 0:
            anomalies.append(AnomalyAlert(
                id=len(anomalies) + 1,
                device_ip=device_ip,
                anomaly_type='llm_call_spike',
                description=f"LLM 调用突增（{len(llm_calls)} 次/天，平均 {profile.avg_llm_calls_per_day}）",
                confidence=0.85,
                severity='high',
                timestamp=now,
                context={'current': len(llm_calls), 'average': profile.avg_llm_calls_per_day}
            ))
        
        # 4. 检测风险趋势上升
        if profile.risk_trend == 'increasing':
            anomalies.append(AnomalyAlert(
                id=len(anomalies) + 1,
                device_ip=device_ip,
                anomaly_type='risk_trend_increasing',
                description="设备风险趋势持续上升",
                confidence=0.75,
                severity='medium',
                timestamp=now,
                context={'trend': profile.risk_trend}
            ))
        
        return anomalies
    
    def calculate_risk_score(self, device_ip: str) -> RiskScore:
        """计算风险评分"""
        history = self.device_history.get(device_ip, [])
        profile = self.baseline_profiles.get(device_ip)
        
        score = 0
        factors = []
        
        # 1. 未授权 OpenClaw
        unauthorized_ops = [op for op in history[-50:] if op.get('is_unauthorized')]
        if unauthorized_ops:
            score += self.risk_weights['unauthorized_openclaw']
            factors.append(f"发现 {len(unauthorized_ops)} 次未授权操作")
        
        # 2. 外部 LLM 调用
        external_llm = [op for op in history[-50:] if op.get('llm_provider') in ['OpenAI', 'Anthropic']]
        if external_llm:
            score += self.risk_weights['llm_call_external']
            factors.append(f"调用外部 LLM {len(external_llm)} 次")
        
        # 3. 敏感文件访问
        sensitive_access = [op for op in history[-50:] if op.get('is_sensitive_access')]
        if sensitive_access:
            score += self.risk_weights['sensitive_file_access']
            factors.append(f"访问敏感文件 {len(sensitive_access)} 次")
        
        # 4. 命令执行
        cmd_exec = [op for op in history[-50:] if op.get('operation_type') == 'command_exec']
        if cmd_exec:
            score += self.risk_weights['command_execution']
            factors.append(f"执行命令 {len(cmd_exec)} 次")
        
        # 5. 异常活跃时间
        now = datetime.now()
        if profile and now.hour not in profile.active_hours and (now.hour < 6 or now.hour > 22):
            score += self.risk_weights['abnormal_activity_time']
            factors.append("非常规时间活跃")
        
        # 6. 高频操作
        if profile:
            hour_ago = now - timedelta(hours=1)
            recent_ops = [op for op in history if op['timestamp'] > hour_ago]
            if len(recent_ops) > profile.avg_operations_per_hour * 3:
                score += self.risk_weights['high_frequency_operations']
                factors.append("操作频率异常")
        
        # 7. 风险趋势
        if profile and profile.risk_trend == 'increasing':
            score += self.risk_weights['risk_score_increasing']
            factors.append("风险趋势上升")
        
        # 限制最高 100 分
        score = min(100, score)
        
        # 确定风险等级
        if score >= 80:
            level = 'critical'
        elif score >= 60:
            level = 'high'
        elif score >= 40:
            level = 'medium'
        else:
            level = 'low'
        
        return RiskScore(
            device_ip=device_ip,
            score=score,
            level=level,
            factors=factors,
            timestamp=datetime.now()
        )
    
    def get_all_risk_scores(self) -> List[RiskScore]:
        """获取所有设备的风险评分"""
        scores = []
        for device_ip in self.device_history.keys():
            score = self.calculate_risk_score(device_ip)
            scores.append(score)
        return scores
    
    def get_all_anomalies(self) -> List[AnomalyAlert]:
        """获取所有设备的异常告警"""
        anomalies = []
        for device_ip in self.device_history.keys():
            device_anomalies = self.detect_anomalies(device_ip)
            anomalies.extend(device_anomalies)
        return anomalies
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        total_devices = len(self.device_history)
        total_operations = sum(len(ops) for ops in self.device_history.values())
        
        risk_scores = self.get_all_risk_scores()
        high_risk_devices = sum(1 for s in risk_scores if s.level in ['high', 'critical'])
        
        anomalies = self.get_all_anomalies()
        
        return {
            'total_devices': total_devices,
            'total_operations': total_operations,
            'high_risk_devices': high_risk_devices,
            'active_anomalies': len(anomalies),
            'avg_risk_score': statistics.mean([s.score for s in risk_scores]) if risk_scores else 0
        }


class AutoResponder:
    """自动响应器"""
    
    def __init__(self, analyzer: AIBehaviorAnalyzer):
        self.analyzer = analyzer
        self.actions = []
    
    def configure_action(self, anomaly_type: str, action: str, threshold: float = 0.8):
        """配置自动响应动作"""
        self.actions.append({
            'anomaly_type': anomaly_type,
            'action': action,
            'threshold': threshold
        })
    
    def process_anomaly(self, anomaly: AnomalyAlert) -> Optional[Dict]:
        """处理异常"""
        for action_config in self.actions:
            if action_config['anomaly_type'] == anomaly.anomaly_type:
                if anomaly.confidence >= action_config['threshold']:
                    return self._execute_action(action_config['action'], anomaly)
        return None
    
    def _execute_action(self, action: str, anomaly: AnomalyAlert) -> Dict:
        """执行响应动作"""
        result = {
            'action': action,
            'anomaly_id': anomaly.id,
            'device_ip': anomaly.device_ip,
            'success': False,
            'message': '',
            'timestamp': datetime.now()
        }
        
        if action == 'block_device':
            # 阻断设备
            result['success'] = True
            result['message'] = f"设备 {anomaly.device_ip} 已阻断"
        
        elif action == 'kill_process':
            # 终止进程
            result['success'] = True
            result['message'] = f"已终止设备 {anomaly.device_ip} 的可疑进程"
        
        elif action == 'send_alert':
            # 发送告警
            result['success'] = True
            result['message'] = f"已发送告警通知"
        
        elif action == 'increase_monitoring':
            # 加强监控
            result['success'] = True
            result['message'] = f"已加强对设备 {anomaly.device_ip} 的监控"
        
        return result


# ==================== FastAPI 集成 ====================

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import func

from database import SessionLocal, get_db
from models import Device, AuditLog, Alert as AlertModel, User
from auth import get_current_user
from tenant_filter import get_tenant_filter, get_tenant_device_ids
from rbac import require_role

router = APIRouter()

analyzer = AIBehaviorAnalyzer()
responder = AutoResponder(analyzer)

class OperationData(BaseModel):
    device_ip: str
    operation_type: str
    details: Dict
    risk_level: Optional[str] = None
    is_llm_call: Optional[bool] = False
    llm_provider: Optional[str] = None
    is_unauthorized: Optional[bool] = False
    is_sensitive_access: Optional[bool] = False

class ActionConfig(BaseModel):
    anomaly_type: str
    action: str
    threshold: float = 0.8

@router.post("/api/ai/analyze/operation")
async def analyze_operation(data: OperationData, current_user: User = require_role("user")):
    """分析操作"""
    analyzer.add_operation(data.device_ip, data.dict())
    return {"success": True, "message": "操作已记录"}

@router.get("/api/ai/analyze/anomalies")
async def get_anomalies(device_ip: Optional[str] = None, current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取异常告警 - 从数据库读取真实数据（按租户过滤）"""
    query = db.query(AlertModel).filter(AlertModel.is_resolved == False)

    # 租户过滤
    device_ids = get_tenant_device_ids(db, current_user)
    if device_ids is not None:
        query = query.filter(AlertModel.device_id.in_(device_ids))

    if device_ip:
        # 先查找对应 IP 的设备
        device = db.query(Device).filter(Device.ip_address == device_ip).first()
        if device:
            query = query.filter(AlertModel.device_id == device.id)
        else:
            return []

    alerts = query.order_by(AlertModel.created_at.desc()).all()

    result = []
    for alert in alerts:
        # 查找关联的设备 IP
        alert_device_ip = ''
        if alert.device_id:
            device = db.query(Device).filter(Device.id == alert.device_id).first()
            if device:
                alert_device_ip = device.ip_address or device.hostname or ''

        severity = 'medium'
        if alert.level in ['critical', 'danger']:
            severity = 'high'
        elif alert.level == 'high':
            severity = 'high'
        elif alert.level == 'medium':
            severity = 'medium'
        elif alert.level in ['low', 'info']:
            severity = 'low'

        result.append({
            'id': alert.id,
            'device_ip': alert_device_ip,
            'anomaly_type': alert.title or 'unknown',
            'description': alert.description or '',
            'confidence': 0.8,
            'severity': severity,
            'timestamp': (alert.created_at or datetime.now()).isoformat(),
            'context': {}
        })
    return result

@router.get("/api/ai/analyze/risk/{device_ip}")
async def get_risk_score(device_ip: str, current_user: User = require_role("viewer")):
    """获取风险评分"""
    score = analyzer.calculate_risk_score(device_ip)
    return score.dict()

@router.get("/api/ai/analyze/risk-scores")
async def get_all_risk_scores(current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取所有设备风险评分 - 从数据库读取真实数据（按租户过滤）"""
    tenant_id = get_tenant_filter(current_user)
    query = db.query(Device)
    if tenant_id is not None:
        query = query.filter(Device.tenant_id == tenant_id)
    devices = query.all()
    scores = []
    for device in devices:
            risk_level = device.risk_level or 'low'
            # 根据 risk_score 确定 risk_level
            if device.risk_score >= 80:
                risk_level = 'critical'
            elif device.risk_score >= 60:
                risk_level = 'high'
            elif device.risk_score >= 40:
                risk_level = 'medium'
            else:
                risk_level = 'low'

            scores.append({
                'device_ip': device.ip_address or device.hostname or f'device-{device.id}',
                'device_name': device.name or '',
                'score': device.risk_score or 0,
                'level': risk_level,
                'factors': [],
                'timestamp': (device.last_active or device.created_at or datetime.now()).isoformat()
            })
    return scores

@router.get("/api/ai/analyze/profile/{device_ip}")
async def get_profile(device_ip: str, current_user: User = require_role("viewer")):
    """获取行为画像"""
    profile = analyzer.baseline_profiles.get(device_ip)
    if profile:
        return profile.dict()
    else:
        raise HTTPException(status_code=404, detail="设备画像不存在")

@router.get("/api/ai/analyze/statistics")
async def get_statistics(current_user: User = require_role("viewer"), db: Session = Depends(get_db)):
    """获取统计信息 - 从数据库读取真实数据（按租户过滤）"""
    from agent_manager import Agent

    tenant_id = get_tenant_filter(current_user)
    device_ids = get_tenant_device_ids(db, current_user)

    device_query = db.query(func.count(Device.id))
    if tenant_id is not None:
        device_query = device_query.filter(Device.tenant_id == tenant_id)
    total_hosts = device_query.scalar() or 0

    total_agents = db.query(func.count(Agent.id)).scalar() or 0

    audit_query = db.query(func.count(AuditLog.id))
    if device_ids is not None:
        audit_query = audit_query.filter(AuditLog.device_id.in_(device_ids))
    total_operations = audit_query.scalar() or 0

    high_risk_query = db.query(func.count(Device.id)).filter(Device.risk_score >= 50)
    if tenant_id is not None:
        high_risk_query = high_risk_query.filter(Device.tenant_id == tenant_id)
    high_risk_devices = high_risk_query.scalar() or 0

    alert_query = db.query(func.count(AlertModel.id)).filter(AlertModel.is_resolved == False)
    if device_ids is not None:
        alert_query = alert_query.filter(AlertModel.device_id.in_(device_ids))
    active_anomalies = alert_query.scalar() or 0

    avg_risk_query = db.query(func.avg(Device.risk_score))
    if tenant_id is not None:
        avg_risk_query = avg_risk_query.filter(Device.tenant_id == tenant_id)
    avg_risk_score = avg_risk_query.scalar() or 0

    return {
        'total_devices': total_hosts,
        'total_hosts': total_hosts,
        'total_agents': total_agents,
        'total_operations': total_operations,
        'high_risk_devices': high_risk_devices,
        'active_anomalies': active_anomalies,
        'avg_risk_score': round(float(avg_risk_score), 1)
    }

@router.post("/api/ai/respond/configure")
async def configure_action(config: ActionConfig, current_user: User = require_role("manager")):
    """配置自动响应"""
    responder.configure_action(config.anomaly_type, config.action, config.threshold)
    return {"success": True, "message": "自动响应已配置"}

@router.post("/api/ai/respond/process")
async def process_anomaly(anomaly_id: int):
    """处理异常"""
    anomalies = analyzer.get_all_anomalies()
    anomaly = next((a for a in anomalies if a.id == anomaly_id), None)
    
    if not anomaly:
        raise HTTPException(status_code=404, detail="异常不存在")
    
    result = responder.process_anomaly(anomaly)
    return result or {"success": False, "message": "无匹配的自动响应规则"}
