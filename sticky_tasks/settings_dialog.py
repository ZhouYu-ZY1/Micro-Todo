"""设置窗口:外观 / 常规 / 归档数据三页签。

独立非模态窗口,不遮挡主界面;任何修改即时生效(实时预览)。
颜色使用系统选择器，字体直接在设置窗口的下拉框中选择。
窗口装饰(顶栏、关闭/最小化)均自己实现,无系统标题栏。
"""

import math
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QColorDialog, QComboBox, QSlider, QSpinBox, QCompleter,
    QAbstractSpinBox, QLineEdit, QMessageBox, QStackedWidget,
    QScrollArea, QSizePolicy, QButtonGroup, QGridLayout, QToolButton,
    QListView, QCheckBox,
)
# 注:QCompleter 仅用其枚举常量配置 combo 内置补全器,不另建实例
from PySide6.QtCore import Qt, Signal, QEvent, QSize, QRectF, QPoint, QPointF
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath,
    QPen, QPixmap, QPolygonF, QTransform, QMouseEvent,
)

from . import APP_VERSION, app_name
from . import autostart
from . import dialogs
from .app_settings import AppSettings, MIN_BG_OPACITY
from .history_window import ArchivePanel
from .i18n import LANG_EN, LANG_ZH, set_language, t
from .icons import app_icon_pixmap, screen_scale, svg_icon, svg_pixmap
from .restart import restart_app


def _rgba(color):
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


# 窗口圆角(与主窗口一致)、圆角外留给投影的透明边距,以及投影的分层参数。
WINDOW_RADIUS = 16
WINDOW_MARGIN = 10
SHADOW_ALPHA = 44
SHADOW_LAYERS = 12

# 缓存主题色箭头小图标(QSS image 不支持 data URL,只能引用本地文件)。
_ARROW_DIR = Path(tempfile.gettempdir()) / "sticky_tasks_qss_arrows"
_ARROW_DIR.mkdir(parents=True, exist_ok=True)
_ARROW_CACHE: dict[tuple[str, str], str] = {}


def _arrow_url(color: QColor, name: str) -> str:
    """返回一个 12px 箭头 PNG 的 file:// URL(按需生成并缓存)。"""
    color_name = color.name()
    key = (color_name, name)
    if key in _ARROW_CACHE:
        return _ARROW_CACHE[key]
    pixmap = svg_pixmap("chevron-down", color, 14)
    if name == "up":
        pixmap = pixmap.transformed(QTransform().rotate(180), Qt.SmoothTransformation)
    path = _ARROW_DIR / f"arrow_{name}_{color_name.lstrip('#')}.png"
    pixmap.save(str(path))
    # QSS url() 在 Windows 下用正斜杠本地路径最稳定, file:// URI 在某些样式中加载失败
    url = str(path).replace("\\", "/")
    _ARROW_CACHE[key] = url
    return url


