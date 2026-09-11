"""贴边条 / 悬停胶囊:主窗口空闲收起后的边缘唤出入口。

独立顶层窗口(无父):主窗口 hide() 时不会被级联隐藏。
Tool + FramelessWindowHint + WindowStaysOnTopHint 保证不进任务栏、始终置顶;
WA_TranslucentBackground 让圆角与阴影外区域透明。

形态:贴边细条(accent 色,提示存在)⇄ Fluent 毛玻璃胶囊(半透明黑 + 白色细描边,
显示"待办 N 项")。两种形态只是同一块画布上的重绘 + 形变动画,窗口自身宽度
同步收缩/展开,且贴边一侧始终钉在屏幕边缘——因此不会出现"鼠标在窗口边界
反复进出"的闪烁。

胶囊宽度按文案实测宽度自适应(内容宽 + 左右 16px 内边距),不写死,换语言或
计数位数变化时都不会出现空旷留白或文字贴边。

拖动:按住可像普通窗口一样左右上下自由拖动,松手后按"离哪边近"自动吸附
到左/右屏幕边缘并收回细条。
"""

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import (
    Qt, Signal, QTimer, QRectF, QPoint, QVariantAnimation,
    QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import (
    QCursor, QPainter, QColor, QPen, QFont, QFontMetricsF, QLinearGradient,
)

from .app_settings import Theme
from .i18n import t

BAR_W = 48            # 收起态窗口(热区)宽度:细条 + 一圈透明热区,方便悬停
BAR_H = 64            # 窗口(热区)高度;可见形状竖直居中其中
BAR_VISIBLE_W = 6     # 贴边条可见宽度
BAR_VISIBLE_H = 44    # 贴边条可见高度
INSET = 4.0           # 形状与窗口边缘/屏幕边缘的间距
LEAVE_DELAY_MS = 420  # 鼠标移出后延时收回,避免抖动/误触
MORPH_MS = 190        # 细条↔胶囊形变动画时长

# ---- Fluent 毛玻璃胶囊规格 ----
PILL_PAD_X = 16.0                        # 内边距:左右
PILL_PAD_Y = 8.0                         # 内边距:上下
PILL_BG = QColor(30, 30, 30, 153)        # 底色 rgba(30,30,30,.6)
PILL_BORDER = QColor(255, 255, 255, 20)  # 描边 1px rgba(255,255,255,.08)
PILL_LIFT = 2.0                          # 悬停轻微上浮(px)
LABEL_PX = 14                            # "待办"字号
NUMBER_PX = 18                           # 数字字号(放大)
UNIT_PX = 12                             # "项"字号(小一号)
GAP_LABEL = 8.0                          # "待办"与数字之间
GAP_UNIT = 4.0                           # 数字与"项"之间
LABEL_COLOR = QColor("#c8c8c8")          # 浅灰
NUMBER_COLOR = QColor("#0078d4")         # 微软蓝
UNIT_COLOR = QColor("#c8c8c8")           # 浅灰


def _lighten(c, amt):
    """把颜色整体提亮 amt(0~255),用于顶部玻璃反光。"""
    return QColor(
        min(255, c.red() + amt), min(255, c.green() + amt), min(255, c.blue() + amt),
        c.alpha(),
    )


def _blend(a, b, amount):
    """在 a、b 之间按 amount(0~1)插值,含 alpha。"""
    amount = max(0.0, min(1.0, amount))
    return QColor(
        int(round(a.red() + (b.red() - a.red()) * amount)),
        int(round(a.green() + (b.green() - a.green()) * amount)),
        int(round(a.blue() + (b.blue() - a.blue()) * amount)),
        int(round(a.alpha() + (b.alpha() - a.alpha()) * amount)),
    )


class EdgeDock(QWidget):
    """贴边条(竖向细胶囊)⇄ Fluent 毛玻璃胶囊(显示待办数),可拖动并边缘吸附。"""

    summoned = Signal()          # 点击:请求唤出主窗口
    moved = Signal(int)          # 拖动结束:新的窗口顶部 Y(全局坐标)
    edge_changed = Signal(str)   # 拖动结束:吸附后的停靠边 left / right

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.resize(BAR_W, BAR_H)
        self._edge = "right"          # "left" / "right"
        self._count = 0
        self._hovered = False
        self._screen_geo = None       # 当前所在屏幕 availableGeometry (QRect)
        self._morph = 0.0             # 0=细条 1=胶囊
        self._hx = 0.0                # 0=贴边 1=自由拖动(窗口内居中)
        # 形变区间:大小与水平锚点由同一个进度同步插值
        self._morph_from = 0.0
        self._morph_to = 0.0
        self._hx_from = 0.0
        self._hx_to = 0.0
        # 松手吸附:位置在"松手点"与"贴边点"之间插值
        self._snap_from = None
        self._snap_to = None
        self._snapping = False
        # 拖动判定
        self._press_global = None
        self._press_origin = None
        self._dragging = False
        # 主题
        self._fill = QColor("#5ea0ff")   # accent:细条与强调
        self._font_family = "Segoe UI Variable"
        # 胶囊尺寸(按实测文案宽度自适应)
        self._pill_visible_w = 104.0
        self._pill_visible_h = 42.0
        self._pill_w = 112
        self._text_parts = None
        self._rebuild_layout()
        # 移出后延时收回细条
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.setInterval(LEAVE_DELAY_MS)
        self._leave_timer.timeout.connect(self._begin_collapse)
        # 形变动画(唯一的时间轴:驱动绘制 + 窗口几何)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(MORPH_MS)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._on_morph)
        self._anim.finished.connect(self._on_morph_finished)
        # 出现时从屏幕边缘外侧滑入
        self._slide_anim = QPropertyAnimation(self, b"pos", self)
        self._slide_anim.setDuration(200)
        self._slide_anim.setEasingCurve(QEasingCurve.OutCubic)

    # ---- 主题 ----
    def set_theme(self, theme: Theme):
        """胶囊配色按 Fluent 规格固定,只有字体族跟随主题。"""
        self._fill = QColor(theme.accent_color)
        self._font_family = theme.font_family
        self._rebuild_layout()
        self.update()

    # ---- 文案排版:实测宽度,驱动胶囊自适应宽度 ----
    def _rebuild_layout(self):
        label = t("main.dock_pending_label")
        unit = t("main.dock_pending_unit")
        number = str(self._count) if self._count < 100 else "99+"

        font_label = QFont(self._font_family)
        font_label.setPixelSize(LABEL_PX)
        font_label.setWeight(QFont.DemiBold)
        font_number = QFont(self._font_family)
        font_number.setPixelSize(NUMBER_PX)
        font_number.setWeight(QFont.ExtraBold)
        font_unit = QFont(self._font_family)
        font_unit.setPixelSize(UNIT_PX)
        font_unit.setWeight(QFont.Medium)

        metrics_label = QFontMetricsF(font_label)
        metrics_number = QFontMetricsF(font_number)
        metrics_unit = QFontMetricsF(font_unit)
        w_label = metrics_label.horizontalAdvance(label)
        w_number = metrics_number.horizontalAdvance(number)
        w_unit = metrics_unit.horizontalAdvance(unit) if unit else 0.0

        content_w = w_label + GAP_LABEL + w_number
        if w_unit:
            content_w += GAP_UNIT + w_unit
        content_h = max(
            metrics_label.height(), metrics_number.height(), metrics_unit.height()
        )
        self._pill_visible_w = content_w + 2 * PILL_PAD_X
        self._pill_visible_h = content_h + 2 * PILL_PAD_Y
        self._pill_w = int(round(self._pill_visible_w + 2 * INSET))
        self._text_parts = (
            label, number, unit, w_label, w_number, w_unit,
            font_label, font_number, font_unit,
        )
        self.setMinimumSize(BAR_W, BAR_H)

    # ---- 显示为贴边条 ----
    def show_bar(self, edge, y, count, screen_geo):
        """把窗口放到指定屏幕边缘、指定顶部 Y,以细条形态从边缘滑入。"""
        self._edge = edge if edge in ("left", "right") else "right"
        self._count = int(count)
        self._rebuild_layout()
        self._screen_geo = screen_geo
        self._hovered = False
        self._dragging = False
        self._snapping = False
        self._press_global = None
        self._snap_from = None
        self._snap_to = None
        self._leave_timer.stop()
        self._anim.stop()
        self._slide_anim.stop()
        self._morph = 0.0
        self._hx = 0.0
        self.setGeometry(self._edge_x(BAR_W), self._clamp_y(y), BAR_W, BAR_H)
        final = self.pos()
        # 从贴边侧外面滑入(左侧从更左、右侧从更右)
        dx = -BAR_W if self._edge == "left" else BAR_W
        self.move(final.x() + dx, final.y())
        self.show()
        self.raise_()
        self._slide_anim.setStartValue(QPoint(final.x() + dx, final.y()))
        self._slide_anim.setEndValue(final)
        self._slide_anim.start()
        self.update()

    def set_count(self, count):
        self._count = int(count)
        self._rebuild_layout()
        self._sync_geometry()
        self.update()

    # ---- 几何:尺寸随形态变化,贴边侧钉在屏幕边缘 ----
    def _clamp_y(self, y):
        geo = self._screen_geo
        if geo is None:
            return int(y)
        return max(geo.top(), min(int(y), geo.bottom() - BAR_H + 1))

    def _edge_x(self, width):
        geo = self._screen_geo
        if geo is None:
            return self.x()
        return geo.left() if self._edge == "left" else geo.right() - width + 1

    def _window_width(self, morph):
        return int(round(BAR_W + (self._pill_w - BAR_W) * morph))

    def _screen_geometry(self):
        """窗口当前所在屏幕的可用区域(跨屏拖动时用于重新贴边)。"""
        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else None

    def _clamp_free(self, pos):
        """自由拖动时把整个窗口限制在屏幕内,并同步所在屏幕。"""
        probe = QPoint(int(pos.x() + self.width() / 2), int(pos.y() + BAR_H / 2))
        screen = QApplication.screenAt(probe) or QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen is not None else self._screen_geo
        if geo is None:
            return pos
        self._screen_geo = geo
        return QPoint(
            max(geo.left(), min(pos.x(), geo.right() - self.width() + 1)),
            max(geo.top(), min(pos.y(), geo.bottom() - BAR_H + 1)),
        )

    # ---- 悬停:细条 ⇄ 胶囊(带动画;移出延时收回防抖)----
    def enterEvent(self, event):
        self._leave_timer.stop()
        if not self._snapping:  # 吸附动画期间不响应悬停,避免尺寸被反复打断
            self.setCursor(Qt.OpenHandCursor)
            if not self._hovered:
                self._hovered = True
                self._animate_to(1.0, 0.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._dragging:
            self.unsetCursor()
            self._leave_timer.start()
        super().leaveEvent(event)

    def _begin_collapse(self):
        if self._dragging:
            return
        # 二次确认:窗口尺寸在动画里一直变,leave 事件可能误报。鼠标若其实
        # 还停在窗口上,就保持展开并稍后再确认,避免"刚弹出又缩回去"。
        if self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self._leave_timer.start()
            return
        self._hovered = False
        self._animate_to(0.0, 0.0)

    def _animate_to(self, target, hx):
        """同时插值形态进度(尺寸)与水平锚点:细条↔贴边胶囊↔自由胶囊。"""
        self._morph_from = float(self._morph)
        self._morph_to = float(target)
        self._hx_from = float(self._hx)
        self._hx_to = float(hx)
        self._anim.stop()
        self._anim.setStartValue(self._morph_from)
        self._anim.setEndValue(self._morph_to)
        self._anim.start()

    def _on_morph(self, value):
        self._morph = float(value)
        span = self._morph_to - self._morph_from
        progress = 1.0 if abs(span) < 1e-6 else (self._morph - self._morph_from) / span
        progress = max(0.0, min(1.0, progress))
        self._hx = self._hx_from + (self._hx_to - self._hx_from) * progress
        self._sync_geometry()
        self.update()

    def _on_morph_finished(self):
        self._snap_from = None
        self._snap_to = None
        self._snapping = False
        self._sync_geometry()

    def _sync_geometry(self):
        """让窗口热区跟着形态一起收缩/展开,贴边侧始终保持不动。

        拖动时不接管:此时窗口位置由鼠标决定。
        """
        if self._dragging:
            return
        morph = max(0.0, min(1.0, self._morph))
        width = self._window_width(morph)
        if self._snap_from is not None:
            fx, fy = self._snap_from
            tx, ty = self._snap_to
            x = int(round(fx + (tx - fx) * morph))
            y = int(round(fy + (ty - fy) * morph))
        else:
            y = self._clamp_y(self.y())
            x = self._edge_x(width)
        self.setGeometry(x, y, width, BAR_H)

    def hideEvent(self, event):
        self._leave_timer.stop()
        self._anim.stop()
        self._slide_anim.stop()
        # 动画被打断时 finished 不会触发,这里把吸附态一并复位,免得下次
        # 显示时还停在"吸附中",连悬停展开都不响应
        self._snap_from = None
        self._snap_to = None
        self._snapping = False
        super().hideEvent(event)

    # ---- 绘制:阴影 + 毛玻璃体(底色/反光/描边) + 文案 ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Windows 分层窗口会让 alpha=0 的像素穿透鼠标,那样只有形状本身(细条)
        # 能悬停,鼠标稍一偏移就 leave → 刚弹出又缩回去。先铺一层 alpha=1 的
        # 近乎全透明的底,把整个窗口(含圆角外、阴影外)都变成可命中区域。
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        rect = self._morph_rect()
        radius = min(rect.width(), rect.height()) / 2.0   # 全胶囊(无限圆角)
        self._paint_shadow(p, rect, radius)
        self._paint_body(p, rect, radius)
        self._paint_label(p, rect)
        p.end()

    def _morph_rect(self):
        """按形变进度插值出细条→胶囊的外形,并在贴边与自由居中之间过渡。"""
        m = self._morph
        w = BAR_VISIBLE_W + (self._pill_visible_w - BAR_VISIBLE_W) * m
        h = BAR_VISIBLE_H + (self._pill_visible_h - BAR_VISIBLE_H) * m
        cy = BAR_H / 2.0 - PILL_LIFT * m      # 悬停时轻微上浮
        dock_left = INSET if self._edge == "left" else self.width() - INSET - w
        free_left = (self.width() - w) / 2.0
        left = dock_left + (free_left - dock_left) * self._hx
        return QRectF(left, cy - h / 2.0, w, h)

    def _paint_shadow(self, p, rect, radius):
        """多层同心圆角矩形外扩形成柔和投影,让胶囊从壁纸上浮起来。"""
        p.setPen(Qt.NoPen)
        strength = 0.5 + 0.5 * self._morph
        for i in range(4, 0, -1):
            spread = i * 1.4
            alpha = int((14 - i * 2.6) * strength)
            p.setBrush(QColor(0, 0, 0, max(0, alpha)))
            rr = rect.adjusted(-spread, -spread + 2.0, spread, spread + 2.0)
            p.drawRoundedRect(rr, radius + spread, radius + spread)

    def _paint_body(self, p, rect, radius):
        """细条(accent)过渡到半透明黑胶囊;顶部叠一层玻璃反光。"""
        m = self._morph
        base = _blend(self._fill, PILL_BG, m)
        top = _lighten(base, int(round(8 + 14 * (1 - m))))
        # 顶部略微提高不透明度,模拟毛玻璃边缘的反光
        top.setAlpha(min(255, base.alpha() + int(round(14 * m))))
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, top)
        grad.setColorAt(0.45, base)
        grad.setColorAt(1.0, base)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(rect, radius, radius)
        # 1px 描边:细条白色略重,胶囊按规格 8% 白
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_blend(QColor(255, 255, 255, 46), PILL_BORDER, m), 1))
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

    def _paint_label(self, p, rect):
        """展开后显示"待办 N 项":浅灰文案 + 微软蓝放大数字。

        透明度由"当前胶囊宽度是否容得下文案 + 内边距"决定,因此文字
        只在胶囊展开到位时淡入,不会在动画中途被裁切。
        """
        if self._text_parts is None:
            return
        (label, number, unit, w_label, w_number, w_unit,
         font_label, font_number, font_unit) = self._text_parts
        total = w_label + GAP_LABEL + w_number + (GAP_UNIT + w_unit if w_unit else 0.0)
        alpha = max(0.0, min(1.0, (rect.width() - total) / (2 * PILL_PAD_X)))
        if alpha <= 0.02:
            return

        x = rect.left() + (rect.width() - total) / 2.0
        y = rect.top()
        height = rect.height()

        label_color = QColor(LABEL_COLOR)
        label_color.setAlphaF(alpha)
        unit_color = QColor(UNIT_COLOR)
        unit_color.setAlphaF(alpha * 0.85)
        number_color = QColor(NUMBER_COLOR)
        number_color.setAlphaF(alpha)

        p.setFont(font_label)
        p.setPen(QPen(label_color))
        p.drawText(QRectF(x, y, w_label, height), Qt.AlignVCenter | Qt.AlignLeft, label)
        x += w_label + GAP_LABEL
        p.setFont(font_number)
        p.setPen(QPen(number_color))
        p.drawText(QRectF(x, y, w_number, height), Qt.AlignVCenter | Qt.AlignLeft, number)
        x += w_number + GAP_UNIT
        if w_unit:
            p.setFont(font_unit)
            p.setPen(QPen(unit_color))
            p.drawText(QRectF(x, y, w_unit, height), Qt.AlignVCenter | Qt.AlignLeft, unit)

    # ---- 拖动:自由移动 → 松手就近贴边 / 点击唤出 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._slide_anim.stop()
            if self._snapping:
                # 吸附动画没结束就被按下:先落到当前几何,避免后续插值错乱
                self._anim.stop()
                self._snap_from = None
                self._snap_to = None
                self._snapping = False
                self._sync_geometry()
            self._press_global = event.globalPosition().toPoint()
            self._press_origin = self.pos()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_global is not None and (event.buttons() & Qt.LeftButton):
            global_pos = event.globalPosition().toPoint()
            if not self._dragging and (global_pos - self._press_global).manhattanLength() > QApplication.startDragDistance():
                self._begin_drag(global_pos)
            if self._dragging:
                delta = global_pos - self._press_global
                self.move(self._clamp_free(self._press_origin + delta))
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._press_global is not None:
            was_dragging = self._dragging
            self._press_global = None
            self._dragging = False
            if was_dragging:
                self._snap_to_nearest_edge()
            else:
                self.summoned.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _begin_drag(self, global_pos):
        """进入自由拖动:立刻展开成胶囊,并补偿位置让形状中心原地不动。"""
        before_center = self._morph_rect().center()
        self._anim.stop()
        self._snap_from = None
        self._snap_to = None
        self._snapping = False
        self._dragging = True
        self._hovered = True
        self._leave_timer.stop()
        self.setCursor(Qt.ClosedHandCursor)
        self._morph = 1.0
        self._hx = 1.0
        self.resize(self._pill_w, BAR_H)
        after_center = self._morph_rect().center()
        self.move(
            self.x() + int(round(before_center.x() - after_center.x())),
            self.y() + int(round(before_center.y() - after_center.y())),
        )
        # 以"补偿后"为拖动起点,后续 delta 从这一刻算起
        self._press_global = global_pos
        self._press_origin = self.pos()
        self.update()

    def _snap_to_nearest_edge(self):
        """松手后按窗口中心与屏幕中线比较,吸附到更近的一侧。"""
        if self._screen_geo is None:
            self._screen_geo = self._screen_geometry()
        geo = self._screen_geo
        center_x = self.x() + self.width() / 2.0
        edge = "left" if geo is not None and center_x < geo.center().x() else "right"
        self._edge = edge
        target_y = self._clamp_y(self.y())
        self._snap_from = (self.x(), self.y())
        self._snap_to = (self._edge_x(BAR_W), target_y)
        self._snapping = True
        self._hovered = False
        self.setCursor(Qt.OpenHandCursor)
        self.moved.emit(int(target_y))
        self.edge_changed.emit(edge)
        # 用同一个进度同时收窄窗口、滑向边缘并收回细条
        self._animate_to(0.0, 0.0)
