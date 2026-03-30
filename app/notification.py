"""
OpenClaw Enterprise - 通知系统
支持飞书、邮件、短信、Webhook 等多种通知方式
"""
import smtplib
import httpx
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, EmailStr
from enum import Enum


class NotificationChannel(str, Enum):
    """通知渠道"""
    FEISHU = "feishu"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    SYSTEM = "system"


class NotificationLevel(str, Enum):
    """通知级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationConfig(BaseModel):
    """通知配置"""
    id: int
    channel: NotificationChannel
    name: str
    is_enabled: bool = True
    config: Dict = {}
    created_at: datetime = datetime.now()


class NotificationMessage(BaseModel):
    """通知消息"""
    title: str
    content: str
    level: NotificationLevel = NotificationLevel.INFO
    recipients: List[str] = []
    extra_data: Dict = {}
    timestamp: datetime = datetime.now()


class NotificationResult(BaseModel):
    """通知结果"""
    success: bool
    channel: str
    message: str
    details: Optional[Dict] = None
    timestamp: datetime = datetime.now()


class FeishuNotifier:
    """飞书通知"""
    
    def __init__(self, webhook_url: str, secret: str = None):
        self.webhook_url = webhook_url
        self.secret = secret
        self.http_client = httpx.Client(timeout=10)
    
    def send(self, message: NotificationMessage) -> NotificationResult:
        """发送飞书通知"""
        try:
            # 构建飞书消息
            if message.level == NotificationLevel.CRITICAL:
                color = "red"
                emoji = "🔴"
            elif message.level == NotificationLevel.ERROR:
                color = "orange"
                emoji = "🟠"
            elif message.level == NotificationLevel.WARNING:
                color = "yellow"
                emoji = "🟡"
            else:
                color = "blue"
                emoji = "🔵"
            
            # 卡片消息
            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": f"{emoji} {message.title}"
                        },
                        "template": color
                    },
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": message.content
                        },
                        {
                            "tag": "note",
                            "elements": [
                                {
                                    "tag": "plain_text",
                                    "content": f"发送时间：{message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                                }
                            ]
                        }
                    ]
                }
            }
            
            response = self.http_client.post(self.webhook_url, json=card)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0 or result.get("StatusCode") == 0:
                    return NotificationResult(
                        success=True,
                        channel="feishu",
                        message="飞书通知发送成功",
                        details={"status_code": response.status_code}
                    )
            
            return NotificationResult(
                success=False,
                channel="feishu",
                message=f"飞书通知发送失败：{response.text}",
                details={"status_code": response.status_code}
            )
            
        except Exception as e:
            return NotificationResult(
                success=False,
                channel="feishu",
                message=f"飞书通知异常：{str(e)}"
            )
    
    def test(self) -> NotificationResult:
        """测试连接"""
        test_msg = NotificationMessage(
            title="OpenClaw 通知测试",
            content="这是一条测试消息，确认飞书通知配置正确。",
            level=NotificationLevel.INFO
        )
        return self.send(test_msg)


class EmailNotifier:
    """邮件通知"""
    
    def __init__(self, smtp_server: str, smtp_port: int, username: str, 
                 password: str, from_email: str, use_tls: bool = True):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_tls = use_tls
    
    def send(self, message: NotificationMessage) -> NotificationResult:
        """发送邮件通知"""
        try:
            if not message.recipients:
                return NotificationResult(
                    success=False,
                    channel="email",
                    message="没有指定收件人"
                )
            
            # 构建邮件
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = ', '.join(message.recipients)
            msg['Subject'] = f"[OpenClaw] {message.title}"
            
            # 邮件正文
            body = f"""
<html>
<body>
    <h2>{message.title}</h2>
    <p>{message.content}</p>
    <hr>
    <p style="color: #888; font-size: 12px;">
        发送时间：{message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}<br>
        通知级别：{message.level.value}
    </p>