def _check_url(color: QColor) -> str:
    """QCheckBox 勾选标记用的对勾 PNG(按需生成并缓存)。

    QSS 画不出勾:indicator 只能填充/描边,勾选形状必须给图片。
    复用 SVG 里的圆圈勾在方形指示器里不协调,这里按指示器尺寸手绘标准对勾。
    """
    key = ("check", color.name())
    if key in _ARROW_CACHE:
        return _ARROW_CACHE[key]
    side = 14
    physical = max(1, math.ceil(side * screen_scale()))
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    k = physical / side
    painter.setPen(
        QPen(color, max(1.6, 1.9 * k), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    )
    painter.drawPolyline(
        QPolygonF([QPointF(3.1 * k, 7.5 * k), QPointF(5.9 * k, 10.3 * k),
                   QPointF(10.9 * k, 4.1 * k)])
    )
    painter.end()
    path = _ARROW_DIR / f"check_{color.name().lstrip('#')}.png"
    pixmap.save(str(path))
    url = str(path).replace("\\", "/")
    _ARROW_CACHE[key] = url
    return url


def build_settings_qss(theme):
    """根据主程序主题生成与 HTML 原型一致的 Fluent 样式。"""
    bg = theme.bg_color.name()
    text = theme.text_color.name()
    muted = theme.icon_color.name()
    accent = theme.accent_color.name()
    line = "rgba(255,255,255,23)" if theme.is_dark else "rgba(0,0,0,28)"
    # 窗口外轮廓:比卡片描边略深,低对比度壁纸下也能看清窗口边界
    outline = "rgba(255,255,255,42)" if theme.is_dark else "rgba(0,0,0,46)"
    radius = WINDOW_RADIUS
    inner_radius = WINDOW_RADIUS - 1  # 壳有 1px 描边,子控件圆角相应小 1px
    surface = "rgba(255,255,255,14)" if theme.is_dark else "rgba(0,0,0,10)"
    surface2 = "rgba(255,255,255,23)" if theme.is_dark else "rgba(0,0,0,19)"
    surface3 = "rgba(255,255,255,40)" if theme.is_dark else "rgba(0,0,0,32)"
    sidebar = "rgba(0,0,0,20)" if theme.is_dark else "rgba(255,255,255,72)"
    titlebar = "rgba(0,0,0,12)" if theme.is_dark else "rgba(255,255,255,55)"
    popup = "#292a31" if theme.is_dark else "#f7f7f9"
    # 关闭按钮 hover 红色(轻微透明度),无论深浅主题都不冲突。
    close_hover = "rgba(232, 80, 80, 0.18)"
    close_hover_text = "rgb(232, 96, 96)"
    # 下拉箭头:用主文字色渲染,确保在浅色/深色主题下都看得清
    down_arrow_url = _arrow_url(theme.text_color, "down")
    # 勾选标记:白色对勾压在 accent 底色上,深浅主题都清楚
    check_url = _check_url(QColor("#ffffff"))
    return f"""
/* 窗口本体与各页面一律透明:圆角与底色只画在壳(settingsShell)上,
   子控件若带底色会在四角盖出直角,圆角就白做了。 */
QWidget#settingsWindow, QWidget#settingsPage, QWidget#scrollContent,
QStackedWidget#settingsStack, QScrollArea#settingsScroll,
QScrollArea#settingsScroll > QWidget > QWidget {{
    background: transparent; color: {text};
}}
QFrame#settingsShell {{
    background: {bg}; border: 1px solid {outline}; border-radius: {radius}px;
}}
/* 顶栏(自己实现):顶部的两个圆角要跟壳对齐 */
QFrame#titleBar {{
    background: {titlebar}; border: none; border-bottom: 1px solid {line};
    border-top-left-radius: {inner_radius}px;
    border-top-right-radius: {inner_radius}px;
}}
QLabel#titleText {{ color: {text}; font-size: 13px; font-weight: 600; padding-top: 1px; }}
QPushButton#_close {{ border: none; border-radius: 6px; background: transparent; color: {muted}; }}
QPushButton#_close:hover {{ background: {close_hover}; color: {close_hover_text}; }}
/* 侧边栏:左下角圆角要跟壳对齐 */
QFrame#sidebar {{
    background: {sidebar}; border: none; border-right: 1px solid {line};
    border-bottom-left-radius: {inner_radius}px;
}}
QLabel {{ color: {text}; font-size: 12px; background: transparent; }}
QLabel#brandTitle {{ font-size: 14px; font-weight: 650; }}
QLabel#brandSub {{ color: {muted}; font-size: 11px; margin-top: 1px; }}
QLabel#navSection {{ color: {muted}; font-size: 11px; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#pageTitle {{ font-size: 23px; font-weight: 650; }}
QLabel#pageLead, QLabel#mutedLabel, QLabel#rowNote, QLabel#sidebarFoot {{ color: {muted}; font-size: 11px; }}
QLabel#sectionTitle {{ color: {muted}; font-size: 12px; font-weight: 600; }}
QLabel#rowTitle {{ font-size: 13px; font-weight: 560; }}
/* 底部状态卡 */
QFrame#footerCard {{ background: {surface}; border: 1px solid {line}; border-radius: 10px; }}
QLabel#footerCaption {{ color: {muted}; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#footerTheme {{ color: {text}; font-size: 13px; font-weight: 600; }}
QLabel#footerVersion {{ color: {muted}; font-size: 10px; }}
QFrame#card {{ background: {surface}; border: 1px solid {line}; border-radius: 12px; }}
QFrame#rowSeparator {{ background: {line}; border: none; min-height: 1px; max-height: 1px; }}
/* 导航按钮:图标 + 文字胶囊,选中加深背景 + accent 色调;刻意去掉左侧
   3px 实色竖条,改成整体高亮更现代 */
QPushButton#navButton {{
    text-align: left; min-height: 38px; padding: 0 12px 0 14px;
    border: none; border-radius: 9px;
    color: {text}; background: transparent;
    font-size: 13px;
}}
QPushButton#navButton:hover {{ color: {text}; background: {surface}; }}
QPushButton#navButton:checked {{ color: {accent}; background: {surface3}; }}
QToolButton#presetButton {{ min-height: 58px; padding: 7px 4px; border: 1px solid {line}; border-radius: 9px; color: {muted}; background: {surface}; font-size: 11px; }}
QToolButton#presetButton:hover {{ color: {text}; background: {surface2}; }}
QToolButton#presetButton:checked {{ color: {text}; border-color: {accent}; background: {surface2}; }}
QToolButton#presetButton:disabled {{ color: {muted}; background: transparent; }}
QPushButton#actionBtn, QPushButton#ghostButton {{ min-height: 32px; padding: 0 12px; border-radius: 7px; color: {text}; background: {surface2}; border: 1px solid {line}; }}
QPushButton#actionBtn:hover, QPushButton#ghostButton:hover {{ border-color: {muted}; }}
QPushButton#wideButton {{ min-height: 32px; border-radius: 7px; color: {text}; background: {surface2}; border: 1px solid {line}; }}
QPushButton#wideButton:hover {{ border-color: {accent}; }}
QPushButton#colorBtn {{ border: 1px solid {line}; border-radius: 7px; min-width: 36px; max-width: 36px; min-height: 31px; max-height: 31px; }}
QSlider::groove:horizontal {{ height: 4px; background: {line}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; background: white; border: 4px solid {accent}; border-radius: 8px; }}
/* 开关型复选框:文字在左侧行标题里,控件本身只显示指示器 */
QCheckBox {{ color: {text}; background: transparent; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {line}; background: {surface2};
}}
QCheckBox::indicator:hover {{ border-color: {muted}; }}
QCheckBox::indicator:checked {{
    background: {accent}; border-color: {accent}; image: url({check_url});
}}
QCheckBox::indicator:disabled {{ background: transparent; border-color: {line}; }}
QSpinBox, QComboBox {{ background: {surface2}; border: 1px solid {line}; border-radius: 7px; color: {text}; min-height: 31px; padding: 0 10px; selection-background-color: {accent}; }}
QComboBox {{ padding-right: 30px; }}
QSpinBox:hover, QComboBox:hover {{ border-color: {muted}; }}
QSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
/* 下拉框箭头用主题色图标,避免系统箭头与背景融为一体看不见 */
QComboBox::drop-down {{ width: 26px; border: none; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::drop-down:hover {{ background: {line}; }}
QComboBox::down-arrow {{ image: url({down_arrow_url}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {popup}; border: 1px solid {line}; color: {text}; padding: 4px; outline: none; selection-background-color: {accent}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 3px 1px; }}
QScrollBar::handle:vertical {{ background: {theme.scrollbar_color.name()}; border-radius: 3px; min-height: 26px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {theme.scrollbar_hover_color.name()}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ color: {text}; background: {popup}; border: 1px solid {line}; padding: 4px 7px; }}
"""

# 预设主题:每套包含背景色、字体颜色、字体、字号与背景不透明度。
# key 用于界面语言文案(中英文切换),name 仅作内部标识与回退。
# 7 套配色 + 自定义预设,正好 8 个铺满两排四列。
PRESETS = [
    {"key": "preset.deep_space", "name": "深空",   "bg": "#232429", "text": "#e9eaf0", "font": "Segoe UI Variable", "size": 13, "opacity": 241},
    {"key": "preset.warm_night", "name": "暖夜",   "bg": "#2b2320", "text": "#f2e8db", "font": "Microsoft YaHei UI", "size": 13, "opacity": 236},
    {"key": "preset.forest",     "name": "森林",   "bg": "#1d2a23", "text": "#e2efe7", "font": "Microsoft YaHei UI", "size": 13, "opacity": 238},
    {"key": "preset.ocean",      "name": "海洋",   "bg": "#182438", "text": "#dbe7f6", "font": "Segoe UI Variable", "size": 13, "opacity": 241},
    {"key": "preset.lavender",   "name": "薰衣草", "bg": "#272332", "text": "#ebe6f5", "font": "Microsoft YaHei UI", "size": 13, "opacity": 237},
    {"key": "preset.ink_black",  "name": "墨黑",   "bg": "#000000", "text": "#e8e8e8", "font": "Microsoft YaHei UI", "size": 13, "opacity": 241},
    {"key": "preset.paper",      "name": "素白",   "bg": "#f3f3f5", "text": "#2b2b31", "font": "Microsoft YaHei UI", "size": 13, "opacity": 249},
]


class _NoWheelComboBox(QComboBox):
    """禁用滚轮换字体:悬停/聚焦时滚轮一动就换字体,太容易误触。"""

    def wheelEvent(self, event):
        event.ignore()  # 交给父级(页面滚动等)


class _NoWheelSpinBox(QSpinBox):
    """禁用滚轮改字号,并去掉上下按钮,只允许键盘输入数值。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)

    def wheelEvent(self, event):
        event.ignore()


class _NoWheelSlider(QSlider):
    """禁用滚轮调透明度:悬停时滚轮一动就改值,太容易误触。"""

    def wheelEvent(self, event):
        event.ignore()


class _DraggableTitle(QFrame):
    """自定义标题栏:在按钮之外的空白区按住可拖动整个窗口。

    与最小化/关闭按钮共存时,按钮会先吃掉鼠标事件,不会误触发拖动。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self._press_at = None
        self._window_origin = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_at = event.globalPosition().toPoint()
            self._window_origin = self.window().frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._press_at is not None
            and self._window_origin is not None
            and event.buttons() & Qt.LeftButton
        ):
            delta = event.globalPosition().toPoint() - self._press_at
            self.window().move(self._window_origin + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_at = None
        self._window_origin = None
        super().mouseReleaseEvent(event)


class SettingsWindow(QWidget):
    """与主窗口同主题的非模态设置窗口。"""

    changed = Signal()
    archive_changed = Signal()

    def __init__(self, settings: AppSettings, store=None, parent=None):
        super().__init__(parent)
        set_language(settings.language)
        self._settings = settings
        self._store = store
        self.archive_panel = None
        self._nav_buttons = []
        self._row_icons = []
        self._title_buttons = []

        self.setObjectName("settingsWindow")
        self.setWindowTitle(t("settings.title"))
        # 自己实现窗口装饰:用 FramelessWindowHint 整个去掉系统标题栏(也就没有
        # 系统的最小化/最大化/关闭,更不会有左上角的设置图标),由自定义顶栏接管。
        # 拖动用 _DraggableTitle 实现,关闭用自定义按钮,缩小则直接关掉。
        # 背景透明是为了圆角:圆角外与投影区交给窗口自己画(见 paintEvent)。
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 圆角外还要留一圈投影边距,窗口整体尺寸同步放大,内容区才不会被挤小。
        self.setMinimumSize(620, 540)
        self.resize(700, 660)
        self._build_ui()
        self.changed.connect(self.refresh_theme)
        self.refresh_theme()

    def _build_ui(self):
        # 最外层只留一圈透明边距(投影区),真正的窗口边框和圆角画在壳上;
        # 壳内仍是老结构:顶栏 + 主体(sidebar + stack),顶栏可拖动。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN
        )
        outer.setSpacing(0)

        self._shell = QFrame()
        self._shell.setObjectName("settingsShell")
        outer.addWidget(self._shell)

        # 壳自带 1px 描边:内边距也留 1px,子控件不会压住描边。
        shell = QVBoxLayout(self._shell)
        shell.setContentsMargins(1, 1, 1, 1)
        shell.setSpacing(0)
        shell.addWidget(self._build_title_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        shell.addLayout(body, 1)

        self._build_sidebar(body)

        self._stack = QStackedWidget()
        self._stack.setObjectName("settingsStack")
        body.addWidget(self._stack, 1)
        self._stack.addWidget(self._build_appearance_page())
        self._stack.addWidget(self._build_general_page())
        self._stack.addWidget(self._build_archive_page())

        self.show_page(0)
        self._install_click_blank_clear_focus()

    def _build_sidebar(self, host):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        # 左下角是窗口圆角,内边距比原先各多 2px,底部的状态卡才不会贴住圆角。
        side.setContentsMargins(12, 16, 12, 14)
        side.setSpacing(2)

        # 顶部不再放 logo + 应用名,避免与自定义顶栏重复;
        # 顶栏已经有 logo + 标题,这里直接给一个小的上间距作为留白。
        side.addSpacing(2)

        # 分组标签:「设置」,给下面 3 个导航一个语义头
        section_label = QLabel(t("settings.section_label"))
        section_label.setObjectName("navSection")
        section_label.setContentsMargins(12, 0, 0, 6)
        side.addWidget(section_label)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        nav_items = (
            (t("settings.nav_appearance"), "palette"),
            (t("settings.nav_general"), "settings"),
            (t("settings.nav_archive"), "archive-box"),
        )
        for index, (label, icon_name) in enumerate(nav_items):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(QCursor(Qt.PointingHandCursor))
            # 必须和 _refresh_nav_icons 里的 svg_icon(..., 16) 一致:
            # 图标位比图标大时 Qt 会把 16px 位图放大到 18px,线条立刻发虚。
            button.setIconSize(QSize(16, 16))
            button.clicked.connect(
                lambda checked=False, page=index: self.show_page(page)
            )
            self._nav_group.addButton(button, index)
            self._nav_buttons.append((button, icon_name))
            side.addWidget(button)

        side.addStretch()

        # 底部状态卡片:主题 + 版本号,看起来像 mini status card
        self._footer_card = QFrame()
        self._footer_card.setObjectName("footerCard")
        foot = QVBoxLayout(self._footer_card)
        foot.setContentsMargins(12, 10, 12, 10)
        foot.setSpacing(2)
        foot_caption = QLabel(t("settings.current_theme_caption"))
        foot_caption.setObjectName("footerCaption")
        foot.addWidget(foot_caption)
        self._footer = QLabel(t("settings.theme_custom"))
        self._footer.setObjectName("footerTheme")
        foot.addWidget(self._footer)
        foot.addSpacing(2)
        version = QLabel(f"{app_name()}  v{APP_VERSION}")
        version.setObjectName("footerVersion")
        foot.addWidget(version)
        side.addWidget(self._footer_card)
        host.addWidget(sidebar)

    def _build_title_bar(self):
        """自定义窗口顶栏:左侧 logo + 标题,右侧仅一个关闭按钮。

        顶栏用 _DraggableTitle,在按钮之外的空白处按住可拖动整个窗口。
        不提供最小化按钮:设置窗口的用法是临时打开调一调就关,不需要最小化,
        也不会跟系统任务栏里的应用图标重复占用空间。
        """
        bar = _DraggableTitle(self)
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        # 左上/右上都是窗口圆角,左右各多留 2px 免得 logo 与关闭按钮压住弧线。
        layout.setContentsMargins(18, 0, 8, 0)
        layout.setSpacing(0)

        # 应用 mark
        mark = self._app_mark(22)
        layout.addWidget(mark)
        layout.addSpacing(10)
        title = QLabel(app_name())
        title.setObjectName("titleText")
        layout.addWidget(title)
        layout.addStretch()

        self._close_btn = self._title_button("x", "_close")
        self._close_btn.clicked.connect(self.close)
        layout.addWidget(self._close_btn)

        return bar

    def _title_button(self, icon_name, obj_name):
        """标题栏上的图标按钮:均匀尺寸、悬停态变化明显。"""
        button = QPushButton(self)
        button.setObjectName(obj_name)
        button.setCursor(QCursor(Qt.PointingHandCursor))
        button.setFixedSize(36, 28)
        button.setIconSize(QSize(14, 14))
        # 用 icon_color 渲染,会在 refresh_title_bar_icons 里按主题刷新
        theme = self._settings.to_theme()
        button.setIcon(svg_icon(icon_name, theme.icon_color, 14))
        self._title_buttons.append((button, icon_name))
        return button

    def _build_appearance_page(self):
        page, body = self._make_page(
            t("settings.appearance_title"),
            t("settings.appearance_lead"),
            scrollable=True,
        )

        body.addWidget(self._section_title(t("settings.theme_presets")))
        preset_card = self._card()
        preset_grid = QGridLayout(preset_card)
        preset_grid.setContentsMargins(14, 14, 14, 14)
        preset_grid.setHorizontalSpacing(9)
        preset_grid.setVerticalSpacing(9)
        self._preset_group = QButtonGroup(self)
        self._preset_group.setExclusive(True)
        self._preset_buttons = []
        for index, preset in enumerate(PRESETS):
            button = self._preset_button(t(preset["key"]), preset["bg"])
            button.clicked.connect(
                lambda checked=False, value=preset: self._apply_preset(value)
            )
            self._preset_group.addButton(button)
            self._preset_buttons.append((button, preset))
            preset_grid.addWidget(button, index // 4, index % 4)
        self._custom_preset_btn = self._preset_button(
            t("settings.custom_preset_tip"), "#334155"
        )
        self._custom_preset_btn.clicked.connect(self._apply_custom_preset)
        self._preset_group.addButton(self._custom_preset_btn)
        custom_index = len(PRESETS)
        preset_grid.addWidget(
            self._custom_preset_btn, custom_index // 4, custom_index % 4
        )
        for column in range(4):
            preset_grid.setColumnStretch(column, 1)
        body.addWidget(preset_card)

        save_preset_btn = QPushButton(t("settings.save_preset_btn"))
        save_preset_btn.setObjectName("wideButton")
        save_preset_btn.setCursor(QCursor(Qt.PointingHandCursor))
        save_preset_btn.clicked.connect(self._save_custom_preset)
        body.addWidget(save_preset_btn)
        body.addSpacing(8)

        body.addWidget(self._section_title(t("settings.colors_section")))
        color_card = self._card()
        color_layout = self._card_layout(color_card)
        self._bg_btn = self._make_color_btn(QColor(self._settings.bg_color))
        self._bg_btn.clicked.connect(self._pick_bg_color)
        self._add_setting_row(
            color_layout,
            t("settings.bg_color"),
            t("settings.bg_color_note"),
            self._bg_btn,
            "palette",
        )
        self._txt_btn = self._make_color_btn(QColor(self._settings.text_color))
        self._txt_btn.clicked.connect(self._pick_text_color)
        self._add_setting_row(
            color_layout,
            t("settings.text_color"),
            t("settings.text_color_note"),
            self._txt_btn,
            "text-format",
            separator=False,
        )
        body.addWidget(color_card)
        body.addSpacing(8)

        body.addWidget(self._section_title(t("settings.typography_section")))
        type_card = self._card()
        type_layout = self._card_layout(type_card)

        self._font_families = sorted(QFontDatabase.families(), key=str.casefold)
        self._font_combo = _NoWheelComboBox()
        self._font_combo.setEditable(True)
        self._font_combo.setInsertPolicy(QComboBox.NoInsert)
        self._font_combo.addItems(self._font_families)
        self._font_combo.setCurrentText(self._settings.font_family)
        self._font_combo.lineEdit().setPlaceholderText(t("settings.font_search"))
        completer = self._font_combo.completer()
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self._font_combo.textActivated.connect(self._on_font_activated)
        self._font_combo.lineEdit().editingFinished.connect(self._commit_font_text)
        self._font_combo.setFixedWidth(190)
        self._style_combo_view(self._font_combo, self._settings.to_theme())
        self._add_setting_row(type_layout, t("settings.font"), "", self._font_combo)

        self._size_spin = _NoWheelSpinBox()
        self._size_spin.setRange(9, 24)
        self._size_spin.setValue(self._settings.font_size)
        self._size_spin.setSuffix(" px")
        self._size_spin.setFixedWidth(78)
        self._size_spin.valueChanged.connect(self._on_size_changed)
        self._add_setting_row(type_layout, t("settings.font_size"), "", self._size_spin)

        opacity_control = QWidget()
        opacity_layout = QHBoxLayout(opacity_control)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.setSpacing(8)
        self._op_slider = _NoWheelSlider(Qt.Horizontal)
        self._op_slider.setRange(MIN_BG_OPACITY, 255)
        self._op_slider.setValue(self._settings.bg_opacity)
        self._op_slider.setFixedWidth(142)
        self._op_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self._op_slider)
        self._op_label = QLabel(f"{int(self._settings.bg_opacity / 255 * 100)}%")
        self._op_label.setObjectName("mutedLabel")
        self._op_label.setFixedWidth(34)
        self._op_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        opacity_layout.addWidget(self._op_label)
        self._add_setting_row(
            type_layout,
            t("settings.bg_opacity"),
            t("settings.bg_opacity_note"),
            opacity_control,
            separator=False,
        )
        body.addWidget(type_card)
        body.addStretch()
        self._refresh_custom_preset_button()
        return page

    def _build_general_page(self):
        page, body = self._make_page(
            t("settings.general_title"),
            t("settings.general_lead"),
        )
        body.addWidget(self._section_title(t("settings.language_section")))
        card = self._card()
        layout = self._card_layout(card)
        self._lang_combo = _NoWheelComboBox()
        self._lang_combo.addItem("简体中文", LANG_ZH)
        self._lang_combo.addItem("English", LANG_EN)
        self._lang_combo.setCurrentIndex(
            1 if self._settings.language == LANG_EN else 0
        )
        self._lang_combo.setFixedWidth(130)
        self._style_combo_view(self._lang_combo, self._settings.to_theme())
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self._add_setting_row(
            layout,
            t("settings.language"),
            t("settings.language_note"),
            self._lang_combo,
            "globe",
            separator=False,
        )
        body.addWidget(card)

        body.addSpacing(8)
        body.addWidget(self._section_title(t("settings.startup_section")))
        startup_card = self._card()
        startup_layout = self._card_layout(startup_card)
        self._autostart_box = QCheckBox()
        self._autostart_box.setCursor(QCursor(Qt.PointingHandCursor))
        self._autostart_box.setChecked(autostart.is_enabled())
        # 非 Windows 或注册表不可写时直接禁用,避免开关拨不动又没有解释
        self._autostart_box.setEnabled(autostart.is_supported())
        self._autostart_box.toggled.connect(self._on_autostart_toggled)
        self._add_setting_row(
            startup_layout,
            t("settings.autostart"),
            t("settings.autostart_note"),
            self._autostart_box,
            "circle-check",
            separator=False,
        )
        body.addWidget(startup_card)
        body.addStretch()
        return page

    def _build_archive_page(self):
        page, body = self._make_page(
            t("settings.archive_title"),
            t("settings.archive_lead"),
        )
        if self._store is not None:
            self.archive_panel = ArchivePanel(self._store)
            self.archive_panel.changed.connect(self.archive_changed.emit)
            body.addWidget(self.archive_panel, 1)
        else:
            card = self._card()
            layout = QVBoxLayout(card)
            unavailable = QLabel(t("settings.archive_unavailable"))
            unavailable.setObjectName("mutedLabel")
            unavailable.setAlignment(Qt.AlignCenter)
            layout.addWidget(unavailable)
            body.addWidget(card, 1)
        return page

    def _app_mark(self, size):
        """顶栏品牌 mark:直接取应用图标 assets/icon.ico(与任务栏/exe 同一个)。

        以前用同构的简化 SVG(蓝底 + 白页 + 对勾),细节比真实图标少,
        和任务栏图标对不上。图标自带颜色,不跟主题走。
        """
        label = QLabel()
        label.setFixedSize(size, size)
        label.setPixmap(app_icon_pixmap(size))
        label.setAlignment(Qt.AlignCenter)
        return label

    def _section_title(self, text):
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        label.setContentsMargins(0, 4, 0, 2)
        return label

    @staticmethod
    def _card():
        card = QFrame()
        card.setObjectName("card")
        return card

    @staticmethod
    def _card_layout(card):
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        return layout

    def _add_setting_row(
        self, layout, title, note, control, icon_name=None, separator=True
    ):
        row = QWidget()
        row.setMinimumHeight(56)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 9, 14, 9)
        row_layout.setSpacing(12)
        if icon_name:
            icon = QLabel()
            icon.setFixedSize(18, 18)
            icon.setPixmap(
                svg_pixmap(icon_name, self._settings.to_theme().icon_color, 18)
            )
            self._row_icons.append((icon, icon_name))
            row_layout.addWidget(icon)
        info = QVBoxLayout()
        info.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("rowTitle")
        info.addWidget(title_label)
        if note:
            note_label = QLabel(note)
            note_label.setObjectName("rowNote")
            info.addWidget(note_label)
        row_layout.addLayout(info, 1)
        row_layout.addWidget(control)
        layout.addWidget(row)
        if separator:
            line = QFrame()
            line.setObjectName("rowSeparator")
            layout.addWidget(line)

    def _preset_button(self, text, color):
        button = QToolButton()
        button.setObjectName("presetButton")
        button.setCheckable(True)
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIcon(self._swatch_icon(QColor(color)))
        button.setIconSize(QSize(25, 25))
        button.setCursor(QCursor(Qt.PointingHandCursor))
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    @staticmethod
    def _swatch_icon(color):
        """色块圆点:按屏幕缩放率渲染,避免高分屏下被放大后边缘发虚。"""
        scale = screen_scale()
        side = 25
        physical = max(1, math.ceil(side * scale))
        pixmap = QPixmap(physical, physical)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        k = physical / side  # 逻辑坐标 -> 物理像素
        painter.setPen(QColor(255, 255, 255, 76))
        painter.setBrush(color)
        painter.drawEllipse(QRectF(1 * k, 1 * k, 23 * k, 23 * k))
        painter.end()
        pixmap.setDevicePixelRatio(physical / side)
        return QIcon(pixmap)

    def _make_page(self, title, lead, scrollable=False):
        page = QWidget()
        page.setObjectName("settingsPage")
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(page)
        # 圆角吃掉了一点视觉边界,正文内边距各加 2px,留白更从容。
        layout.setContentsMargins(29, 27, 29, 27)
        layout.setSpacing(0)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        layout.addSpacing(5)
        lead_label = QLabel(lead)
        lead_label.setObjectName("pageLead")
        lead_label.setWordWrap(True)
        layout.addWidget(lead_label)
        layout.addSpacing(22)

        if not scrollable:
            return page, layout

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setObjectName("scrollContent")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 6, 0)
        body.setSpacing(10)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page, body

    def show_page(self, index):
        if not 0 <= index < self._stack.count():
            return
        self._stack.setCurrentIndex(index)
        button = self._nav_group.button(index)
        if button is not None:
            button.setChecked(True)
        if index == 2 and self.archive_panel is not None:
            self.archive_panel.refresh()
        self._refresh_nav_icons()

    def show_archive_page(self):
        self.show_page(2)

    # ---- 绘制:圆角壳外的柔和投影 ----
    def paintEvent(self, event):
        """Frameless 窗口没有系统投影,自己在圆角壳外画一层由内向外渐隐的影。

        从壳的边缘向外画多层圆角矩形的"环带"(外扩矩形减去壳矩形),
        越往外 alpha 越低,形成背景→透明的过渡;环带画法保证壳内部不被叠加。
        """
        super().paintEvent(event)
        if not hasattr(self, "_shell"):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        cr = QRectF(self._shell.geometry())
        inner = QPainterPath()
        inner.addRoundedRect(cr, WINDOW_RADIUS, WINDOW_RADIUS)
        for i in range(SHADOW_LAYERS, 0, -1):
            expand = WINDOW_MARGIN * i / SHADOW_LAYERS
            alpha = int(SHADOW_ALPHA * (1.0 - (i - 1) / SHADOW_LAYERS))
            ring = QPainterPath()
            ring.addRoundedRect(
                cr.adjusted(-expand, -expand, expand, expand),
                WINDOW_RADIUS + expand,
                WINDOW_RADIUS + expand,
            )
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawPath(ring.subtracted(inner))
        p.end()

    def refresh_theme(self):
        theme = self._settings.to_theme()
        self.setStyleSheet(build_settings_qss(theme))
        self.setFont(QFont(theme.font_family, 10))
        self._style_combo_view(self._font_combo, theme)
        self._style_combo_view(self._lang_combo, theme)
        if self.archive_panel is not None:
            self.archive_panel.set_theme(theme)
        self._refresh_nav_icons()
        self._refresh_title_buttons_icons()
        for label, icon_name in self._row_icons:
            label.setPixmap(svg_pixmap(icon_name, theme.icon_color, 18))
        self._sync_preset_selection()

    def _refresh_nav_icons(self):
        theme = self._settings.to_theme()
        current = self._stack.currentIndex()
        for index, (button, icon_name) in enumerate(self._nav_buttons):
            # 选中用强调色(配合高亮背景双重指示),未选中用主文字色,
            # 跟正文层级保持一致——导航按钮是用户每次打开都盯着的功能项,
            # 不该是次要的灰色。
            color = theme.accent_color if index == current else theme.text_color
            button.setIcon(svg_icon(icon_name, color, 16))

    def _refresh_title_buttons_icons(self):
        """顶栏按钮(最小化/关闭)的图标也要按主题色刷新。"""
        theme = self._settings.to_theme()
        for button, icon_name in self._title_buttons:
            button.setIcon(svg_icon(icon_name, theme.icon_color, 14))

    def set_text_hidden(self, hidden):
        if self.archive_panel is not None:
            self.archive_panel.set_text_hidden(hidden)

    def refresh_archive(self):
        if self.archive_panel is not None:
            self.archive_panel.refresh()

    # ---- 点击空白处清除焦点(消掉字号框的蓝色选中高亮)----
    _FOCUS_KEEPERS = (QComboBox, QAbstractSpinBox, QLineEdit, QSlider)

    def _install_click_blank_clear_focus(self):
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.MouseButtonPress
            and not isinstance(obj, self._FOCUS_KEEPERS)
        ):
            focused = self.focusWidget()
            if focused is not None:
                focused.clearFocus()
        return super().eventFilter(obj, event)

    # ---- 开机自启动 ----
    def _on_autostart_toggled(self, enabled):
        """写注册表失败(被安全软件拦截等)时把开关拨回原位并说明原因。"""
        if autostart.set_enabled(enabled):
            return
        self._autostart_box.blockSignals(True)
        self._autostart_box.setChecked(not enabled)
        self._autostart_box.blockSignals(False)
        dialogs.warning(self, app_name(), t("settings.autostart_failed"))

    # ---- 语言(两段式确认:确认切换 → 提示重启) ----
    def _on_language_changed(self, index):
        lang = self._lang_combo.itemData(index)
        if lang == self._settings.language:
            return
        old_index = 1 if self._settings.language == LANG_EN else 0
        lang_name = "English" if lang == LANG_EN else "中文"

        # 第一段:用旧语言确认,用户看得懂才能做决定
        box = dialogs.message_box(self)
        box.setWindowTitle(app_name())
        box.setText(t("settings.lang_confirm", lang=lang_name))
        confirm_btn = box.addButton(t("common.confirm"), QMessageBox.AcceptRole)
        box.addButton(t("common.cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not confirm_btn:
            # 取消:下拉框回退,不保存任何改动
            self._lang_combo.blockSignals(True)
            self._lang_combo.setCurrentIndex(old_index)
            self._lang_combo.blockSignals(False)
            return

        self._settings.language = lang
        set_language(lang)
        self.changed.emit()

        # 第二段:用新语言提示,顺带预览新语言效果
        box2 = dialogs.message_box(self)
        box2.setWindowTitle(app_name())
        box2.setText(t("settings.lang_restart"))
        restart_btn = box2.addButton(t("common.restart_now"), QMessageBox.AcceptRole)
        box2.addButton(t("common.later"), QMessageBox.RejectRole)
        box2.exec()
        if box2.clickedButton() is restart_btn:
            restart_app()

    # ---- 工具 ----
    def _separator(self):
        """分区之间的细横线(不用文字标题,版面更干净)。"""
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255, 255, 255, 18);")
        return sep

    def _row_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #9698a3; font-size: 12px; font-weight: 500;")
        lbl.setFixedHeight(18)
        return lbl

    def _make_color_btn(self, color: QColor) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("colorBtn")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._paint_color_btn(btn, color)
        return btn

    def _paint_color_btn(self, btn: QPushButton, color: QColor):
        btn.setStyleSheet(
            f"QPushButton#colorBtn {{"
            f"  background: {color.name()};"
            f"  border: 1px solid rgba(255,255,255,30);"
            f"  border-radius: 6px;"
            f"  min-width: 60px; min-height: 26px;"
            f"}}"
        )

    def _emit_changed(self):
        """将当前 UI 状态写回 settings 并通知主窗口刷新。"""
        self._settings.bg_color = self._bg_color.name()
        self._settings.text_color = self._txt_color.name()
        if self._font_combo.currentText() in self._font_families:
            self._settings.font_family = self._font_combo.currentText()
        self._settings.font_size = self._size_spin.value()
        self._settings.bg_opacity = self._op_slider.value()
        self.changed.emit()

    # ---- 槽 ----
    def _pick_bg_color(self):
        color = self._show_color_dialog(
            QColor(self._settings.bg_color), t("settings.pick_bg"),
        )
        if color.isValid():
            self._bg_color = color
            self._paint_color_btn(self._bg_btn, color)
            self._emit_changed()
        else:
            self.changed.emit()

    def _pick_text_color(self):
        color = self._show_color_dialog(
            QColor(self._settings.text_color), t("settings.pick_text"),
        )
        if color.isValid():
            self._txt_color = color
            self._paint_color_btn(self._txt_btn, color)
            self._emit_changed()
        else:
            self.changed.emit()

    def _on_font_activated(self, family):
        if family in self._font_families:
            self._settings.font_family = family
            self.changed.emit()

    def _commit_font_text(self):
        family = self._font_combo.currentText().strip()
        match = next(
            (name for name in self._font_families if name.casefold() == family.casefold()),
            None,
        )
        self._font_combo.setCurrentText(match or self._settings.font_family)
        if match:
            self._settings.font_family = match
            self.changed.emit()

    def _on_size_changed(self, val):
        self._emit_changed()

    def _on_opacity_changed(self, val):
        self._op_label.setText(f"{int(val / 255 * 100)}%")
        self._emit_changed()

    def _apply_preset(self, preset):
        """一键应用预设主题。"""
        self._bg_color = QColor(preset["bg"])
        self._txt_color = QColor(preset["text"])
        self._paint_color_btn(self._bg_btn, self._bg_color)
        self._paint_color_btn(self._txt_btn, self._txt_color)
        self._font_combo.blockSignals(True)
        self._size_spin.blockSignals(True)
        self._op_slider.blockSignals(True)
        self._font_combo.setCurrentText(preset["font"])
        self._size_spin.setValue(preset["size"])
        self._op_slider.setValue(preset["opacity"])
        self._font_combo.blockSignals(False)
        self._size_spin.blockSignals(False)
        self._op_slider.blockSignals(False)
        self._op_label.setText(f"{int(preset['opacity'] / 255 * 100)}%")
        self._emit_changed()

    def _save_custom_preset(self):
        self._settings.custom_preset = {
            "name": "自定义",
            "bg": self._settings.bg_color,
            "text": self._settings.text_color,
            "font": self._settings.font_family,
            "size": self._settings.font_size,
            "opacity": self._settings.bg_opacity,
        }
        self._refresh_custom_preset_button()
        self.changed.emit()

    def _apply_custom_preset(self):
        if self._settings.custom_preset is not None:
            self._apply_preset(self._settings.custom_preset)

    def _refresh_custom_preset_button(self):
        preset = self._settings.custom_preset
        color = QColor(preset["bg"]) if preset is not None else QColor("#34353d")
        self._custom_preset_btn.setIcon(self._swatch_icon(color))
        self._custom_preset_btn.setToolTip(
            t("settings.custom_preset_tip") if preset is not None
            else t("settings.no_custom_preset"),
        )
        self._custom_preset_btn.setEnabled(preset is not None)
        if preset is None:
            self._custom_preset_btn.setChecked(False)

    def _preset_matches(self, preset):
        """当前外观是否与某套预设一致。

        颜色、字号、透明度必须完全相同;字体只在系统确实安装了该字体时
        才参与比较,否则预设字体缺失会导致整套预设永远无法命中。
        """
        settings = self._settings
        font_ok = (
            preset["font"] == settings.font_family
            or preset["font"] not in self._font_families
        )
        return (
            QColor(preset["bg"]).name() == QColor(settings.bg_color).name()
            and QColor(preset["text"]).name() == QColor(settings.text_color).name()
            and font_ok
            and int(preset["size"]) == int(settings.font_size)
            and int(preset["opacity"]) == int(settings.bg_opacity)
        )

    def _sync_preset_selection(self):
        """按当前外观高亮对应的预设按钮,不匹配任何预设时全部取消选中。"""
        if not hasattr(self, "_preset_group"):
            return
        for button, preset in self._preset_buttons:
            if self._preset_matches(preset):
                button.setChecked(True)
                self._update_footer(t(preset["key"]))
                return
        custom = self._settings.custom_preset
        if custom is not None and self._preset_matches(custom):
            self._custom_preset_btn.setChecked(True)
            self._update_footer(t("settings.theme_custom"))
            return
        # 互斥组内无法直接取消,需临时解除互斥
        self._preset_group.setExclusive(False)
        for button, _ in self._preset_buttons:
            button.setChecked(False)
        self._custom_preset_btn.setChecked(False)
        self._preset_group.setExclusive(True)
        self._update_footer(t("settings.theme_custom"))

    def _update_footer(self, theme_name):
        """侧边栏底部状态卡:只更新当前主题名(版本号已在卡片里独立显示)。"""
        if not hasattr(self, "_footer"):
            return
        self._footer.setText(theme_name)

    def _restore_custom_colors(self):
        for index, color in enumerate(self._settings.custom_colors):
            if index < QColorDialog.customCount():
                QColorDialog.setCustomColor(index, QColor(color))

    def _style_combo_view(self, combo, theme):
        """给 QComboBox 的弹窗列表单独设置与主题一致的 QSS,
        避免 Windows 深色模式/原生样式把弹窗背景和文字都刷成黑色。"""
        popup = "#292a31" if theme.is_dark else "#f7f7f9"
        text = theme.text_color.name()
        accent = theme.accent_color.name()
        line = "rgba(255,255,255,23)" if theme.is_dark else "rgba(0,0,0,28)"
        view = combo.view()
        if view is None:
            view = QListView(combo)
            combo.setView(view)
        view.setObjectName("themedComboView")
        view.setStyleSheet(f"""
QListView#themedComboView {{
    background: {popup};
    color: {text};
    padding: 4px;
    outline: none;
    selection-background-color: {accent};
}}
QListView#themedComboView::item {{
    color: {text};
    border-radius: 4px;
    padding: 4px 8px;
}}
QListView#themedComboView::item:selected {{
    background: {accent};
    color: {text};
}}
QListView#themedComboView::item:hover {{
    background: {line};
}}
""")

    def _build_color_dialog_qss(self, theme):
        """为 QColorDialog 生成与当前主题一致的样式表。"""
        bg = theme.bg_color.name()
        text = theme.text_color.name()
        muted = theme.icon_color.name()
        accent = theme.accent_color.name()
        line = "rgba(255,255,255,23)" if theme.is_dark else "rgba(0,0,0,28)"
        surface2 = "rgba(255,255,255,23)" if theme.is_dark else "rgba(0,0,0,19)"
        popup = "#292a31" if theme.is_dark else "#f7f7f9"
        return f"""
QColorDialog {{
    background: {bg};
    color: {text};
}}
QColorDialog QLabel {{
    color: {text};
    background: transparent;
}}
QColorDialog QPushButton {{
    color: {text};
    background: {surface2};
    border: 1px solid {line};
    border-radius: 6px;
    padding: 4px 12px;
}}
QColorDialog QPushButton:hover {{
    border-color: {muted};
}}
QColorDialog QLineEdit,
QColorDialog QSpinBox,
QColorDialog QComboBox {{
    color: {text};
    background: {surface2};
    border: 1px solid {line};
    border-radius: 5px;
    padding: 2px 6px;
    selection-background-color: {accent};
}}
QColorDialog QListView {{
    background: {popup};
    color: {text};
    outline: none;
    selection-background-color: {accent};
}}
QColorDialog QListView::item:selected {{
    background: {accent};
    color: {text};
}}
QColorDialog QListView::item:hover {{
    background: {line};
}}
"""

    def _show_color_dialog(self, initial, title):
        self._restore_custom_colors()
        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle(title)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        # 用当前主题重新装扮颜色对话框,避免父窗口样式/系统深色把它变成黑块
        dialog.setStyleSheet(self._build_color_dialog_qss(self._settings.to_theme()))
        accepted = dialog.exec()
        self._remember_custom_colors()
        return dialog.selectedColor() if accepted else QColor()

    def _remember_custom_colors(self):
        self._settings.custom_colors = [
            QColorDialog.customColor(index).name()
            for index in range(QColorDialog.customCount())
            if QColorDialog.customColor(index).isValid()
        ]

    # ---- 初始化内部状态(从 settings 读取) ----
    @property
    def _bg_color(self):
        return QColor(self._settings.bg_color)

    @_bg_color.setter
    def _bg_color(self, c: QColor):
        self._settings.bg_color = c.name()

    @property
    def _txt_color(self):
        return QColor(self._settings.text_color)

    @_txt_color.setter
    def _txt_color(self, c: QColor):
        self._settings.text_color = c.name()
