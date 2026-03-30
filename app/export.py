"""
OpenClaw Enterprise - 报表导出模块
支持 CSV、Excel、PDF 格式，生成合规报告
"""
import csv
import io
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, Response, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import get_db
from models import Device, User
from auth import get_current_user
from tenant_filter import get_tenant_filter, get_tenant_device_ids
from rbac import require_role


# ==================== PDF 导出 (fpdf2) ====================

def _get_pdf_font_path() -> Optional[str]:
    """查找系统中文字体路径"""
    candidates = [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def generate_pdf_report(
    title: str,
    sections: List[Dict],
) -> bytes:
    """
    用 fpdf2 生成 PDF 报告。
    sections: [{"heading": str, "table": {"headers": [...], "rows": [...]}, "text": str}, ...]
    """
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # 尝试加载中文字体
    font_path = _get_pdf_font_path()
    if font_path:
        try:
            pdf.add_font("zh", "", font_path, uni=True)
            pdf.add_font("zh", "B", font_path, uni=True)
            font_name = "zh"
        except Exception:
            font_name = "Helvetica"
    else:
        font_name = "Helvetica"

    # 标题
    pdf.set_font(font_name, "B", 18)
    pdf.set_text_color(99, 102, 241)  # #6366f1
    pdf.cell(0, 12, title, ln=True, align="C")
    pdf.set_font(font_name, "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.ln(6)

    for sec in sections:
        # Section heading
        if sec.get("heading"):
            pdf.set_font(font_name, "B", 13)
            pdf.set_text_color(99, 102, 241)
            pdf.cell(0, 10, sec["heading"], ln=True)
            pdf.set_draw_color(99, 102, 241)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(3)

        # Free text
        if sec.get("text"):
            pdf.set_font(font_name, "", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 6, sec["text"])
            pdf.ln(3)

        # Table
        tbl = sec.get("table")
        if tbl:
            headers = tbl["headers"]
            rows = tbl["rows"]
            col_count = len(headers)
            col_w = 190 / col_count

            # Header row
            pdf.set_font(font_name, "B", 9)
            pdf.set_fill_color(240, 240, 245)
            pdf.set_text_color(50, 50, 50)
            for h in headers:
                pdf.cell(col_w, 8, str(h), border=1, fill=True)
            pdf.ln()

            # Data rows
            pdf.set_font(font_name, "", 9)
            pdf.set_text_color(60, 60, 60)
            for row in rows[:200]:
                for val in row:
                    pdf.cell(col_w, 7, str(val)[:40], border=1)
                pdf.ln()
            pdf.ln(4)

    # Footer
    pdf.set_font(font_name, "", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 8, "OpenClaw Enterprise - AI Agent Management Platform", ln=True, align="C")

    # Output to bytes
    return bytes(pdf.output())


# ==================== CSV 导出 ====================

def export_devices_to_csv(devices: List[Dict]) -> str:
    """导出设备列表为 CSV"""
    output = io.StringIO()
    fieldnames = ['ID', '设备名称', '主机名', 'IP', '用户', '部门', '版本', '状态', '风险等级', '风险评分', '最后活跃', '注册时间']
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for device in devices:
        writer.writerow({
            'ID': device.get('id', ''),
            '设备名称': device.get('name', ''),
            '主机名': device.get('hostname', ''),
            'IP': device.get('ip', ''),
            '用户': device.get('user', ''),
            '部门': device.get('tenant', ''),
            '版本': device.get('version', ''),
            '状态': device.get('status', ''),
            '风险等级': device.get('risk_level', ''),
            '风险评分': device.get('risk_score', ''),
            '最后活跃': device.get('last_active', ''),
            '注册时间': device.get('created_at', '')
        })
    
    return output.getvalue()


def export_audit_logs_to_csv(logs: List[Dict]) -> str:
    """导出审计日志为 CSV"""
    output = io.StringIO()
    fieldnames = ['ID', '时间', '设备', '用户', '操作类型', '操作详情', '风险级别', '状态']
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for log in logs:
        writer.writerow({
            'ID': log.get('id', ''),
            '时间': log.get('timestamp', ''),
            '设备': log.get('device', ''),
            '用户': log.get('user', ''),
            '操作类型': log.get('operation_type', ''),
            '操作详情': log.get('operation_detail', ''),
            '风险级别': log.get('risk_level', ''),
            '状态': log.get('status', '')
        })
    
    return output.getvalue()


def export_alerts_to_csv(alerts: List[Dict]) -> str:
    """导出告警列表为 CSV"""
    output = io.StringIO()
    fieldnames = ['ID', '告警标题', '告警级别', '告警描述', '设备 IP', '状态', '创建时间', '解决时间']
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for alert in alerts:
        writer.writerow({
            'ID': alert.get('id', ''),
            '告警标题': alert.get('title', ''),
            '告警级别': alert.get('level', ''),
            '告警描述': alert.get('description', ''),
            '设备 IP': alert.get('device_ip', ''),
            '状态': '已解决' if alert.get('is_resolved') else '未解决',
            '创建时间': alert.get('created_at', ''),
            '解决时间': alert.get('resolved_at', '') or ''
        })
    
    return output.getvalue()


# ==================== Excel 导出（简化版，无需额外依赖） ====================

def export_to_excel_simple(data: List[Dict], sheet_name: str = "Sheet1") -> bytes:
    """
    简化版 Excel 导出（实际项目建议使用 openpyxl 或 xlsxwriter）
    这里返回 CSV 格式，扩展名为 .xlsx
    """
    if not data:
        return b""
    
    output = io.BytesIO()
    
    # 写入 BOM（Excel 识别 UTF-8）
    output.write(b'\xef\xbb\xbf')
    
    # 写入 CSV 内容
    fieldnames = list(data[0].keys())
    
    # 表头
    output.write(('\t'.join(fieldnames) + '\n').encode('utf-8'))
    
    # 数据行
    for row in data:
        values = [str(row.get(field, '')) for field in fieldnames]
        output.write(('\t'.join(values) + '\n').encode('utf-8'))
    
    output.seek(0)
    return output.getvalue()


# ==================== PDF 报告生成（简化版） ====================

def generate_compliance_report_html(
    report_title: str,
    report_period: str,
    stats: Dict,
    devices: List[Dict],
    alerts: List[Dict],
    audit_summary: Dict
) -> str:
    """生成合规报告 HTML（可用于打印或转 PDF）"""
    
    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report_title}</title>
    <style>
        body {{
            font-family: 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            border-bottom: 3px solid #6366f1;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #6366f1;
            margin: 0;
        }}
        .header p {{
            color: #666;
            margin: 10px 0 0 0;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section-title {{
            font-size: 18px;
            font-weight: bold;
            color: #6366f1;
            border-left: 4px solid #6366f1;
            padding-left: 10px;
            margin-bottom: 15px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #6366f1;
        }}
        .stat-label {{
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }}
        .badge-green {{ background: #d4edda; color: #155724; }}
        .badge-yellow {{ background: #fff3cd; color: #856404; }}
        .badge-red {{ background: #f8d7da; color: #721c24; }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #666;
            font-size: 12px;
        }}
        @media print {{
            .no-print {{ display: none; }}
            body {{ max-width: none; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🐱 {report_title}</h1>
        <p>报告周期：{report_period}</p>
        <p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="section">
        <div class="section-title">📊 统计概览</div>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats.get('total_devices', 0)}</div>
                <div class="stat-label">总设备数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('online_devices', 0)}</div>
                <div class="stat-label">在线设备</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('total_alerts', 0)}</div>
                <div class="stat-label">告警总数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('resolved_alerts', 0)}</div>
                <div class="stat-label">已解决告警</div>
            </div>
        </div>
    </div>
    
    <div class="section">
        <div class="section-title">📋 审计摘要</div>
        <table>
            <tr>
                <th>指标</th>
                <th>数值</th>
            </tr>
            <tr>
                <td>总操作数</td>
                <td>{audit_summary.get('total_operations', 0)}</td>
            </tr>
            <tr>
                <td>文件操作</td>
                <td>{audit_summary.get('file_operations', 0)}</td>
            </tr>
            <tr>
                <td>命令执行</td>
                <td>{audit_summary.get('command_operations', 0)}</td>
            </tr>
            <tr>
                <td>API 调用</td>
                <td>{audit_summary.get('api_operations', 0)}</td>
            </tr>
            <tr>
                <td>阻断操作</td>
                <td>{audit_summary.get('blocked_operations', 0)}</td>
            </tr>
        </table>
    </div>
    
    <div class="section">
        <div class="section-title">🚨 重要告警</div>
        <table>
            <thead>
                <tr>
                    <th>告警标题</th>
                    <th>级别</th>
                    <th>时间</th>
                    <th>状态</th>
                </tr>
            </thead>
            <tbody>
"""
    
    # 添加告警数据（最多 10 条）
    for alert in alerts[:10]:
        level_class = {
            'critical': 'badge-red',
            'high': 'badge-red',
            'medium': 'badge-yellow',
            'low': 'badge-green'
        }.get(alert.get('level', ''), 'badge-green')
        
        status = '✅ 已解决' if alert.get('is_resolved') else '⏳ 未解决'
        
        html += f"""
                <tr>
                    <td>{alert.get('title', '')}</td>
                    <td><span class="badge {level_class}">{alert.get('level', '').upper()}</span></td>
                    <td>{alert.get('created_at', '')}</td>
                    <td>{status}</td>
                </tr>
"""
    
    html += """
            </tbody>
        </table>
    </div>
    
    <div class="section">
        <div class="section-title">💻 设备列表</div>
        <table>
            <thead>
                <tr>
                    <th>设备名称</th>
                    <th>用户</th>
                    <th>状态</th>
                    <th>风险等级</th>
                </tr>
            </thead>
            <tbody>
"""
    
    # 添加设备数据（最多 20 条）
    for device in devices[:20]:
        status_class = {
            'online': 'badge-green',
            'offline': 'badge-yellow',
            'warning': 'badge-yellow',
            'violation': 'badge-red'
        }.get(device.get('status', ''), 'badge-green')
        
        html += f"""
                <tr>
                    <td>{device.get('name', '')}</td>
                    <td>{device.get('user', '')}</td>
                    <td><span class="badge {status_class}">{device.get('status', '').upper()}</span></td>
                    <td>{device.get('risk_level', '').upper()}</td>
                </tr>
"""
    
    html += f"""
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        <p>OpenClaw Enterprise - 企业级 AI 智能体管控平台</p>
        <p>报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p style="margin-top: 10px;">
            <button class="no-print" onclick="window.print()" style="padding: 10px 20px; background: #6366f1; color: white; border: none; border-radius: 6px; cursor: pointer;">🖨️ 打印报告</button>
            <button class="no-print" onclick="window.close()" style="padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer; margin-left: 10px;">关闭窗口</button>
        </p>
    </div>
</body>
</html>
"""
    
    return html


# ==================== FastAPI 路由 ====================

router = APIRouter()

@router.get("/api/export/devices")
async def export_devices(format: str = "csv", current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    """导出设备列表（按租户过滤）"""
    tenant_id = get_tenant_filter(current_user)
    query = db.query(Device)
    if tenant_id is not None:
        query = query.filter(Device.tenant_id == tenant_id)
    rows = query.all()
    devices = [{"id": d.id, "name": d.name, "hostname": d.hostname, "ip": d.ip_address or "", "user": "", "tenant": "", "version": d.version or "", "status": d.status or "", "risk_level": d.risk_level or "", "risk_score": d.risk_score or 0, "last_active": str(d.last_active or ""), "created_at": str(d.created_at or "")} for d in rows]
    
    if format == "csv":
        csv_content = export_devices_to_csv(devices)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=devices.csv"}
        )
    elif format == "pdf":
        headers = ['ID', 'Name', 'Hostname', 'IP', 'Status', 'Risk', 'Score']
        rows = [[d.get('id',''), d.get('name',''), d.get('hostname',''), d.get('ip',''), d.get('status',''), d.get('risk_level',''), d.get('risk_score',0)] for d in devices]
        pdf_bytes = generate_pdf_report("OpenClaw - Device List", [{"heading": "Devices", "table": {"headers": headers, "rows": rows}}])
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=devices.pdf"})
    else:
        raise HTTPException(status_code=400, detail="不支持的格式")


@router.get("/api/export/audit-logs")
async def export_audit_logs(
    format: str = "csv",
    start_date: str = None,
    end_date: str = None,
    current_user: User = require_role("manager"),
    db: Session = Depends(get_db)
):
    """导出审计日志（按租户过滤）"""
    from models import AuditLog
    device_ids = get_tenant_device_ids(db, current_user)
    
    query = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(1000)
    if device_ids is not None:
        query = query.filter(AuditLog.device_id.in_(device_ids))
    
    rows = query.all()
    logs = [{"id": r.id, "timestamp": str(r.timestamp or ""), "device": f"Device-{r.device_id}" if r.device_id else "-", "user": "-", "operation_type": r.operation_type or "", "operation_detail": r.operation_detail or "", "risk_level": r.risk_level or "", "status": r.status or ""} for r in rows]
    
    if format == "csv":
        csv_content = export_audit_logs_to_csv(logs)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit-logs.csv"}
        )
    elif format == "pdf":
        headers = ['ID', 'Time', 'Device', 'Type', 'Detail', 'Risk', 'Status']
        rows = [[l.get('id',''), l.get('timestamp',''), l.get('device',''), l.get('operation_type',''), str(l.get('operation_detail',''))[:30], l.get('risk_level',''), l.get('status','')] for l in logs]
        pdf_bytes = generate_pdf_report("OpenClaw - Audit Logs", [{"heading": "Audit Logs", "table": {"headers": headers, "rows": rows}}])
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=audit-logs.pdf"})
    else:
        raise HTTPException(status_code=400, detail="不支持的格式")


@router.get("/api/export/alerts")
async def export_alerts(format: str = "csv", current_user: User = require_role("manager"), db: Session = Depends(get_db)):
    """导出告警列表（按租户过滤）"""
    from models import Alert
    device_ids = get_tenant_device_ids(db, current_user)
    
    query = db.query(Alert).order_by(Alert.created_at.desc()).limit(1000)
    if device_ids is not None:
        query = query.filter(Alert.device_id.in_(device_ids))
    
    rows = query.all()
    alerts = [{"id": r.id, "title": r.title or "", "level": r.level or "", "description": r.description or "", "device_ip": "-", "is_resolved": r.is_resolved, "created_at": str(r.created_at or ""), "resolved_at": str(r.resolved_at or "")} for r in rows]
    
    if format == "csv":
        csv_content = export_alerts_to_csv(alerts)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=alerts.csv"}
        )
    elif format == "pdf":
        headers = ['ID', 'Title', 'Level', 'Status', 'Created']
        rows = [[a.get('id',''), a.get('title',''), a.get('level',''), 'Resolved' if a.get('is_resolved') else 'Open', a.get('created_at','')] for a in alerts]
        pdf_bytes = generate_pdf_report("OpenClaw - Alerts", [{"heading": "Alerts", "table": {"headers": headers, "rows": rows}}])
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=alerts.pdf"})
    else:
        raise HTTPException(status_code=400, detail="不支持的格式")


@router.get("/api/report/compliance")
async def generate_compliance_report(
    period: str = "weekly",
    format: str = "html"
):
    """生成合规报告"""
    from database import SessionLocal
    from models import Device, Alert, AuditLog
    
    now = datetime.now()
    if period == "daily":
        start = now - timedelta(days=1)
        title = "OpenClaw 安全合规日报"
    elif period == "weekly":
        start = now - timedelta(weeks=1)
        title = "OpenClaw 安全合规周报"
    elif period == "monthly":
        start = now - timedelta(days=30)
        title = "OpenClaw 安全合规月报"
    else:
        start = now - timedelta(weeks=1)
        title = "OpenClaw 安全合规报告"
    
    period_str = f"{start.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')}"
    
    db = SessionLocal()
    try:
        total_devices = db.query(Device).count()
        online_devices = db.query(Device).filter(Device.status == "online").count()
        total_alerts = db.query(Alert).filter(Alert.created_at >= start).count()
        resolved_alerts = db.query(Alert).filter(Alert.created_at >= start, Alert.is_resolved == True).count()
        
        total_ops = db.query(AuditLog).filter(AuditLog.timestamp >= start).count()
        blocked_ops = db.query(AuditLog).filter(AuditLog.timestamp >= start, AuditLog.status == "blocked").count()
        
        device_rows = db.query(Device).all()
        devices = [{"name": d.name, "user": "-", "status": d.status or "", "risk_level": d.risk_level or ""} for d in device_rows]
        
        alert_rows = db.query(Alert).filter(Alert.created_at >= start).order_by(Alert.created_at.desc()).limit(20).all()
        alerts = [{"title": a.title, "level": a.level, "is_resolved": a.is_resolved, "created_at": str(a.created_at or "")} for a in alert_rows]
    finally:
        db.close()
    
    stats = {
        "total_devices": total_devices,
        "online_devices": online_devices,
        "total_alerts": total_alerts,
        "resolved_alerts": resolved_alerts
    }
    
    audit_summary = {
        "total_operations": total_ops,
        "file_operations": 0,
        "command_operations": 0,
        "api_operations": total_ops,
        "blocked_operations": blocked_ops
    }
    
    html_content = generate_compliance_report_html(
        report_title=title,
        report_period=period_str,
        stats=stats,
        devices=devices,
        alerts=alerts,
        audit_summary=audit_summary
    )
    
    if format == "html":
        return Response(
            content=html_content,
            media_type="text/html",
            headers={"Content-Disposition": "attachment; filename=compliance-report.html"}
        )
    elif format == "pdf":
        sections = [
            {
                "heading": "Statistics Overview",
                "table": {
                    "headers": ["Metric", "Value"],
                    "rows": [
                        ["Total Devices", str(stats["total_devices"])],
                        ["Online Devices", str(stats["online_devices"])],
                        ["Total Alerts", str(stats["total_alerts"])],
                        ["Resolved Alerts", str(stats["resolved_alerts"])],
                    ]
                }
            },
            {
                "heading": "Audit Summary",
                "table": {
                    "headers": ["Metric", "Value"],
                    "rows": [
                        ["Total Operations", str(audit_summary["total_operations"])],
                        ["API Operations", str(audit_summary["api_operations"])],
                        ["Blocked Operations", str(audit_summary["blocked_operations"])],
                    ]
                }
            },
            {
                "heading": "Alerts",
                "table": {
                    "headers": ["Title", "Level", "Status", "Created"],
                    "rows": [
                        [a.get("title",""), a.get("level",""), "Resolved" if a.get("is_resolved") else "Open", a.get("created_at","")]
                        for a in alerts
                    ]
                }
            },
            {
                "heading": "Devices",
                "table": {
                    "headers": ["Name", "Status", "Risk Level"],
                    "rows": [[d.get("name",""), d.get("status",""), d.get("risk_level","")] for d in devices]
                }
            }
        ]
        pdf_bytes = generate_pdf_report(title, sections)
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=compliance-report.pdf"})
    else:
        return Response(
            content=html_content,
            media_type="text/html"
        )


@router.get("/api/report/dashboard")
async def get_dashboard_data():
    """获取仪表盘数据（从数据库读取真实数据）"""
    from database import SessionLocal
    from models import Device, Alert, AuditLog
    from agent_manager import Agent
    from sqlalchemy import func

    db = SessionLocal()
    try:
        # 统计
        total_devices = db.query(func.count(Device.id)).scalar() or 0
        online_devices = db.query(func.count(Device.id)).filter(Device.status == "online").scalar() or 0
        offline_devices = db.query(func.count(Device.id)).filter(Device.status != "online").scalar() or 0
        total_alerts = db.query(func.count(Alert.id)).scalar() or 0
        critical_alerts = db.query(func.count(Alert.id)).filter(Alert.level.in_(["critical", "high"])).scalar() or 0
        resolved_alerts = db.query(func.count(Alert.id)).filter(Alert.is_resolved == True).scalar() or 0

        # Agent 统计
        total_agents = db.query(func.count(Agent.id)).scalar() or 0
        active_agents = db.query(func.count(Agent.id)).filter(Agent.status == "running").scalar() or 0

        # 审计摘要
        total_operations = db.query(func.count(AuditLog.id)).scalar() or 0
        file_operations = db.query(func.count(AuditLog.id)).filter(
            AuditLog.operation_type.in_(["file_read", "file_write", "file_delete"])
        ).scalar() or 0
        command_operations = db.query(func.count(AuditLog.id)).filter(
            AuditLog.operation_type.in_(["command_exec", "exec"])
        ).scalar() or 0
        api_operations = db.query(func.count(AuditLog.id)).filter(
            AuditLog.operation_type.like("api_%")
        ).scalar() or 0
        blocked_operations = db.query(func.count(AuditLog.id)).filter(
            AuditLog.status == "blocked"
        ).scalar() or 0

        # 风险分布
        low_risk = db.query(func.count(Device.id)).filter(Device.risk_score < 40).scalar() or 0
        medium_risk = db.query(func.count(Device.id)).filter(Device.risk_score >= 40, Device.risk_score < 60).scalar() or 0
        high_risk = db.query(func.count(Device.id)).filter(Device.risk_score >= 60).scalar() or 0

        # 最近 7 天告警趋势
        now = datetime.now()
        alert_trend = []
        for i in range(6, -1, -1):
            day = now - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            count = db.query(func.count(Alert.id)).filter(
                Alert.created_at >= day_start,
                Alert.created_at < day_end
            ).scalar() or 0
            alert_trend.append({"date": day_start.strftime("%Y-%m-%d"), "count": count})

        return {
            "stats": {
                "total_devices": total_devices,
                "online_devices": online_devices,
                "offline_devices": offline_devices,
                "total_alerts": total_alerts,
                "critical_alerts": critical_alerts,
                "resolved_alerts": resolved_alerts,
                "total_agents": total_agents,
                "active_agents": active_agents
            },
            "audit_summary": {
                "total_operations": total_operations,
                "file_operations": file_operations,
                "command_operations": command_operations,
                "api_operations": api_operations,
                "blocked_operations": blocked_operations
            },
            "risk_distribution": {
                "low": low_risk,
                "medium": medium_risk,
                "high": high_risk
            },
            "alert_trend": alert_trend
        }
    finally:
        db.close()
