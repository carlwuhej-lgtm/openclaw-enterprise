"""
OpenClaw Enterprise - 完整安全治理报告生成器
生成专业的 AI Agent 安全治理 PDF 报告
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from fpdf import FPDF
from sqlalchemy import func

from database import SessionLocal
from models import Device, AuditLog, Alert, SecurityPolicy, Tenant
from agent_manager import Agent


# ==================== 颜色方案（Nightwatch 主题）====================
class C:
    """颜色常量 (r, g, b)"""
    BRAND = (0, 212, 255)        # #00d4ff 品牌青色
    ACCENT = (0, 255, 136)       # #00ff88 强调绿
    DARK = (10, 22, 40)          # #0a1628 深色背景
    DARK_LIGHT = (18, 35, 60)    # 稍浅深色
    DANGER = (239, 68, 68)       # #ef4444
    WARNING = (245, 158, 11)     # #f59e0b
    SAFE = (16, 185, 129)        # #10b981
    WHITE = (255, 255, 255)
    TEXT = (50, 55, 65)          # 正文色
    TEXT_LIGHT = (120, 125, 135) # 辅助文字
    ROW_ALT = (245, 247, 250)   # 交替行背景
    ROW_WHITE = (255, 255, 255)
    LINE = (220, 225, 230)       # 分隔线
    COVER_BG = (8, 18, 35)      # 封面背景


# ==================== PDF 报告类 ====================
class FullReportPDF(FPDF):
    """完整安全治理报告 PDF"""

    def __init__(self, period_str: str, period_label: str):
        super().__init__()
        self.period_str = period_str
        self.period_label = period_label
        self._font_name = "Helvetica"
        self._zh_ok = False
        self._toc_entries = []     # [(level, title, page_no)]
        self._chapter_counter = 0
        self._setup_fonts()

    # ---------- 字体 ----------
    def _setup_fonts(self):
        candidates = [
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]
        for p in candidates:
            if os.path.isfile(p):
                try:
                    self.add_font("zh", "", p)
                    self.add_font("zh", "B", p)
                    self._font_name = "zh"
                    self._zh_ok = True
                    return
                except Exception:
                    continue
        # fallback: Helvetica
        self._font_name = "Helvetica"
        self._zh_ok = False

    def _round_rect(self, x, y, w, h, r, style=""):
        """绘制圆角矩形（兼容方案）"""
        try:
            from fpdf.enums import RenderStyle
            rs = {"": RenderStyle.D, "D": RenderStyle.D, "F": RenderStyle.F, "DF": RenderStyle.DF, "FD": RenderStyle.DF}
            self._draw_rounded_rect(x, y, w, h, rs.get(style, RenderStyle.D), True, r)
        except Exception:
            # 极端 fallback：普通矩形
            self.rect(x, y, w, h, style)

    def _safe(self, text: str) -> str:
        """确保文本可安全渲染"""
        if self._zh_ok:
            return str(text)
        # Helvetica fallback: latin-1 安全
        return str(text).encode("latin-1", "replace").decode("latin-1")

    # ---------- 页脚 ----------
    def footer(self):
        if self.page_no() <= 1:
            return  # 封面不显示页脚
        self.set_y(-15)
        self.set_font(self._font_name, "", 7)
        self.set_text_color(*C.TEXT_LIGHT)
        self.set_draw_color(*C.LINE)
        self.line(20, self.get_y() - 2, 190, self.get_y() - 2)
        footer_text = self._safe(f"OpenClaw Enterprise  |  {self.period_str}  |  {self.period_label}")
        self.cell(0, 8, footer_text, align="L")
        self.cell(0, 8, self._safe(f"{self.page_no()}"), align="R")

    # ---------- 封面 ----------
    def add_cover(self, org_name: str):
        self.add_page()
        # 深色背景
        self.set_fill_color(*C.COVER_BG)
        self.rect(0, 0, 210, 297, "F")

        # 顶部装饰线
        self.set_fill_color(*C.BRAND)
        self.rect(0, 0, 210, 4, "F")

        # 品牌标识区域
        self.set_y(60)
        self.set_font(self._font_name, "", 11)
        self.set_text_color(*C.BRAND)
        self.cell(0, 8, self._safe("OPENCLAW ENTERPRISE"), align="C", new_x="LMARGIN", new_y="NEXT")

        # 主标题
        self.ln(12)
        self.set_font(self._font_name, "B", 32)
        self.set_text_color(*C.WHITE)
        self.cell(0, 16, self._safe("AI Agent"), align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 16, self._safe("安全治理报告"), align="C", new_x="LMARGIN", new_y="NEXT")

        # 品牌色分隔线
        self.ln(8)
        x_center = 105
        self.set_draw_color(*C.BRAND)
        self.set_line_width(0.8)
        self.line(x_center - 30, self.get_y(), x_center + 30, self.get_y())
        self.set_line_width(0.2)  # reset
        self.ln(10)

        # 副标题（周期类型）
        self.set_font(self._font_name, "", 16)
        self.set_text_color(180, 200, 220)
        self.cell(0, 10, self._safe(self.period_label), align="C", new_x="LMARGIN", new_y="NEXT")

        # 报告周期
        self.ln(30)
        self.set_font(self._font_name, "", 11)
        self.set_text_color(140, 160, 180)
        self.cell(0, 8, self._safe(f"报告周期：{self.period_str}"), align="C", new_x="LMARGIN", new_y="NEXT")

        # 生成时间
        self.cell(0, 8, self._safe(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), align="C", new_x="LMARGIN", new_y="NEXT")

        # 机构名称
        self.ln(4)
        self.set_font(self._font_name, "", 11)
        self.set_text_color(*C.BRAND)
        self.cell(0, 8, self._safe(org_name), align="C", new_x="LMARGIN", new_y="NEXT")

        # 底部装饰
        self.set_fill_color(*C.BRAND)
        self.rect(0, 293, 210, 4, "F")

    # ---------- 目录 ----------
    def add_toc_placeholder(self):
        """添加目录页（后期回填页码）"""
        self.add_page()
        self._toc_page = self.page_no()
        self.set_font(self._font_name, "B", 20)
        self.set_text_color(*C.DARK)
        self.cell(0, 14, self._safe("目    录"), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(6)

        # 品牌色装饰线
        self.set_draw_color(*C.BRAND)
        self.set_line_width(0.6)
        self.line(80, self.get_y(), 130, self.get_y())
        self.set_line_width(0.2)
        self.ln(10)

    def _render_toc_entries(self):
        """渲染目录内容（在所有章节添加完后调用）"""
        # 回到目录页
        current_page = self.page_no()
        self.page = self._toc_page
        # 目录内容起始 y 位置
        y = 50
        for level, title, page_no in self._toc_entries:
            self.set_y(y)
            if level == 1:
                self.set_font(self._font_name, "B", 12)
                self.set_text_color(*C.DARK)
                indent = 20
            else:
                self.set_font(self._font_name, "", 10)
                self.set_text_color(*C.TEXT)
                indent = 30

            self.set_x(indent)
            title_text = self._safe(title)
            page_text = self._safe(str(page_no))

            # 标题
            self.cell(120, 8, title_text)
            # 点线填充
            self.set_text_color(*C.TEXT_LIGHT)
            dots = " " + "." * 40
            # 页码
            self.set_x(170)
            self.cell(20, 8, page_text, align="R")
            y += 10 if level == 1 else 8

        self.page = current_page

    # ---------- 章节标题 ----------
    def chapter_title(self, title: str, level: int = 1):
        """添加章节标题"""
        if level == 1:
            self._chapter_counter += 1
            self.add_page()
            # 顶部品牌色条
            self.set_fill_color(*C.BRAND)
            self.rect(20, 18, 4, 18, "F")
            self.set_xy(28, 18)
            self.set_font(self._font_name, "B", 22)
            self.set_text_color(*C.DARK)
            self.cell(0, 18, self._safe(title))
            self.ln(22)
            # 分隔线
            self.set_draw_color(*C.LINE)
            self.line(20, self.get_y(), 190, self.get_y())
            self.ln(8)
        else:
            self.ln(6)
            self.set_font(self._font_name, "B", 13)
            self.set_text_color(C.DARK_LIGHT[0] + 20, C.DARK_LIGHT[1] + 30, C.DARK_LIGHT[2] + 40)
            self.cell(0, 10, self._safe(title), new_x="LMARGIN", new_y="NEXT")
            self.ln(2)

        self._toc_entries.append((level, title, self.page_no()))

    # ---------- 正文 ----------
    def body_text(self, text: str):
        self.set_font(self._font_name, "", 10)
        self.set_text_color(*C.TEXT)
        self.multi_cell(0, 6, self._safe(text))
        self.ln(3)

    # ---------- 指标卡片 ----------
    def kpi_cards(self, cards: list):
        """
        cards: [(label, value, color_tuple), ...]
        绘制 4 个指标卡片（2x2 网格）
        """
        card_w = 80
        card_h = 32
        gap = 5
        start_x = 22
        start_y = self.get_y()

        for i, (label, value, color) in enumerate(cards):
            col = i % 2
            row = i // 2
            x = start_x + col * (card_w + gap)
            y = start_y + row * (card_h + gap)

            # 卡片背景 - 淡色底
            r, g, b = color
            self.set_fill_color(min(r + 200, 250), min(g + 200, 250), min(b + 200, 250))
            self._round_rect(x, y, card_w, card_h, 4, style="F")

            # 左侧色条
            self.set_fill_color(*color)
            self.rect(x, y + 4, 3, card_h - 8, "F")

            # 数值
            self.set_xy(x + 8, y + 4)
            self.set_font(self._font_name, "B", 22)
            self.set_text_color(*color)
            self.cell(card_w - 12, 14, self._safe(str(value)))

            # 标签
            self.set_xy(x + 8, y + 18)
            self.set_font(self._font_name, "", 9)
            self.set_text_color(*C.TEXT_LIGHT)
            self.cell(card_w - 12, 8, self._safe(label))

        self.set_y(start_y + 2 * (card_h + gap) + 4)

    # ---------- 安全评分 ----------
    def security_score(self, score: int, rating: str):
        """绘制安全评分仪表"""
        y = self.get_y()
        center_x = 105
        # 评分数字
        if score >= 80:
            color = C.SAFE
        elif score >= 60:
            color = C.WARNING
        else:
            color = C.DANGER

        # 背景框
        box_w, box_h = 120, 40
        bx = center_x - box_w / 2
        self.set_fill_color(248, 250, 252)
        self._round_rect(bx, y, box_w, box_h, 5, style="F")

        # 分数
        self.set_xy(bx + 10, y + 4)
        self.set_font(self._font_name, "B", 30)
        self.set_text_color(*color)
        self.cell(40, 20, self._safe(str(score)))

        # 评级文字
        self.set_xy(bx + 55, y + 6)
        self.set_font(self._font_name, "B", 14)
        self.cell(55, 10, self._safe(rating))

        # 进度条背景
        bar_x, bar_y = bx + 55, y + 22
        bar_w, bar_h = 55, 6
        self.set_fill_color(*C.LINE)
        self._round_rect(bar_x, bar_y, bar_w, bar_h, 3, style="F")
        # 进度条填充
        fill_w = bar_w * score / 100
        self.set_fill_color(*color)
        self._round_rect(bar_x, bar_y, max(fill_w, 6), bar_h, 3, style="F")

        # 辅助文字
        self.set_xy(bx + 10, y + 26)
        self.set_font(self._font_name, "", 8)
        self.set_text_color(*C.TEXT_LIGHT)
        self.cell(40, 8, self._safe("/100 分"))

        self.set_y(y + box_h + 6)

    # ---------- 表格 ----------
    def data_table(self, headers: list, rows: list, col_widths: list = None):
        """绘制专业数据表格"""
        if not col_widths:
            total_w = 170
            col_widths = [total_w / len(headers)] * len(headers)

        x_start = 20
        # 表头
        self.set_fill_color(*C.DARK)
        self.set_text_color(*C.WHITE)
        self.set_font(self._font_name, "B", 9)
        y = self.get_y()
        for i, h in enumerate(headers):
            x = x_start + sum(col_widths[:i])
            self.set_xy(x, y)
            # 左右圆角处理 (首尾)
            self.cell(col_widths[i], 9, self._safe(str(h)), fill=True, align="C")
        self.ln(9)

        # 数据行
        self.set_font(self._font_name, "", 8.5)
        for row_idx, row in enumerate(rows):
            # 检查是否需要换页
            if self.get_y() > 265:
                self.add_page()
                # 重绘表头
                self.set_fill_color(*C.DARK)
                self.set_text_color(*C.WHITE)
                self.set_font(self._font_name, "B", 9)
                y = self.get_y()
                for i, h in enumerate(headers):
                    x = x_start + sum(col_widths[:i])
                    self.set_xy(x, y)
                    self.cell(col_widths[i], 9, self._safe(str(h)), fill=True, align="C")
                self.ln(9)
                self.set_font(self._font_name, "", 8.5)

            bg = C.ROW_ALT if row_idx % 2 == 0 else C.ROW_WHITE
            self.set_fill_color(*bg)
            self.set_text_color(*C.TEXT)
            y = self.get_y()
            for i, val in enumerate(row):
                x = x_start + sum(col_widths[:i])
                self.set_xy(x, y)
                text = str(val) if val is not None else "-"
                if len(text) > 35:
                    text = text[:33] + ".."
                self.cell(col_widths[i], 8, self._safe(text), fill=True)
            self.ln(8)

        self.ln(4)

    # ---------- 信息框 ----------
    def info_box(self, text: str, box_type: str = "info"):
        """信息提示框"""
        colors = {
            "info": C.BRAND,
            "success": C.SAFE,
            "warning": C.WARNING,
            "danger": C.DANGER,
        }
        color = colors.get(box_type, C.BRAND)
        y = self.get_y()
        # 背景
        r, g, b = color
        self.set_fill_color(min(r + 210, 252), min(g + 210, 252), min(b + 210, 252))
        # 先计算高度
        self.set_font(self._font_name, "", 9.5)
        line_count = max(1, len(text) // 70 + 1)
        box_h = max(14, line_count * 6 + 8)
        self._round_rect(20, y, 170, box_h, 3, style="F")
        # 左侧色条
        self.set_fill_color(*color)
        self.rect(20, y, 3, box_h, "F")
        # 文字
        self.set_xy(27, y + 3)
        self.set_text_color(*C.TEXT)
        self.multi_cell(158, 6, self._safe(text))
        self.set_y(y + box_h + 4)

    # ---------- 统计条目 ----------
    def stat_bar(self, label: str, value: int, total: int, color: tuple):
        """水平统计条"""
        y = self.get_y()
        bar_w = 100
        bar_h = 6
        ratio = value / max(total, 1)
        fill_w = max(bar_w * ratio, 2)

        # 标签
        self.set_xy(20, y)
        self.set_font(self._font_name, "", 9)
        self.set_text_color(*C.TEXT)
        self.cell(40, 8, self._safe(label))

        # 背景条
        bx = 62
        self.set_fill_color(*C.LINE)
        self._round_rect(bx, y + 1, bar_w, bar_h, 3, style="F")
        # 填充条
        self.set_fill_color(*color)
        self._round_rect(bx, y + 1, fill_w, bar_h, 3, style="F")

        # 数值
        self.set_xy(bx + bar_w + 4, y)
        self.set_font(self._font_name, "B", 9)
        self.set_text_color(*color)
        self.cell(20, 8, self._safe(f"{value}"))
        self.set_font(self._font_name, "", 8)
        self.set_text_color(*C.TEXT_LIGHT)
        pct = f"  ({ratio * 100:.0f}%)" if total > 0 else ""
        self.cell(20, 8, self._safe(pct))

        self.set_y(y + 12)


# ==================== 数据收集 ====================
def _collect_report_data(period: str):
    """从数据库收集报告所需的所有数据"""
    now = datetime.now()
    if period == "daily":
        start = now - timedelta(days=1)
        period_label = "日报"
    elif period == "monthly":
        start = now - timedelta(days=30)
        period_label = "月报"
    else:
        start = now - timedelta(weeks=1)
        period_label = "周报"

    period_str = f"{start.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')}"

    db = SessionLocal()
    try:
        # 租户
        tenant = db.query(Tenant).first()
        org_name = tenant.name if tenant else "OpenClaw Enterprise"

        # ---- 资产 ----
        devices = db.query(Device).all()
        agents = db.query(Agent).all()
        total_devices = len(devices)
        total_agents = len(agents)

        # ---- 审计日志 ----
        audit_query = db.query(AuditLog).filter(AuditLog.timestamp >= start)
        total_audits = audit_query.count()

        # 类型分布
        type_dist = dict(
            db.query(AuditLog.operation_type, func.count(AuditLog.id))
            .filter(AuditLog.timestamp >= start)
            .group_by(AuditLog.operation_type)
            .all()
        )

        # 风险分布
        risk_dist = dict(
            db.query(AuditLog.risk_level, func.count(AuditLog.id))
            .filter(AuditLog.timestamp >= start)
            .group_by(AuditLog.risk_level)
            .all()
        )

        # 状态分布
        status_dist = dict(
            db.query(AuditLog.status, func.count(AuditLog.id))
            .filter(AuditLog.timestamp >= start)
            .group_by(AuditLog.status)
            .all()
        )

        # 最近 20 条
        recent_logs = (
            audit_query.order_by(AuditLog.timestamp.desc()).limit(20).all()
        )

        # ---- 告警 ----
        alert_query = db.query(Alert).filter(Alert.created_at >= start)
        total_alerts = alert_query.count()
        alert_levels = dict(
            db.query(Alert.level, func.count(Alert.id))
            .filter(Alert.created_at >= start)
            .group_by(Alert.level)
            .all()
        )
        resolved_alerts = alert_query.filter(Alert.is_resolved == True).count()
        unresolved_alerts = total_alerts - resolved_alerts
        alert_list = alert_query.order_by(Alert.created_at.desc()).limit(20).all()

        # ---- 策略 ----
        policies = db.query(SecurityPolicy).all()
        enabled_policies = sum(1 for p in policies if p.is_enabled)

        # ---- 安全评分计算 ----
        score = 100
        # 扣分项：
        # 1. 高危操作未拦截
        blocked = status_dist.get("blocked", 0)
        allowed = status_dist.get("allowed", 0)
        if total_audits > 0:
            block_ratio = blocked / total_audits
        else:
            block_ratio = 0

        # 2. 危险操作
        danger_ops = risk_dist.get("danger", 0)
        warning_ops = risk_dist.get("warning", 0)
        score -= danger_ops * 5
        score -= warning_ops * 2

        # 3. 未解决告警
        score -= unresolved_alerts * 10

        # 4. 策略覆盖
        if len(policies) > 0:
            policy_ratio = enabled_policies / len(policies)
            if policy_ratio < 0.8:
                score -= 10

        # 5. 设备风险
        for d in devices:
            if d.risk_level == "high":
                score -= 5
            elif d.risk_level == "medium":
                score -= 2

        score = max(0, min(100, score))

        if score >= 90:
            rating = "优秀"
        elif score >= 80:
            rating = "良好"
        elif score >= 60:
            rating = "一般"
        elif score >= 40:
            rating = "较差"
        else:
            rating = "危险"

        return {
            "period": period,
            "period_str": period_str,
            "period_label": period_label,
            "org_name": org_name,
            "now": now,
            "start": start,
            # 资产
            "devices": devices,
            "agents": agents,
            "total_devices": total_devices,
            "total_agents": total_agents,
            # 审计
            "total_audits": total_audits,
            "type_dist": type_dist,
            "risk_dist": risk_dist,
            "status_dist": status_dist,
            "recent_logs": recent_logs,
            "blocked": blocked,
            "allowed": allowed,
            # 告警
            "total_alerts": total_alerts,
            "alert_levels": alert_levels,
            "resolved_alerts": resolved_alerts,
            "unresolved_alerts": unresolved_alerts,
            "alert_list": alert_list,
            # 策略
            "policies": policies,
            "enabled_policies": enabled_policies,
            # 评分
            "score": score,
            "rating": rating,
        }
    finally:
        db.close()


# ==================== 报告生成 ====================
def generate_full_report(period: str = "weekly") -> bytes:
    """生成完整安全治理报告 PDF"""
    data = _collect_report_data(period)
    pdf = FullReportPDF(data["period_str"], data["period_label"])
    pdf.set_auto_page_break(auto=True, margin=20)

    # ===== 封面 =====
    pdf.add_cover(data["org_name"])

    # ===== 目录 =====
    pdf.add_toc_placeholder()

    # ===== 第一章：执行摘要 =====
    pdf.chapter_title("第一章  执行摘要")

    # 态势总结
    safe_ops = data["risk_dist"].get("safe", 0)
    danger_ops = data["risk_dist"].get("danger", 0)
    summary = (
        f"本报告覆盖 {data['period_str']} 期间的安全治理数据。"
        f"平台当前管理 {data['total_devices']} 台主机、{data['total_agents']} 个 AI Agent，"
        f"期间共记录 {data['total_audits']} 次审计操作，产生 {data['total_alerts']} 条告警。"
    )
    if data["score"] >= 80:
        summary += f" 整体安全态势良好，安全评分 {data['score']} 分（{data['rating']}）。"
    elif data["score"] >= 60:
        summary += f" 安全态势尚可，安全评分 {data['score']} 分（{data['rating']}），建议关注以下风险项。"
    else:
        summary += f" 安全态势需要关注，安全评分 {data['score']} 分（{data['rating']}），请尽快处理未解决的风险。"
    pdf.body_text(summary)

    # KPI 卡片
    pdf.kpi_cards([
        ("管理主机数", data["total_devices"], C.BRAND),
        ("AI Agent 数", data["total_agents"], (139, 92, 246)),  # 紫色
        ("审计操作数", data["total_audits"], C.SAFE),
        ("告警事件数", data["total_alerts"], C.DANGER if data["total_alerts"] > 0 else C.SAFE),
    ])

    # 安全评分
    pdf.ln(2)
    pdf.set_font(pdf._font_name, "B", 12)
    pdf.set_text_color(*C.DARK)
    pdf.cell(0, 10, pdf._safe("安全评分"), new_x="LMARGIN", new_y="NEXT")
    pdf.security_score(data["score"], data["rating"])

    # 亮点 / 风险
    pdf.ln(2)
    if data["total_alerts"] == 0:
        pdf.info_box("本期亮点：报告周期内无告警事件，系统运行平稳。", "success")
    if data["blocked"] > 0:
        pdf.info_box(
            f"安全防护：拦截了 {data['blocked']} 次操作（占总操作 {data['blocked'] * 100 / max(data['total_audits'], 1):.0f}%），安全策略正常生效。",
            "info"
        )
    if danger_ops > 0:
        pdf.info_box(f"风险提示：检测到 {danger_ops} 次危险级别操作，请重点关注。", "danger")
    if data["unresolved_alerts"] > 0:
        pdf.info_box(f"待处理：{data['unresolved_alerts']} 条告警尚未解决。", "warning")

    # ===== 第二章：资产概览 =====
    pdf.chapter_title("第二章  资产概览")

    pdf.chapter_title("2.1 主机清单", level=2)
    if data["devices"]:
        headers = ["ID", "名称", "主机名", "IP 地址", "系统", "状态", "风险", "版本"]
        widths = [10, 30, 30, 22, 25, 16, 14, 23]
        rows = []
        for d in data["devices"]:
            rows.append([
                d.id,
                d.name or "-",
                (d.hostname or "-")[:18],
                d.ip_address or "-",
                (d.os_info or "-")[:16],
                d.status or "-",
                d.risk_level or "low",
                d.version or "-",
            ])
        pdf.data_table(headers, rows, widths)
    else:
        pdf.info_box("暂无主机数据", "info")

    pdf.chapter_title("2.2 Agent 清单", level=2)
    if data["agents"]:
        headers = ["ID", "Agent ID", "名称", "模型", "状态", "工作目录"]
        widths = [10, 22, 28, 35, 16, 59]
        rows = []
        for a in data["agents"]:
            rows.append([
                a.id,
                a.agent_id or "-",
                a.name or "-",
                a.model or "-",
                a.status or "-",
                (a.workspace or "-")[-35:] if a.workspace else "-",
            ])
        pdf.data_table(headers, rows, widths)
    else:
        pdf.info_box("暂无 Agent 数据", "info")

    pdf.chapter_title("2.3 资产风险分布", level=2)
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    for d in data["devices"]:
        level = d.risk_level or "low"
        if level in risk_counts:
            risk_counts[level] += 1
    total_d = max(data["total_devices"], 1)
    pdf.stat_bar("低风险 (Low)", risk_counts["low"], total_d, C.SAFE)
    pdf.stat_bar("中风险 (Medium)", risk_counts["medium"], total_d, C.WARNING)
    pdf.stat_bar("高风险 (High)", risk_counts["high"], total_d, C.DANGER)

    # ===== 第三章：安全审计 =====
    pdf.chapter_title("第三章  安全审计")

    pdf.chapter_title("3.1 审计操作统计", level=2)
    pdf.body_text(
        f"报告周期内共记录 {data['total_audits']} 次审计操作，"
        f"涵盖 {len(data['type_dist'])} 种操作类型。"
    )

    pdf.chapter_title("3.2 操作类型分布", level=2)
    total_ops = max(data["total_audits"], 1)
    type_colors = {
        "api_read": C.BRAND,
        "api_create": (139, 92, 246),
        "api_update": C.WARNING,
        "api_delete": C.DANGER,
        "file_read": C.SAFE,
        "file_write": (34, 197, 94),
        "file_delete": C.DANGER,
        "command_exec": C.WARNING,
    }
    for op_type, count in sorted(data["type_dist"].items(), key=lambda x: -x[1]):
        color = type_colors.get(op_type, C.TEXT_LIGHT)
        pdf.stat_bar(op_type, count, total_ops, color)

    pdf.chapter_title("3.3 风险级别分布", level=2)
    risk_colors = {"safe": C.SAFE, "warning": C.WARNING, "danger": C.DANGER}
    for level_name in ["safe", "warning", "danger"]:
        count = data["risk_dist"].get(level_name, 0)
        color = risk_colors.get(level_name, C.TEXT_LIGHT)
        pdf.stat_bar(level_name.capitalize(), count, total_ops, color)

    pdf.chapter_title("3.4 拦截统计", level=2)
    pdf.stat_bar("Allowed（放行）", data["allowed"], total_ops, C.SAFE)
    pdf.stat_bar("Blocked（拦截）", data["blocked"], total_ops, C.DANGER)

    pdf.chapter_title("3.5 最近审计日志", level=2)
    if data["recent_logs"]:
        headers = ["ID", "时间", "操作类型", "风险", "状态", "详情"]
        widths = [12, 32, 24, 16, 16, 70]
        rows = []
        for log in data["recent_logs"]:
            ts = log.timestamp.strftime("%m-%d %H:%M:%S") if log.timestamp else "-"
            detail = (log.operation_detail or "-")[:40]
            rows.append([
                log.id,
                ts,
                log.operation_type or "-",
                log.risk_level or "-",
                log.status or "-",
                detail,
            ])
        pdf.data_table(headers, rows, widths)
    else:
        pdf.info_box("报告周期内无审计日志记录", "info")

    # ===== 第四章：告警分析 =====
    pdf.chapter_title("第四章  告警分析")

    pdf.chapter_title("4.1 告警统计", level=2)
    if data["total_alerts"] > 0:
        pdf.body_text(
            f"报告周期内共产生 {data['total_alerts']} 条告警，"
            f"已解决 {data['resolved_alerts']} 条，未解决 {data['unresolved_alerts']} 条。"
        )
        total_a = max(data["total_alerts"], 1)
        for level_name in ["critical", "high", "medium", "low"]:
            count = data["alert_levels"].get(level_name, 0)
            if count > 0:
                color = C.DANGER if level_name in ("critical", "high") else (C.WARNING if level_name == "medium" else C.SAFE)
                pdf.stat_bar(level_name.capitalize(), count, total_a, color)

        pdf.chapter_title("4.2 告警列表", level=2)
        if data["alert_list"]:
            headers = ["ID", "标题", "级别", "状态", "创建时间"]
            widths = [12, 60, 20, 20, 58]
            rows = []
            for a in data["alert_list"]:
                ts = a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "-"
                status_text = "已解决" if a.is_resolved else "未解决"
                rows.append([a.id, a.title or "-", a.level or "-", status_text, ts])
            pdf.data_table(headers, rows, widths)
    else:
        pdf.info_box("本期无告警事件，系统运行正常。", "success")

    # ===== 第五章：安全策略 =====
    pdf.chapter_title("第五章  安全策略")

    pdf.chapter_title("5.1 策略列表和启用状态", level=2)
    if data["policies"]:
        pdf.body_text(
            f"当前共配置 {len(data['policies'])} 条安全策略，"
            f"已启用 {data['enabled_policies']} 条，"
            f"未启用 {len(data['policies']) - data['enabled_policies']} 条。"
        )
        headers = ["ID", "策略名称", "描述", "状态"]
        widths = [12, 40, 88, 30]
        rows = []
        for p in data["policies"]:
            status_text = "已启用" if p.is_enabled else "未启用"
            rows.append([
                p.id,
                p.name or "-",
                (p.description or "-")[:50],
                status_text,
            ])
        pdf.data_table(headers, rows, widths)
    else:
        pdf.info_box("暂无安全策略配置", "warning")

    pdf.chapter_title("5.2 策略执行情况", level=2)
    if data["blocked"] > 0:
        pdf.body_text(
            f"安全策略在报告周期内共拦截 {data['blocked']} 次操作，"
            f"拦截率 {data['blocked'] * 100 / max(data['total_audits'], 1):.1f}%。"
            f"策略覆盖率 {data['enabled_policies'] * 100 / max(len(data['policies']), 1):.0f}%。"
        )
    else:
        pdf.body_text("报告周期内暂无策略拦截记录。")

    # ===== 第六章：建议与改进 =====
    pdf.chapter_title("第六章  建议与改进")
    pdf.body_text("基于本期数据分析，提出以下安全建议：")

    suggestions = []
    # 拦截比例
    if data["total_audits"] > 0 and data["blocked"] / data["total_audits"] < 0.1:
        suggestions.append(
            "拦截率较低：当前拦截率仅 {:.1f}%，建议审查安全策略规则，确认是否需要加强管控。"
            .format(data["blocked"] * 100 / data["total_audits"])
        )
    # 未解决告警
    if data["unresolved_alerts"] > 0:
        suggestions.append(
            f"未解决告警：当前有 {data['unresolved_alerts']} 条告警未解决，建议尽快处理。"
        )
    # 策略覆盖
    disabled = len(data["policies"]) - data["enabled_policies"]
    if disabled > 0:
        suggestions.append(
            f"策略覆盖：有 {disabled} 条安全策略未启用，建议评估后启用以提升防护能力。"
        )
    # 高风险设备
    high_risk_devices = [d for d in data["devices"] if d.risk_level == "high"]
    if high_risk_devices:
        suggestions.append(
            f"高风险主机：检测到 {len(high_risk_devices)} 台高风险主机，建议及时排查。"
        )
    # 危险操作
    danger_count = data["risk_dist"].get("danger", 0)
    if danger_count > 0:
        suggestions.append(
            f"危险操作：本期检测到 {danger_count} 次危险级别操作，建议对相关 Agent 加强监控。"
        )
    # 告警规则
    if data["total_alerts"] == 0 and data["total_audits"] > 10:
        suggestions.append(
            "告警规则：报告期间无告警产生，建议检查告警规则配置是否合理，避免漏报。"
        )
    # Agent 异常
    stopped_agents = [a for a in data["agents"] if a.status in ("stopped", "error")]
    if stopped_agents:
        names = ", ".join(a.name or a.agent_id for a in stopped_agents[:3])
        suggestions.append(
            f"Agent 状态：{len(stopped_agents)} 个 Agent 处于非运行状态（{names}），建议检查。"
        )
    # 兜底
    if not suggestions:
        suggestions.append("当前安全态势良好，暂无需要改进的事项。建议保持定期审查。")

    for i, s in enumerate(suggestions, 1):
        box_type = "warning" if "建议" in s or "未" in s else "info"
        if "良好" in s or "正常" in s:
            box_type = "success"
        pdf.info_box(f"{i}. {s}", box_type)
        pdf.ln(1)

    # ===== 填充目录页码 =====
    pdf._render_toc_entries()

    return bytes(pdf.output())


# ==================== FastAPI 路由 ====================
router = APIRouter()


@router.get("/api/report/full")
async def get_full_report(
    format: str = "pdf",
    period: str = "weekly",
):
    """
    生成完整的 AI Agent 安全治理报告

    - **format**: pdf（默认）
    - **period**: daily / weekly / monthly
    """
    if format != "pdf":
        raise HTTPException(status_code=400, detail="目前仅支持 PDF 格式")

    if period not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="period 须为 daily / weekly / monthly")

    try:
        pdf_bytes = generate_full_report(period)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报告生成失败: {e}")

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"openclaw_security_report_{period}_{now_str}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