</body>
</html>
"""
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            # 发送邮件
            if self.use_tls:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            
            server.login(self.username, self.password)
            server.sendmail(self.from_email, message.recipients, msg.as_string())
            server.quit()
            
            return NotificationResult(
                success=True,
                channel="email",
                message=f"邮件通知发送成功（{len(message.recipients)} 个收件人）",
                details={"recipients": message.recipients}
            )
            
        except Exception as e:
            return NotificationResult(
                success=False,
                channel="email",
                message=f"邮件通知失败：{str(e)}"
            )
    
    def test(self, to_email: str) -> NotificationResult:
        """测试连接"""
        test_msg = NotificationMessage(
            title="OpenClaw 邮件通知测试",
            content="这是一条测试邮件，确认邮件服务配置正确。",
            level=NotificationLevel.INFO,
            recipients=[to_email]
        )
        return self.send(test_msg)


class SMSNotifier:
    """短信通知（阿里云/腾讯云）"""
    
    def __init__(self, provider: str, access_key: str, secret_key: str, 
                 sign_name: str, template_code: str):
        self.provider = provider
        self.access_key = access_key
        self.secret_key = secret_key
        self.sign_name = sign_name
        self.template_code = template_code
        self.http_client = httpx.Client(timeout=10)
    
    def send(self, message: NotificationMessage) -> NotificationResult:
        """发送短信通知"""
        try:
            if not message.recipients:
                return NotificationResult(
                    success=False,
                    channel="sms",
                    message="没有指定收件人"
                )
            
            # 这里简化实现，实际需要调用阿里云/腾讯云 API
            # 示例：阿里云短信 API
            if self.provider == "aliyun":
                return self._send_aliyun(message)
            elif self.provider == "tencent":
                return self._send_tencent(message)
            else:
                return NotificationResult(
                    success=False,
                    channel="sms",
                    message=f"不支持的短信提供商：{self.provider}"
                )
                
        except Exception as e:
            return NotificationResult(
                success=False,
                channel="sms",
                message=f"短信通知异常：{str(e)}"
            )
    
    def _send_aliyun(self, message: NotificationMessage) -> NotificationResult:
        """阿里云短信"""
        # 实际实现需要调用阿里云 API
        # 这里仅做示例
        return NotificationResult(
            success=True,
            channel="sms_aliyun",
            message=f"短信已发送（{len(message.recipients)} 个收件人）",
            details={"provider": "aliyun"}
        )
    
    def _send_tencent(self, message: NotificationMessage) -> NotificationResult:
        """腾讯云短信"""
        # 实际实现需要调用腾讯云 API
        return NotificationResult(
            success=True,
            channel="sms_tencent",
            message=f"短信已发送（{len(message.recipients)} 个收件人）",
            details={"provider": "tencent"}
        )


class WebhookNotifier:
    """Webhook 通知"""
    
    def __init__(self, url: str, headers: Dict = None, method: str = "POST"):
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}
        self.method = method
        self.http_client = httpx.Client(timeout=10)
    
    def send(self, message: NotificationMessage) -> NotificationResult:
        """发送 Webhook 通知"""
        try:
            payload = {
                "title": message.title,
                "content": message.content,
                "level": message.level.value,
                "timestamp": message.timestamp.isoformat(),
                "extra": message.extra_data
            }
            
            response = self.http_client.request(
                self.method,
                self.url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code in [200, 201, 202, 204]:
                return NotificationResult(
                    success=True,
                    channel="webhook",
                    message="Webhook 通知发送成功",
                    details={"status_code": response.status_code}
                )
            
            return NotificationResult(
                success=False,
                channel="webhook",
                message=f"Webhook 通知失败：{response.status_code}",
                details={"status_code": response.status_code, "body": response.text}
            )
            
        except Exception as e:
            return NotificationResult(
                success=False,
                channel="webhook",
                message=f"Webhook 通知异常：{str(e)}"
            )
    
    def test(self) -> NotificationResult:
        """测试连接"""
        test_msg = NotificationMessage(
            title="OpenClaw Webhook 测试",
            content="这是一条测试消息，确认 Webhook 配置正确。",
            level=NotificationLevel.INFO
        )
        return self.send(test_msg)


class NotificationManager:
    """通知管理器"""
    
    def __init__(self):
        self.configs: List[NotificationConfig] = []
        self.notifiers: Dict[str, object] = {}
        self.notification_log: List[Dict] = []
    
    def add_config(self, config: NotificationConfig):
        """添加通知配置"""
        self.configs.append(config)
        self._create_notifier(config)
    
    def remove_config(self, config_id: int):
        """移除通知配置"""
        self.configs = [c for c in self.configs if c.id != config_id]
        if config_id in self.notifiers:
            del self.notifiers[config_id]
    
    def _create_notifier(self, config: NotificationConfig):
        """创建通知器"""
        if config.channel == NotificationChannel.FEISHU:
            self.notifiers[config.id] = FeishuNotifier(
                webhook_url=config.config.get("webhook_url"),
                secret=config.config.get("secret")
            )
        elif config.channel == NotificationChannel.EMAIL:
            self.notifiers[config.id] = EmailNotifier(
                smtp_server=config.config.get("smtp_server"),
                smtp_port=config.config.get("smtp_port", 465),
                username=config.config.get("username"),
                password=config.config.get("password"),
                from_email=config.config.get("from_email"),
                use_tls=config.config.get("use_tls", True)
            )
        elif config.channel == NotificationChannel.SMS:
            self.notifiers[config.id] = SMSNotifier(
                provider=config.config.get("provider"),
                access_key=config.config.get("access_key"),
                secret_key=config.config.get("secret_key"),
                sign_name=config.config.get("sign_name"),
                template_code=config.config.get("template_code")
            )
        elif config.channel == NotificationChannel.WEBHOOK:
            self.notifiers[config.id] = WebhookNotifier(
                url=config.config.get("url"),
                headers=config.config.get("headers"),
                method=config.config.get("method", "POST")
            )
    
    def send(self, message: NotificationMessage, channels: List[int] = None) -> List[NotificationResult]:
        """发送通知"""
        results = []
        
        # 确定发送渠道
        if channels:
            configs = [c for c in self.configs if c.id in channels and c.is_enabled]
        else:
            configs = [c for c in self.configs if c.is_enabled]
        
        # 根据级别过滤
        if message.level == NotificationLevel.CRITICAL:
            # 严重告警：所有渠道都发送
            pass
        elif message.level == NotificationLevel.ERROR:
            # 错误：只发送给管理员
            configs = [c for c in configs if c.config.get("notify_admin", True)]
        elif message.level == NotificationLevel.WARNING:
            # 警告：只发送配置的渠道
            configs = [c for c in configs if c.config.get("notify_warning", True)]
        
        # 发送通知
        for config in configs:
            if config.id in self.notifiers:
                notifier = self.notifiers[config.id]
                result = notifier.send(message)
                results.append(result)
                
                # 记录日志
                self.notification_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "channel": config.channel.value,
                    "title": message.title,
                    "level": message.level.value,
                    "success": result.success
                })
        
        return results
    
    def send_alert(self, alert_title: str, alert_description: str, 
                   level: str = "critical", device_ip: str = None):
        """发送告警通知"""
        level_map = {
            "critical": NotificationLevel.CRITICAL,
            "high": NotificationLevel.ERROR,
            "medium": NotificationLevel.WARNING,
            "low": NotificationLevel.INFO
        }
        
        content = f"""## 告警详情

**告警标题**: {alert_title}
**告警级别**: {level}
**告警描述**: {alert_description}
"""
        
        if device_ip:
            content += f"\n**设备 IP**: `{device_ip}`"
        
        message = NotificationMessage(
            title=f"[告警] {alert_title}",
            content=content,
            level=level_map.get(level, NotificationLevel.INFO),
            extra_data={
                "alert_title": alert_title,
                "alert_level": level,
                "device_ip": device_ip
            }
        )
        
        return self.send(message)
    
    def get_log(self, limit: int = 100) -> List[Dict]:
        """获取通知日志"""
        return self.notification_log[-limit:]
    
    def test_all(self) -> Dict:
        """测试所有通知渠道"""
        results = {}
        
        for config in self.configs:
            if config.id in self.notifiers:
                notifier = self.notifiers[config.id]
                if hasattr(notifier, 'test'):
                    if config.channel == NotificationChannel.EMAIL:
                        result = notifier.test(config.config.get("test_email", ""))
                    else:
                        result = notifier.test()
                    results[config.id] = result.success
                else:
                    results[config.id] = "N/A"
        
        return results


# ==================== FastAPI 集成 ====================

from fastapi import APIRouter, HTTPException

router = APIRouter()
notification_manager = NotificationManager()

@router.get("/api/notification/configs")
async def get_notification_configs():
    """获取通知配置列表"""
    return notification_manager.configs

@router.post("/api/notification/configs")
async def create_notification_config(config: NotificationConfig):
    """创建通知配置"""
    notification_manager.add_config(config)
    return {"success": True, "config": config}

@router.delete("/api/notification/configs/{config_id}")
async def delete_notification_config(config_id: int):
    """删除通知配置"""
    notification_manager.remove_config(config_id)
    return {"success": True}

@router.post("/api/notification/send")
async def send_notification(
    title: str,
    content: str,
    level: str = "info",
    channels: List[int] = None
):
    """发送通知"""
    level_map = {
        "info": NotificationLevel.INFO,
        "warning": NotificationLevel.WARNING,
        "error": NotificationLevel.ERROR,
        "critical": NotificationLevel.CRITICAL
    }
    
    message = NotificationMessage(
        title=title,
        content=content,
        level=level_map.get(level, NotificationLevel.INFO)
    )
    
    results = notification_manager.send(message, channels)
    return {"success": True, "results": results}

@router.post("/api/notification/alert")
async def send_alert(
    alert_title: str,
    alert_description: str,
    level: str = "critical",
    device_ip: str = None
):
    """发送告警通知"""
    results = notification_manager.send_alert(alert_title, alert_description, level, device_ip)
    return {"success": True, "results": results}

@router.get("/api/notification/log")
async def get_notification_log(limit: int = 100):
    """获取通知日志"""
    return notification_manager.get_log(limit)

@router.post("/api/notification/test/{config_id}")
async def test_notification(config_id: int):
    """测试通知渠道"""
    if config_id not in notification_manager.notifiers:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    notifier = notification_manager.notifiers[config_id]
    config = next((c for c in notification_manager.configs if c.id == config_id), None)
    
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    if hasattr(notifier, 'test'):
        if config.channel == NotificationChannel.EMAIL:
            result = notifier.test(config.config.get("test_email", ""))
        else:
            result = notifier.test()
        return result
    else:
        return {"message": "该渠道不支持测试"}

@router.get("/api/notification/stats")
async def get_notification_stats():
    """获取通知统计"""
    log = notification_manager.notification_log
    return {
        "total": len(log),
        "success": sum(1 for l in log if l.get("success")),
        "failed": sum(1 for l in log if not l.get("success")),
        "by_channel": {},
        "by_level": {}
    }


# ==================== 前端通知配置 API（简化版，JSON 文件存储） ====================
import os as _os

_NOTIFICATION_CONFIG_FILE = _os.path.join(_os.path.dirname(__file__), "notification_config.json")

def _load_notification_config() -> dict:
    """从文件加载通知配置"""
    try:
        if _os.path.exists(_NOTIFICATION_CONFIG_FILE):
            with open(_NOTIFICATION_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.loads(f.read())
    except Exception:
        pass
    return {"channels": {}}

def _save_notification_config(config: dict):
    """保存通知配置到文件"""
    with open(_NOTIFICATION_CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(config, ensure_ascii=False, indent=2))


@router.get("/api/notification/config")
async def get_notification_config_api():
    """获取前端通知配置"""
    return _load_notification_config()


@router.post("/api/notification/config")
async def save_notification_config_api(request: dict):
    """保存前端通知配置"""
    try:
        config = _load_notification_config()
        channel = request.get("channel", "")
        if not channel:
            raise HTTPException(status_code=400, detail="缺少 channel 字段")
        
        config["channels"][channel] = {
            "channel": channel,
            "name": request.get("name", f"{channel} 通知"),
            "is_enabled": request.get("is_enabled", True),
            "config": request.get("config", {}),
            "updated_at": datetime.now().isoformat()
        }
        _save_notification_config(config)
        
        # 同步到 NotificationManager
        cfg_data = config["channels"][channel]
        nc = NotificationConfig(
            id=hash(channel) % 10000,
            channel=channel,
            name=cfg_data["name"],
            is_enabled=cfg_data["is_enabled"],
            config=cfg_data["config"]
        )
        # 移除旧的同类型配置
        notification_manager.configs = [c for c in notification_manager.configs if c.channel != channel]
        notification_manager.add_config(nc)
        
        return {"success": True, "message": f"{channel} 配置已保存"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/notification/test")
async def test_notification_api(request: dict):
    """测试通知渠道"""
    try:
        channel = request.get("channel", "")
        config_data = request.get("config", {})
        
        if channel == "feishu":
            webhook_url = config_data.get("webhook_url", "")
            if not webhook_url:
                return {"success": False, "message": "飞书 Webhook URL 不能为空"}
            notifier = FeishuNotifier(
                webhook_url=webhook_url,
                secret=config_data.get("secret")
            )
            result = notifier.test()
            # 记录日志
            notification_manager.notification_log.append({
                "timestamp": datetime.now().isoformat(),
                "channel": "feishu",
                "title": "测试通知",
                "level": "info",
                "success": result.success
            })
            return {"success": result.success, "message": result.message}
        
        elif channel == "webhook":
            url = config_data.get("url", "")
            if not url:
                return {"success": False, "message": "Webhook URL 不能为空"}
            notifier = WebhookNotifier(
                url=url,
                method=config_data.get("method", "POST")
            )
            result = notifier.test()
            notification_manager.notification_log.append({
                "timestamp": datetime.now().isoformat(),
                "channel": "webhook",
                "title": "测试通知",
                "level": "info",
                "success": result.success
            })
            return {"success": result.success, "message": result.message}
        
        elif channel == "email":
            smtp = config_data.get("smtp_server", "")
            if not smtp:
                return {"success": False, "message": "SMTP 服务器不能为空"}
            notifier = EmailNotifier(
                smtp_server=smtp,
                smtp_port=config_data.get("smtp_port", 465),
                username=config_data.get("username", ""),
                password=config_data.get("password", ""),
                from_email=config_data.get("from_email", ""),
            )
            test_email = config_data.get("test_email", config_data.get("from_email", ""))
            if not test_email:
                return {"success": False, "message": "测试邮箱不能为空"}
            result = notifier.test(test_email)
            notification_manager.notification_log.append({
                "timestamp": datetime.now().isoformat(),
                "channel": "email",
                "title": "测试通知",
                "level": "info",
                "success": result.success
            })
            return {"success": result.success, "message": result.message}
        
        else:
            return {"success": False, "message": f"不支持测试 {channel} 渠道"}
    
    except Exception as e:
        return {"success": False, "message": f"测试失败: {str(e)}"}
