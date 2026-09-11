"""主窗口:半透明、无边框、普通层级的桌面便签。"""

import sys
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    _user32 = ctypes.WinDLL("user32")
    # 必须声明 argtypes:HWND_TOPMOST(-1)/HWND_NOTOPMOST(-2) 是 64 位
    # 指针宽度的哨兵值,不声明时 ctypes 按 32 位 int 传递,高字节
    # 为垃圾值,调用会静默失败(置顶不生效/取消不掉)。
    _user32.SetWindowPos.restype = ctypes.c_int
    _user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint,
    ]
else:
    _user32 = None

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QMenu, QGraphicsOpacityEffect, QAbstractButton, QMessageBox,
)
from PySide6.QtCore import (
    Qt, QEvent, QSize, Signal, QRectF, QPropertyAnimation, QEasingCurve,
    QTimer,
)
from PySide6.QtGui import (
    QCursor, QPixmap, QPainter, QPainterPath, QColor, QFont,
    QShortcut, QKeySequence,
)

from . import app_name
from . import dialogs
from .i18n import t
from .icons import svg_icon
from .task_store import TaskStore
from .task_item import TaskItem
from .group_widget import TaskGroupWidget
from .drag_session import DragSession
from .edge_dock import EdgeDock, BAR_H
from .app_paths import SETTINGS_FILE
from .app_settings import AppSettings, Theme
from .settings_dialog import SettingsWindow
from .tray import TrayIcon

def build_qss(t: Theme) -> str:
    """根据主题动态生成 QSS。"""
    bg = t.bg_color
    # 背景用纯色:垂直渐变的色差只有约 22 个灰阶却要铺满整个窗口高度,
    # 8bit 量化下会出现一条条水平色带,中等透明度时尤其明显。
    op = t.bg_opacity
    sep = t.sep_color
    sb = t.scrollbar_color
    sbh = t.scrollbar_hover_color
    txt = t.text_color
    ico = t.icon_color
    ico_h = t.icon_hover_color
    hl = t.highlight_color
    acc = t.accent_color

    return f"""
QFrame#container {{
    background: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {op});
    border: 1px solid rgba({sep.red()}, {sep.green()}, {sep.blue()}, {min(90, sep.alpha() + 30)});
    border-radius: 16px;
}}
QFrame#sectionSep {{
    background: rgba({sep.red()}, {sep.green()}, {sep.blue()}, {max(8, sep.alpha() - 4)});
    border: none;
    max-height: 1px;
    margin: 0 12px;
}}
QLabel {{ color: {txt.name()}; font-size: {t.font_size}px; font-family: "{t.font_family}"; }}
QStackedWidget#taskStack {{ background: transparent; }}
QLabel#taskText {{
    background: transparent;
    border: none;
    color: {txt.name()};
    font-size: {t.font_size}px;
    font-family: "{t.font_family}";
    padding: 0px;
}}
QPlainTextEdit#taskEdit {{
    background: rgba({hl.red()},{hl.green()},{hl.blue()},{max(14, hl.alpha())});
    border: 1px solid rgba({acc.red()}, {acc.green()}, {acc.blue()}, 145);
    border-radius: 9px;
    color: {txt.name()};
    font-size: {t.font_size}px;
    font-family: "{t.font_family}";
    padding: 5px 8px;
    selection-background-color: rgba({acc.red()}, {acc.green()}, {acc.blue()}, 110);
}}
QLabel#titleLabel {{
    color: {t.fixed_title_color.name()};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    font-family: "Segoe UI Variable";
}}
QPushButton {{ color: {txt.name()}; background: transparent; border: none; }}
QWidget#taskGroup {{
    background: transparent;
    margin: 4px 8px 2px 8px;
}}
QFrame#groupHeader {{
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {max(8, hl.alpha() - 1)});
    border: 1px solid rgba({sep.red()}, {sep.green()}, {sep.blue()}, {max(10, sep.alpha() - 3)});
    border-radius: 11px;
}}
QLabel#groupName {{
    color: {txt.name()};
    font-size: {max(10, t.font_size - 1)}px;
    font-family: "{t.font_family}";
    font-weight: 600;
}}
QLabel#groupCount {{
    color: rgba({ico.red()}, {ico.green()}, {ico.blue()}, 185);
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha() + 5});
    border: 1px solid rgba({sep.red()}, {sep.green()}, {sep.blue()}, {sep.alpha()});
    border-radius: 8px;
    min-width: 16px;
    padding: 1px 5px;
    font-size: {max(9, t.font_size - 3)}px;
}}
QPushButton#groupChevron {{
    color: rgba({ico.red()}, {ico.green()}, {ico.blue()}, 220);
    background: transparent;
    border: none;
    border-radius: 7px;
    font-size: 10px;
}}
QPushButton#groupChevron:hover {{
    color: {acc.name()};
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha() + 6});
}}
QPushButton#groupAddBtn {{
    color: rgba({ico.red()}, {ico.green()}, {ico.blue()}, 220);
    background: transparent;
    border: none;
    border-radius: 8px;
    font-size: 17px;
    font-weight: 500;
}}
QPushButton#groupAddBtn:hover {{
    color: {acc.name()};
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha() + 8});
}}
QPushButton#groupCompletedBtn {{
    color: rgba({ico.red()}, {ico.green()}, {ico.blue()}, 190);
    background: transparent;
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 6px 8px 6px 18px;
    margin: 1px 8px;
    font-size: {max(9, t.font_size - 3)}px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QPushButton#groupCompletedBtn:hover {{
    color: {acc.name()};
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha()});
}}
QFrame#completedItem {{
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {max(7, hl.alpha() - 2)});
    border: 1px solid rgba({sep.red()}, {sep.green()}, {sep.blue()}, {max(8, sep.alpha() - 4)});
    border-radius: 9px;
    margin: 2px 8px;
}}
QFrame#completedItem:hover {{
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha() + 5});
    border-color: rgba({sep.red()}, {sep.green()}, {sep.blue()}, {sep.alpha() + 8});
}}
QLabel#doneTextDone {{
    color: rgba({ico.red()},{ico.green()},{ico.blue()},200);
    font-family: "{t.font_family}";
    font-size: {max(9, t.font_size - 1)}px;
    text-decoration: line-through;
}}
QPushButton#restoreBtn {{
    color: rgba({ico.red()},{ico.green()},{ico.blue()},210);
    background: transparent;
    border: 1px solid rgba({ico.red()},{ico.green()},{ico.blue()},45);
    border-radius: 7px;
    padding: 1px 4px;
    font-size: 12px;
}}
QPushButton#restoreBtn:hover {{
    color: #ffffff;
    background: rgba({acc.red()}, {acc.green()}, {acc.blue()}, 100);
    border-color: rgba({acc.red()}, {acc.green()}, {acc.blue()}, 160);
}}
QPushButton#newGroupBtn {{
    color: rgba({ico.red()}, {ico.green()}, {ico.blue()}, 205);
    background: transparent;
    border: 1px dashed rgba({ico.red()}, {ico.green()}, {ico.blue()}, 42);
    border-radius: 10px;
    text-align: left;
    padding: 8px 12px;
    margin: 5px 8px 3px 8px;
    font-size: {max(10, t.font_size - 2)}px;
    font-weight: 600;
}}
QPushButton#newGroupBtn:hover {{
    color: {acc.name()};
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha()});
    border-color: rgba({acc.red()}, {acc.green()}, {acc.blue()}, 100);
}}
QPushButton#settingsBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 4px;
}}
QPushButton#settingsBtn:hover {{
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha() + 5});
    border-color: rgba({sep.red()}, {sep.green()}, {sep.blue()}, {sep.alpha()});
}}
QFrame#footerBar {{
    border-top: 1px solid rgba({sep.red()}, {sep.green()}, {sep.blue()}, {max(8, sep.alpha() - 4)});
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {max(3, hl.alpha() - 6)});
}}
QScrollArea#listScroll {{ border: none; background: transparent; }}
QScrollArea#listScroll viewport {{ background: transparent; }}
QWidget#listWidget {{ background: transparent; }}
QLabel#emptyHint {{
    color: rgba({ico.red()}, {ico.green()}, {ico.blue()}, 120);
    font-size: 11px;
    padding: 8px 18px 2px 18px;
}}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 6px 0; }}
QScrollBar::handle:vertical {{
    background: rgba({sb.red()},{sb.green()},{sb.blue()},{sb.alpha()});
    border-radius: 2px;
    min-height: 24px;
    margin: 0 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba({sbh.red()},{sbh.green()},{sbh.blue()},{sbh.alpha()});
    border-radius: 3px;
    margin: 0 1px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""

EDGE = 10           # 边 resize 检测宽度(匹配 8px 外边距)
CORNER = 14         # 角 resize 检测范围(缩小避免与右下角设置按钮重叠)
MIN_W, MIN_H = 220, 200
PANEL_H = 160       # 已完成面板展开时向下扩展的高度
IDLE_COLLAPSE_MS = 5000   # 鼠标离开或窗口切到后台,满这么久就自动收起为贴边条
DOCK_WATCHDOG_MS = 3000   # 贴边条兜底自检间隔(防止"收起后什么都看不到")


class _SvgStateButton(QWidget):
    """保持原有交互接口，仅将状态图形改为 SVG。"""
    toggled = Signal(bool)

    def __init__(self, inactive_icon, active_icon, active=False, accent_active=True, parent=None):
        super().__init__(parent)
        self._inactive_icon = inactive_icon
        self._active_icon = active_icon
        self._active = active
        self._accent_active = accent_active
        self._color = QColor("#8e9099")
        self._accent = QColor("#5ea0ff")
        self._refresh_icon()

    def set_theme(self, theme: Theme):
        self._color = theme.icon_color
        self._accent = theme.accent_color
        self._refresh_icon()

    def _set_active(self, active):
        self._active = active
        self._refresh_icon()

    def _refresh_icon(self):
        color = self._accent if self._active and self._accent_active else self._color
        name = self._active_icon if self._active else self._inactive_icon
        self._icon = svg_icon(name, color, 18)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        self._icon.paint(p, self.rect(), Qt.AlignCenter)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggled.emit(not self._active)
            event.accept()
            return
        super().mousePressEvent(event)


class LockButton(_SvgStateButton):
    def __init__(self, locked=False, parent=None):
        super().__init__("unlock", "lock", locked, accent_active=False, parent=parent)
        self._sync_tooltip()

    def set_locked(self, locked):
        self._set_active(locked)
        self._sync_tooltip()

    def _sync_tooltip(self):
        action = t("main.lock_action_on") if self._active else t("main.lock_action_off")
        self.setToolTip(t("main.lock_tooltip", action=action))

class PinButton(_SvgStateButton):
    """图钉按钮：置顶态切换为高亮 SVG。"""
    def __init__(self, pinned=False, parent=None):
        super().__init__("pin-off", "pin", pinned, parent=parent)
        self._sync_tooltip()

    def set_pinned(self, pinned):
        self._set_active(pinned)
        self._sync_tooltip()

    def _sync_tooltip(self):
        self.setToolTip(
            t("main.pin_tooltip_on") if self._active else t("main.pin_tooltip_off"),
        )


class EyeButton(_SvgStateButton):
    """眼睛按钮：隐藏态切换为高亮的 eye-off SVG。"""
    def __init__(self, hidden=False, parent=None):
        super().__init__("eye", "eye-off", hidden, parent=parent)
        self._sync_tooltip()

    def set_hidden(self, hidden):
        self._set_active(hidden)
        self._sync_tooltip()

    def _sync_tooltip(self):
        self.setToolTip(
            t("main.eye_tooltip_on") if self._active else t("main.eye_tooltip_off"),
        )

class HeaderBar(QFrame):
    """上方栏:标题、锁头、空白拖动区域及右键菜单。"""

    def __init__(self, window):
        super().__init__()
        self._window = window

        hl = QHBoxLayout(self)
        hl.setContentsMargins(18, 7, 12, 7)
        hl.setSpacing(6)
        # 固定高度:锁头隐藏(锁定+鼠标移出)时顶部栏不塌缩
        self.setFixedHeight(42)

        self.title_label = QLabel(app_name())
        self.title_label.setObjectName("titleLabel")
        hl.addWidget(self.title_label)
        hl.addStretch()

        # 图钉:置顶/取消置顶;眼睛:隐藏/显示任务文本;都在锁头左侧
        self.pin_btn = PinButton(parent=self)
        self.pin_btn.setFixedSize(28, 28)
        self.pin_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.pin_btn.toggled.connect(lambda p: window.set_always_on_top(p))
        hl.addWidget(self.pin_btn)

        self.eye_btn = EyeButton(parent=self)
        self.eye_btn.setFixedSize(28, 28)
        self.eye_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.eye_btn.toggled.connect(lambda h: window.set_text_hidden(h))
        hl.addWidget(self.eye_btn)

        # 锁头:锁定/解锁窗口(提示文案随状态切换)
        self.lock_btn = LockButton(parent=self)
        self.lock_btn.setFixedSize(28, 28)
        self.lock_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.lock_btn.toggled.connect(lambda l: window.set_locked(l))
        hl.addWidget(self.lock_btn)

    def contextMenuEvent(self, event):
        # 锁定态下右键菜单不响应(解锁走锁头点击)
        if self._window._locked:
            return
        self._window.show_header_menu(event.globalPos())


class MainWindow(QWidget):
    def __init__(self, store: TaskStore, settings_path: Path = None):
        super().__init__()
        self.store = store
        self._settings_path = settings_path or SETTINGS_FILE
        self.settings = AppSettings.load(self._settings_path)
        self.theme = self.settings.to_theme()
        self._drag_pos = None
        self._group_widgets = {}  # group_id -> TaskGroupWidget
        self._locked = False
        self._always_on_top = self.settings.always_on_top  # 置顶态,showEvent 里原生应用
        self._text_hidden = False  # 隐私模式(不持久化,启动默认显示)
        self._completed_expanded = False
        self._collapsed_h = None  # 已完成面板折叠时窗口高度
        self._expanded_panel_h = 0
        self._panel_lift = 0
        self._resize_dir = None
        self._resize_start_geo = None
        self._resize_origin = None
        self._edge_watch_ready = False
        self._cursor_overriding = False  # 是否已压入应用级 resize 光标
        self._settings_dirty = False
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(180)
        self._settings_save_timer.timeout.connect(self._flush_settings_save)
        QApplication.instance().aboutToQuit.connect(self._save_settings_on_quit)
        self._drag_session = None
        self._drag_context = None
        self._fade_pixmap = None   # 边缘羽化缓存,避免每次重绘都画 14 层矢量图形
        self._fade_key = None
        self._task_drag_scroll_timer = QTimer(self)
        self._fade_key = None
        self._task_drag_scroll_timer = QTimer(self)
        self._task_drag_scroll_timer.setInterval(40)
        self._task_drag_scroll_timer.timeout.connect(self._auto_scroll_task_drag)

        # 空闲自动贴边:鼠标离开窗口、或窗口切到后台,满 IDLE_COLLAPSE_MS
        # 后收起为贴边条(见 enter/leaveEvent 与 changeEvent)
        self._edge_dock = None  # 懒建的 EdgeDock
        self._tray = None       # 懒建的 TrayIcon
        self._cursor_inside = False   # 鼠标当前是否停留在窗口上
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(IDLE_COLLAPSE_MS)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        # 兜底自检:偶发情况下主窗口收起后贴边条没露出来(被窗口管理器跟着
        # 隐藏、或滑入动画被打断停在屏幕外),桌面上就什么都看不到了
        self._dock_watchdog = QTimer(self)
        self._dock_watchdog.setInterval(DOCK_WATCHDOG_MS)
        self._dock_watchdog.timeout.connect(self._watch_dock)
        self._dock_watchdog.start()

        self.setWindowTitle(app_name())
        self.setFont(QFont(self.theme.font_family, 10))
        # 仅无边框;置顶不用 Qt 标志而用原生 API(showEvent),
        # 避免 Qt 标志残留与原生层级不一致导致置顶无法取消
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(MIN_W, MIN_H)
        self.setMouseTracking(True)
        self.resize(320, 460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 9, 9, 9)

        self.container = QFrame()
        self.container.setObjectName("container")
        self.container.setStyleSheet(build_qss(self.theme))
        # 容器内固定箭头光标,避免被窗口边缘的 resize 光标继承
        self.container.setCursor(QCursor(Qt.ArrowCursor))
        outer.addWidget(self.container)

        v = QVBoxLayout(self.container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ---- 标题栏(加号 + 锁头横向排列;空白处可拖动窗口,右键退出/解锁)----
        self.header = HeaderBar(self)
        # 图钉按钮初始状态跟随持久化设置
        self.header.pin_btn.set_pinned(self.settings.always_on_top)
        v.addWidget(self.header)

        # ---- 顶部分隔线 ----
        self.top_sep = QFrame()
        self.top_sep.setObjectName("sectionSep")
        self.top_sep.setFrameShape(QFrame.NoFrame)
        self.top_sep.setFixedHeight(1)
        v.addWidget(self.top_sep)

        # ---- 任务列表(可滚动)----
        self.scroll = QScrollArea()
        self.scroll.setObjectName("listScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget = QWidget()
        self.list_widget.setObjectName("listWidget")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 5, 0, 5)
        self.list_layout.setSpacing(2)
        self.list_layout.setAlignment(Qt.AlignTop)

        # ---- 新建分组:放在所有分组之后 ----
        self._new_group_btn = QPushButton(t("main.new_group"))
        self._new_group_btn.setObjectName("newGroupBtn")
        self._new_group_btn.setIconSize(QSize(16, 16))
        self._new_group_btn.setIcon(svg_icon("add", self.theme.icon_color, 16))
        self._new_group_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._new_group_btn.setFocusPolicy(Qt.NoFocus)
        self._new_group_btn.clicked.connect(self.add_group)
        self.list_layout.addWidget(self._new_group_btn)

        # ---- 空列表引导提示(紧跟加号之后;不占用任务的索引空间)----
        self._empty_hint = QLabel(t("main.empty_hint"))
        self._empty_hint.setObjectName("emptyHint")
        self._empty_hint.setVisible(False)
        self.list_layout.addWidget(self._empty_hint)

        self.list_layout.addStretch()  # 末尾占位,任务顶对齐
        self.scroll.setWidget(self.list_widget)
        v.addWidget(self.scroll, 1)

        # ---- 底部:已完成按钮 + 设置齿轮(最右) ----
        self.footer_bar = QFrame()
        self.footer_bar.setObjectName("footerBar")
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(10, 4, 9, 4)
        footer_layout.setSpacing(0)

        footer_layout.addStretch(1)

        self.settings_btn = QPushButton()
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.settings_btn.setFocusPolicy(Qt.NoFocus)
        self.settings_btn.setToolTip(t("main.settings_tooltip"))
        self.settings_btn.setIcon(svg_icon("settings", self.theme.icon_color, 16))
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.clicked.connect(self.open_settings)
        footer_layout.addWidget(self.settings_btn)

        v.addWidget(self.footer_bar)

        self.load_tasks()
        self._restore_window_geometry()
        # 托盘图标常驻:窗口收起成贴边条后,通知区域里仍能找回并退出程序
        self._ensure_tray()

        self._new_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self._new_shortcut.activated.connect(self.add_task)
        self._lock_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self._lock_shortcut.activated.connect(self.toggle_locked)

        # 让边缘缩放对"可见深色块边缘"生效:给容器及所有子控件开鼠标追踪 + 事件过滤
        self._install_edge_watch(self.container)
        self._edge_watch_ready = True

    # ---- 边缘缩放:让 container 及子控件把鼠标事件转给窗口做边缘检测 ----
    def _watch_widget(self, w):
        w.setMouseTracking(True)
        w.installEventFilter(self)
        for c in w.findChildren(QWidget):
            c.setMouseTracking(True)
            c.installEventFilter(self)

    def _install_edge_watch(self, root):
        self._watch_widget(root)

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = self.mapFromGlobal(event.globalPosition().toPoint())
            direction = self._edge(pos)
            if direction is not None:
                # 角落区域与 footer 按钮重叠时,优先让按钮处理点击;
                # 边(非角)仍照常启动缩放。
                corners = ("topleft", "topright", "bottomleft", "bottomright")
                if isinstance(obj, QAbstractButton) and direction in corners:
                    return False
                self._resize_dir = direction
                self._resize_start_geo = self.frameGeometry()
                self._resize_origin = event.globalPosition().toPoint()
                return True  # 消费,防止子控件把它当普通点击
        elif et == QEvent.MouseMove:
            if self._resize_dir is not None and (event.buttons() & Qt.LeftButton):
                self._do_resize(event.globalPosition().toPoint())
                return True
            if not event.buttons():
                pos = self.mapFromGlobal(event.globalPosition().toPoint())
                direction = self._edge(pos)
                self._apply_edge_cursor(direction)
        elif et == QEvent.MouseButtonRelease:
            if self._resize_dir is not None:
                self._resize_dir = None
                self._resize_start_geo = None
                self._resize_origin = None
                self._apply_edge_cursor(None)
                return True
        return super().eventFilter(obj, event)

    # ---- 边缘虚化(缓存成位图,避免每次重绘都画 14 层矢量图形)----
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() <= 0 or self.height() <= 0:
            return
        p = QPainter(self)
        p.drawPixmap(0, 0, self._edge_fade_pixmap())
        p.end()

    def _screen_dpr(self):
        """窗口所在屏幕的设备像素比(副屏高DPI下图标不糊)。"""
        try:
            screen = (
                QApplication.screenAt(self.frameGeometry().center())
                or QApplication.primaryScreen()
            )
            return (screen.devicePixelRatio() if screen else None) or 1.0
        except Exception:
            return 1.0

    def _edge_fade_pixmap(self):
        """返回当前尺寸+主题下的羽化位图,命中缓存时直接复用。"""
        key = (self.width(), self.height(), id(self.theme))
        if self._fade_pixmap is not None and self._fade_key == key:
            return self._fade_pixmap
        dpr = self._screen_dpr()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        self._paint_edge_fade(p)
        p.end()
        self._fade_pixmap = pm
        self._fade_key = key
        return pm

    def _paint_edge_fade(self, p):
        """容器边缘向外逐渐虚化(羽化),替代硬阴影。

        从容器边缘向外画多层同心圆角矩形的"环带"(外扩矩形减去容器矩形),
        越往外 alpha 越低,形成背景色→透明的柔和过渡。
        环带画法保证容器内部不被叠加任何颜色,透明度与滑杆值一致。
        """
        cr = QRectF(self.container.geometry())
        radius = 16.0
        fade = 8.0       # 虚化区域宽度(匹配外边距)
        layers = 14
        base = self.theme.edge_fade_color
        # 羽化强度随背景透明度等比缩放:低透明度时不再残留一圈可见薄雾
        fade_strength = self.theme.bg_opacity / 255.0
        p.setPen(Qt.NoPen)
        inner = QPainterPath()
        inner.addRoundedRect(cr, radius, radius)
        for i in range(layers, 0, -1):
            expand = fade * i / layers
            # 越贴近容器边缘越不透明,最外层趋近全透明
            alpha = int(56 * fade_strength * (1.0 - (i - 1) / layers))
            rect = cr.adjusted(-expand, -expand, expand, expand)
            r = radius + expand
            ring = QPainterPath()
            ring.addRoundedRect(rect, r, r)
            p.setBrush(QColor(base.red(), base.green(), base.blue(), alpha))
            p.drawPath(ring.subtracted(inner))  # 只画容器外的那圈环

    # ---- 分组列表加载与局部刷新 ----
    def _update_empty_hint(self):
        self._empty_hint.setVisible(not self.store.active_tasks())

    def load_tasks(self):
        empty_ids = [task.id for task in self.store.active_tasks() if not task.text.strip()]
        if empty_ids:
            self.store.permanent_delete(empty_ids)
        self._rebuild_groups()

    def _clear_group_widgets(self):
        for widget in self._group_widgets.values():
            self.list_layout.removeWidget(widget)
            widget.deleteLater()
        self._group_widgets.clear()

    def _rebuild_groups(self):
        self._cancel_active_drag()
        self._clear_group_widgets()
        for group in self.store.groups():
            widget = TaskGroupWidget(
                group,
                self.store.active_tasks(group.id),
                self.store.completed_tasks(group.id),
                self.store.deferred_tasks(group.id),
                parent=self.list_widget,
            )
            self._connect_group_widget(widget)
            position = self.list_layout.indexOf(self._new_group_btn)
            self.list_layout.insertWidget(position, widget)
            self._group_widgets[group.id] = widget
            widget.show()
            self._watch_widget(widget)
            widget.set_theme(self.theme)
            widget.set_locked(self._locked)
            widget.set_text_hidden(self._text_hidden)
        self._update_empty_hint()

    def _connect_group_widget(self, widget):
        widget.add_requested.connect(self.add_task)
        widget.rename_requested.connect(self.rename_group)
        widget.delete_requested.connect(self.delete_group)
        widget.group_drag_started.connect(self._on_group_drag_started)
        widget.group_drag_moved.connect(self._on_group_drag_moved)
        widget.group_drag_finished.connect(self._on_group_drag_finished)
        widget.task_completed.connect(self.on_complete)
        widget.task_deferred.connect(self.on_defer)
        widget.task_changed.connect(self.on_text_changed)
        widget.task_deleted.connect(self.on_delete)
        widget.task_restored.connect(self.on_restore)
        widget.task_completed_deleted.connect(self.on_delete)
        widget.task_drag_started.connect(self._on_group_task_drag_started)
        widget.task_drag_moved.connect(self._on_group_task_drag_moved)
        widget.task_drag_finished.connect(self._on_group_task_drag_finished)
        widget.completed_toggled.connect(self._on_completed_toggled)
        widget.deferred_toggled.connect(self._on_deferred_toggled)
        widget.group_toggled.connect(self._on_group_toggled)

    def _refresh_group(self, group_id):
        widget = self._group_widgets.get(group_id)
        group = self.store.get_group(group_id)
        if widget is None or group is None or group.deleted:
            self._rebuild_groups()
            return
        widget.group = group
        widget.header.group = group
        widget.refresh(
            self.store.active_tasks(group_id),
            self.store.completed_tasks(group_id),
            self.store.deferred_tasks(group_id),
        )
        widget.set_theme(self.theme)
        widget.set_locked(self._locked)
        widget.set_text_hidden(self._text_hidden)
        self._update_empty_hint()

    def _fade_in(self, item):
        effect = QGraphicsOpacityEffect(item)
        effect.setOpacity(0)
        item.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: item.setGraphicsEffect(None))
        item._fade_anim = anim
        anim.start()

    # ---- 分组和任务操作 ----
    def add_group(self):
        if self._locked:
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, t("group.new_title"), t("group.name_label"),
        )
        if ok and name.strip():
            self.store.create_group(name)
            self._rebuild_groups()

    def rename_group(self, group_id):
        from PySide6.QtWidgets import QInputDialog
        group = self.store.get_group(group_id)
        if group is None:
            return
        name, ok = QInputDialog.getText(
            self, t("group.rename_title"), t("group.name_label"), text=group.name,
        )
        if ok and name.strip():
            self.store.rename_group(group_id, name)
            self._rebuild_groups()

    def delete_group(self, group_id):
        group = self.store.get_group(group_id)
        if group is None:
            return
        count = self.store.group_task_count(group_id, include_deleted=True)
        answer = dialogs.question(
            self, t("group.delete"),
            t("group.delete_confirm", name=group.name, count=count),
        )
        if answer == QMessageBox.Yes:
            self.store.delete_group(group_id)
            self._rebuild_groups()

    def add_task(self, group_id=None):
        if self._locked:
            return
        if group_id is None:
            groups = self.store.groups()
            if not groups:
                group = self.store.create_group("Default")
                group_id = group.id
            else:
                group_id = groups[0].id
        group = self.store.get_group(group_id)
        if group is not None and not group.is_expanded:
            # 折叠状态下新增任务会让内容不可见，自动展开该分组。
            self.store.set_group_expanded(group_id, True)
        task = self.store.add(group_id, "")
        self._refresh_group(group_id)
        item = self._group_widgets[group_id]._active_items.get(task.id)
        if item is not None:
            item.start_edit()
            # 布局/行高在下一轮事件循环才最终确定,延后滚动才能完整露出输入行。
            QTimer.singleShot(0, lambda: self._scroll_to_item(item))

    def _scroll_to_item(self, item):
        """把任务行滚动到可视区域(分组可能刚重建,控件已销毁时静默跳过)。"""
        try:
            if item is None or not item.isVisible():
                return
            self.scroll.ensureWidgetVisible(item, 0, 16)
        except RuntimeError:
            pass

    def on_complete(self, task_id):
        self._set_task_state(task_id, self.store.complete)

    def on_defer(self, task_id):
        self._set_task_state(task_id, self.store.defer)

    def _set_task_state(self, task_id, setter):
        task = self.store.get(task_id)
        if task is None:
            return
        if not task.text.strip():
            self.on_delete(task_id, permanent=True)
            return
        setter(task_id)
        self._refresh_group(task.group_id)

    def on_restore(self, task_id):
        task = self.store.restore(task_id)
        if task is not None:
            self._rebuild_groups()

    def on_text_changed(self, task_id, text):
        task = self.store.update_text(task_id, text)
        if task is not None:
            self._refresh_group(task.group_id)

    def on_delete(self, task_id, permanent=False):
        task = self.store.get(task_id)
        if task is None:
            return
        if not task.text.strip():
            permanent = True
        group_id = task.group_id
        removed = self.store.permanent_delete([task_id]) if permanent else [self.store.delete(task_id)]
        if removed and removed[0] is not None:
            self._refresh_group(group_id)

    def _on_group_toggled(self, group_id, expanded):
        self.store.set_group_expanded(group_id, expanded)

    def _on_completed_toggled(self, group_id, expanded):
        self.store.set_completed_expanded(group_id, expanded)

    def _on_deferred_toggled(self, group_id, expanded):
        self.store.set_deferred_expanded(group_id, expanded)

    # ---- 实时浮层拖动排序 ----
    def _start_drag_session(self, kind, group_id, widget, layout, global_pos, items):
        self._cancel_active_drag()
        self._drag_context = {
            "kind": kind,
            "group_id": group_id,
            "task_id": getattr(getattr(widget, "task", None), "id", None),
            "items": items,
            "original_ids": [getattr(getattr(item, "task", None), "id", getattr(item, "group", None).id if hasattr(getattr(item, "group", None), "id") else None) for item in items],
        }
        self._drag_session = DragSession(
            widget, layout, self.list_widget, global_pos,
            self.theme.accent_color, lambda: items,
            background=self._drag_snapshot_background(),
        )
        self._task_drag_global_pos = global_pos
        self._task_drag_scroll_timer.start()

    def _drag_snapshot_background(self):
        """浮层铺底色:与容器实际呈现的背景一致(含透明度合成)。"""
        bg = self.theme.bg_color
        return QColor(bg.red(), bg.green(), bg.blue(), self.theme.bg_opacity)

    def _on_group_drag_started(self, group_id, global_pos):
        if self._locked or group_id not in self._group_widgets:
            return
        widget = self._group_widgets[group_id]
        items = [
            self.list_layout.itemAt(index).widget()
            for index in range(self.list_layout.count())
            if isinstance(self.list_layout.itemAt(index).widget(), TaskGroupWidget)
        ]
        self._start_drag_session("group", group_id, widget, self.list_layout, global_pos, items)

    def _on_group_drag_moved(self, group_id, global_pos):
        if not self._drag_context or self._drag_context["group_id"] != group_id:
            return
        self._task_drag_global_pos = global_pos
        items = self._drag_context["items"]
        others = [item for item in items if item is not self._drag_session.widget]
        pointer_y = self.list_widget.mapFromGlobal(global_pos).y()
        target = len(others)
        for index, item in enumerate(others):
            if pointer_y < item.geometry().center().y():
                target = index
                break
        self._drag_session.move(global_pos, target)

    def _on_group_drag_finished(self, group_id):
        if not self._drag_context or self._drag_context["group_id"] != group_id:
            return
        context = self._drag_context
        session = self._drag_session
        self._task_drag_scroll_timer.stop()
        session.finish()
        ordered = [
            self.list_layout.itemAt(index).widget().group.id
            for index in range(self.list_layout.count())
            if isinstance(self.list_layout.itemAt(index).widget(), TaskGroupWidget)
        ]
        if ordered != context["original_ids"]:
            self.store.reorder_groups(ordered)
            self._group_widgets = {gid: self._group_widgets[gid] for gid in ordered}
        self._drag_session = None
        self._drag_context = None
        self._task_drag_global_pos = None

    def _on_group_task_drag_started(self, group_id, task_id, global_pos):
        if self._locked:
            return
        group_widget = self._group_widgets.get(group_id)
        if group_widget is None:
            return
        widget = group_widget._active_items.get(task_id)
        if widget is None:
            return
        items = group_widget.ordered_task_items()
        self._start_drag_session("task", group_id, widget, group_widget.active_layout, global_pos, items)
        self._drag_context["task_id"] = task_id

    def _on_group_task_drag_moved(self, group_id, task_id, global_pos):
        if (
            not self._drag_context
            or self._drag_context["kind"] != "task"
            or self._drag_context["group_id"] != group_id
            or self._drag_context["task_id"] != task_id
        ):
            return
        self._task_drag_global_pos = global_pos
        group_widget = self._group_widgets[group_id]
        items = self._drag_context["items"]
        others = [item for item in items if item is not self._drag_session.widget]
        pointer_y = group_widget.active_body.mapFromGlobal(global_pos).y()
        target = len(others)
        for index, item in enumerate(others):
            if pointer_y < item.geometry().center().y():
                target = index
                break
        self._drag_session.move(global_pos, target)

    def _on_group_task_drag_finished(self, group_id, task_id):
        if (
            not self._drag_context
            or self._drag_context["kind"] != "task"
            or self._drag_context["group_id"] != group_id
            or self._drag_context["task_id"] != task_id
        ):
            return
        context = self._drag_context
        self._task_drag_scroll_timer.stop()
        self._drag_session.finish()
        ordered = [item.task.id for item in context["items"] if item is not self._drag_session.widget]
        # The session's widget is restored into the layout; derive the final
        # order from the layout rather than from the stale snapshot list.
        group_widget = self._group_widgets[group_id]
        ordered = [item.task.id for item in group_widget.ordered_task_items()]
        if ordered != context["original_ids"]:
            self.store.reorder_active(group_id, ordered)
        self._drag_session = None
        self._drag_context = None
        self._task_drag_global_pos = None

    def _auto_scroll_task_drag(self):
        if self._drag_session is None or self._task_drag_global_pos is None:
            self._task_drag_scroll_timer.stop()
            return
        pos = self._task_drag_global_pos
        viewport = self.scroll.viewport()
        local = viewport.mapFromGlobal(pos)
        delta = -12 if local.y() < 28 else 12 if local.y() > viewport.height() - 28 else 0
        if delta:
            bar = self.scroll.verticalScrollBar()
            old = bar.value()
            bar.setValue(old + delta)
            if bar.value() != old:
                if self._drag_context["kind"] == "group":
                    self._on_group_drag_moved(self._drag_context["group_id"], pos)
                else:
                    self._on_group_task_drag_moved(
                        self._drag_context["group_id"], self._drag_context["task_id"], pos,
                    )

    def _cancel_active_drag(self):
        if self._drag_session is not None:
            self._drag_session.cancel()
        self._drag_session = None
        self._drag_context = None
        self._task_drag_global_pos = None
        self._task_drag_scroll_timer.stop()

    # ---- 屏幕边界辅助 ----
    def _keep_expanded_panel_on_screen(self):
        return

    def _restore_window_geometry(self):
        width = self.settings.window_width or 320
        height = self.settings.window_height or 460
        x = self.settings.window_x
        y = self.settings.window_y
        if x is None or y is None:
            self.resize(width, height)
            return
        primary = QApplication.primaryScreen()
        target = next(
            (screen for screen in QApplication.screens()
             if screen.availableGeometry().contains(x, y)),
            primary,
        )
        if target is None:
            self.setGeometry(x, y, width, height)
            return
        available = target.availableGeometry()
        width = min(max(MIN_W, width), available.width())
        height = min(max(MIN_H, height), available.height())
        x = min(max(x, available.left()), available.right() - width + 1)
        y = min(max(y, available.top()), available.bottom() - height + 1)
        self.setGeometry(x, y, width, height)

    # ---- 设置 ----
    def open_settings(self):
        win = getattr(self, "_settings_win", None)
        if win is not None:
            # 窗口已存在(可能只是被关闭隐藏),直接显示
            win.refresh_archive()
            win.set_text_hidden(self._text_hidden)
            win.show()
            win.raise_()
            win.activateWindow()
            return
        # 注意: parent=None —— 设置窗口是独立顶级窗口,与主窗口平级。
        # 如果传 parent=self,在 Windows 下会被主窗口的窗口标志影响,
        # 导致系统"设置"图标 / 标题栏重新出现,自定义顶栏前会有重复的灰底栏。
        win = SettingsWindow(self.settings, self.store, parent=None)
        win.changed.connect(self._on_settings_changed)
        win.archive_changed.connect(self._reload_task_views)
        win.set_text_hidden(self._text_hidden)
        self._settings_win = win
        win.show()

    def open_history(self):
        """兼容原入口：打开设置窗口并定位到归档数据页。"""
        self.open_settings()
        self._settings_win.show_archive_page()

    def _reload_task_views(self):
        self._rebuild_groups()

    # ---- 托盘图标 ----
    def _ensure_tray(self):
        """创建托盘图标(程序运行期间常驻通知区域)。"""
        if self._tray is None:
            self._tray = TrayIcon(self, parent=self)
            self._tray.show()
        return self._tray

    def summon(self):
        """把主窗口唤到前台(贴边条点击与托盘菜单共用)。"""
        if self.isMinimized():
            self.showNormal()
        self._summon_from_dock()

    def start_collapsed(self):
        """开机自启动:不弹主窗口,直接以贴边条形态出现在屏幕边缘。

        用户关掉了自动贴边时退回普通显示——否则会"启动后立刻消失",
        让人以为程序根本没起来。
        """
        if not self.settings.auto_dock_enabled:
            self.show()
            return
        geo = self._dock_screen_geometry()
        if geo is None:
            self.show()
            return
        self._place_dock(geo)
        # 只留贴边条:即使主窗口先前已被显示过,这里也一并收起来
        self.hide()

    # ---- 空闲自动贴边(贴边条 ⇄ 悬停胶囊) ----
    def _ensure_dock(self):
        if self._edge_dock is None:
            dock = EdgeDock()
            dock.summoned.connect(self._summon_from_dock)
            dock.moved.connect(self._on_dock_moved)
            dock.edge_changed.connect(self._on_dock_edge_changed)
            dock.set_theme(self.theme)
            self._edge_dock = dock
        return self._edge_dock

    def _is_editing(self):
        """任何任务处于编辑态(编辑框展开)时不收起。"""
        for widget in self._group_widgets.values():
            for item in widget._active_items.values():
                if item.stack.currentIndex() == item._EDIT_PAGE:
                    return True
        return False

    def _can_collapse(self):
        """当前是否允许收起为贴边条。"""
        if not self.settings.auto_dock_enabled:
            return False
        if self._always_on_top:
            return False  # 置顶时不自动收起
        if not self.isVisible() or self.isMinimized():
            return False  # 已收起或已最小化
        if self._drag_session is not None or self._is_editing():
            return False
        if QApplication.activeModalWidget() is not None:
            return False
        if QApplication.activePopupWidget() is not None:
            return False  # 右键菜单等弹出层展开时
        win = getattr(self, "_settings_win", None)
        if win is not None and win.isVisible():
            return False
        return True

    def _on_idle_timeout(self):
        if self.isActiveWindow() and self._cursor_inside:
            return  # 用户已经回来(窗口在前台且鼠标停在上面),这次不收
        if self._can_collapse():
            self._collapse_to_dock()
            return
        # 条件暂时不满足(编辑中/弹窗打开/拖动会话/设置窗口开着)时重排一次:
        # 否则条件解除后不会再有事件来触发收起,表现为"有时候不会变"
        if self.settings.auto_dock_enabled and self.isVisible() and not self.isMinimized():
            self._idle_timer.start()

    def _collapse_to_dock(self):
        if not self._can_collapse():
            return
        geo = self._dock_screen_geometry()
        if geo is None:
            return
        self._place_dock(geo)
        self.setWindowOpacity(1.0)  # 万一淡入动画被打断,别留着 0 透明的窗口
        self.hide()
        # 主窗口一消失,个别情况下贴边条会被窗口管理器"跟着"隐藏,或滑入
        # 动画被打断停在屏幕外,形成"主窗口和贴边条都没了"的假死观感。
        self._ensure_dock_reachable()

    def _dock_screen_geometry(self):
        """贴边条该出现的屏幕可用区域(跟随主窗口所在屏幕)。"""
        screen = (
            QApplication.screenAt(self.frameGeometry().center())
            or QApplication.primaryScreen()
        )
        return screen.availableGeometry() if screen is not None else None

    def _place_dock(self, geo):
        """把贴边条摆到屏幕边缘并显示出来。"""
        center = self.frameGeometry().center()
        # 用户拖动过贴边条(dock_y 已持久化)时沿用其停靠边,否则按窗口位置就近
        if self.settings.dock_y is None:
            edge = "left" if center.x() < geo.center().x() else "right"
        else:
            edge = self.settings.dock_edge
        self.settings.dock_edge = edge
        y = self.settings.dock_y
        if y is None:
            y = center.y() - BAR_H // 2
        count = len(self.store.active_tasks())
        self._ensure_dock().show_bar(edge, y, count, geo)

    def _dock_reachable(self, dock):
        """贴边条是否真的摆在用户看得见的地方(可见且与某块屏幕有交集)。"""
        if dock is None or not dock.isVisible():
            return False
        rect = dock.frameGeometry()
        return any(
            screen.availableGeometry().intersects(rect)
            for screen in QApplication.screens()
        )

    def _ensure_dock_reachable(self, check_position=False):
        """确保贴边条能被看到;看不到就重新摆一遍。

        check_position=True 时连"是否落在屏幕内"一起校验,只在滑入动画
        早已结束的自检里用——收起瞬间窗口还在屏幕外往内滑,会误判。
        """
        dock = self._edge_dock
        if check_position:
            ok = self._dock_reachable(dock)
        else:
            ok = dock is not None and dock.isVisible()
        if ok:
            return
        geo = self._dock_screen_geometry()
        if geo is not None:
            self._place_dock(geo)
        dock = self._edge_dock
        if dock is not None and not dock.isVisible():
            dock.show()
            dock.raise_()

    def _watch_dock(self):
        """兜底自检:主窗口已收起、自动贴边开着,却看不到贴边条时找回来。"""
        if self.isVisible() or not self.settings.auto_dock_enabled:
            return
        self._ensure_dock_reachable(check_position=True)

    def _summon_from_dock(self):
        self._idle_timer.stop()
        if self._edge_dock is not None:
            self._edge_dock.hide()
        self.setWindowOpacity(0.0)
        self.show()
        self._apply_topmost_native(self._always_on_top)
        self.raise_()
        self.activateWindow()
        # 淡入过渡:窗口从透明渐显
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(170)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self.setWindowOpacity(1.0))
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._summon_anim = anim

    def _on_dock_moved(self, y):
        self.settings.dock_y = int(y)
        self._settings_dirty = True
        self._settings_save_timer.start()

    def _on_dock_edge_changed(self, edge):
        """贴边条被拖到另一侧:记住新的停靠边。"""
        if edge in ("left", "right"):
            self.settings.dock_edge = edge
        self._settings_dirty = True
        self._settings_save_timer.start()

    def set_auto_dock_enabled(self, enabled):
        self.settings.auto_dock_enabled = bool(enabled)
        if enabled:
            self._idle_timer.start()   # 打开开关后立即开始倒计时
        else:
            self._idle_timer.stop()
        self._settings_dirty = True
        self._settings_save_timer.start()


    def _on_settings_changed(self):
        """设置变动立即预览，短时间内的连续磁盘写入合并保存。"""
        self.apply_theme()
        self._settings_dirty = True
        self._settings_save_timer.start()

    def _snapshot_geometry(self):
        """把当前窗口位置/大小写入 settings。"""
        self.settings.window_x = self.x()
        self.settings.window_y = self.y()
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()

    def _flush_settings_save(self):
        if not self._settings_dirty:
            return
        self._settings_save_timer.stop()
        self.settings.save(self._settings_path)
        self._settings_dirty = False

    def _save_settings_on_quit(self):
        """退出前强制保存一次。

        菜单"退出"走 QApplication.quit(),不触发 closeEvent,
        若只依赖 closeEvent,窗口位置/大小会丢失。
        """
        self._snapshot_geometry()
        self._settings_dirty = True
        self._flush_settings_save()

    def apply_theme(self):
        """重新从 settings 生成主题并刷新所有 UI。"""
        self.theme = self.settings.to_theme()
        t = self.theme
        # 容器 QSS
        self.container.setStyleSheet(build_qss(t))
        # 全局字体
        self.setFont(QFont(t.font_family, 10))
        # 锁头
        self.header.lock_btn.set_theme(t)
        # 图钉与眼睛
        self.header.pin_btn.set_theme(t)
        self.header.eye_btn.set_theme(t)
        # 设置与新建分组图标
        self.settings_btn.setIcon(svg_icon("settings", t.icon_color, 16))
        self._new_group_btn.setIcon(svg_icon("add", t.icon_color, 16))
        # 分组与任务项
        for widget in self._group_widgets.values():
            widget.set_theme(t)

        # 贴边条 / 悬停胶囊
        if self._edge_dock is not None:
            self._edge_dock.set_theme(t)

        settings_win = getattr(self, "_settings_win", None)
        if settings_win is not None:
            settings_win.refresh_theme()

        # 主题变了,羽化缓存失效
        self._fade_pixmap = None
        self._fade_key = None
        # 边缘虚化重画
        self.update()

    # ---- 锁定/解锁 ----
    def set_locked(self, locked):
        self._cancel_active_drag()
        self._locked = locked
        # 锁头位置固定在右上角;锁上时先显示,鼠标移出窗口再隐藏(见 leaveEvent)
        self.header.lock_btn.set_locked(locked)
        for btn in self._header_icon_btns():
            btn.setVisible(True)
        self._new_group_btn.setVisible(not locked)
        self.footer_bar.setVisible(not locked)
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if locked else Qt.ScrollBarAsNeeded,
        )
        for widget in self._group_widgets.values():
            widget.set_locked(locked)

    def unlock(self):
        self.set_locked(False)

    def toggle_locked(self):
        self.set_locked(not self._locked)

    def _header_icon_btns(self):
        """顶部栏右侧图标按钮组(锁定态下随鼠标进出统一显隐)。"""
        return (self.header.pin_btn, self.header.eye_btn, self.header.lock_btn)

    # ---- 图钉置顶 ----
    def _apply_topmost_native(self, pinned):
        """Windows 原生改 z-order(不重建窗口、不闪烁)。不可用时返回 False。"""
        if _user32 is None or not self.isVisible():
            return False
        HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
        SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
        return bool(_user32.SetWindowPos(
            int(self.winId()),
            HWND_TOPMOST if pinned else HWND_NOTOPMOST,
            0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
        ))

    def showEvent(self, event):
        """每次窗口(重)显示后按当前置顶设置校正层级。

        覆盖最小化还原、隐藏重显等场景,避免状态丢失或残留。
        """
        super().showEvent(event)
        self._apply_topmost_native(self._always_on_top)

    def set_always_on_top(self, pinned):
        """切换窗口置顶;状态写入 settings 跨重启保持。

        Windows 上直接走原生 SetWindowPos 改 z-order,避免
        setWindowFlags 重建窗口导致的整界面闪烁;非 Windows 退回重建方式。
        """
        self.settings.always_on_top = pinned
        self._always_on_top = pinned
        self.header.pin_btn.set_pinned(pinned)
        if not self._apply_topmost_native(pinned):
            # 非 Windows(或窗口尚未显示):重建窗口标志兼容
            flags = Qt.FramelessWindowHint
            if pinned:
                flags |= Qt.WindowStaysOnTopHint
            was_visible = self.isVisible()
            geo = self.geometry()
            self.setWindowFlags(flags)
            self.setGeometry(geo)
            if was_visible:
                self.show()
        self._settings_dirty = True
        self._settings_save_timer.start()

    # ---- 隐藏任务文本(隐私模式) ----
    def set_text_hidden(self, hidden):
        """全视图同步掩码：主列表和设置中的归档数据。"""
        self._text_hidden = hidden
        self.header.eye_btn.set_hidden(hidden)
        for widget in self._group_widgets.values():
            widget.set_text_hidden(hidden)
        win = getattr(self, "_settings_win", None)
        if win is not None:
            win.set_text_hidden(hidden)

    def toggle_text_hidden(self):
        self.set_text_hidden(not self._text_hidden)

    def show_header_menu(self, global_pos):
        """上方栏右键菜单:退出/最小化/自动贴边(锁定态不弹,见 HeaderBar)。"""
        menu = QMenu(self)
        menu.addAction(t("main.menu_quit"), QApplication.quit)
        menu.addAction(t("main.menu_minimize"), self.showMinimized)
        dock_action = menu.addAction(t("main.menu_autodock"))
        dock_action.setCheckable(True)
        dock_action.setChecked(self.settings.auto_dock_enabled)
        dock_action.toggled.connect(self.set_auto_dock_enabled)
        menu.exec(global_pos)

    # ---- 边缘 8 方向 resize ----
    def _edge(self, pos):
        if self._locked:          # 锁定后不允许调整窗口大小
            return None
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        # 角:用更大的 CORNER 范围优先判定,便于命中对角缩放
        left_c = x < CORNER
        right_c = x > w - CORNER
        top_c = y < CORNER
        bottom_c = y > h - CORNER
        if top_c and left_c:
            return "topleft"
        if top_c and right_c:
            return "topright"
        if bottom_c and left_c:
            return "bottomleft"
        if bottom_c and right_c:
            return "bottomright"
        # 边:用较窄的 EDGE 范围
        if x < EDGE:
            return "left"
        if x > w - EDGE:
            return "right"
        if y < EDGE:
            return "top"
        if y > h - EDGE:
            return "bottom"
        return None

    def _apply_edge_cursor(self, direction):
        """用应用级 override 光标,确保能盖过 footer 等子控件自带的光标。"""
        if direction is not None:
            cur = QCursor(self._cursor_for(direction))
            if self._cursor_overriding:
                QApplication.changeOverrideCursor(cur)
            else:
                QApplication.setOverrideCursor(cur)
                self._cursor_overriding = True
        elif self._cursor_overriding:
            QApplication.restoreOverrideCursor()
            self._cursor_overriding = False

    def _cursor_for(self, direction):
        if direction in ("left", "right"):
            return Qt.SizeHorCursor
        if direction in ("top", "bottom"):
            return Qt.SizeVerCursor
        if direction in ("topleft", "bottomright"):
            return Qt.SizeFDiagCursor
        if direction in ("topright", "bottomleft"):
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def _do_resize(self, global_pos):
        g = self._resize_start_geo
        dx = global_pos.x() - self._resize_origin.x()
        dy = global_pos.y() - self._resize_origin.y()
        d = self._resize_dir
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        if "left" in d:
            new_w = max(MIN_W, w - dx)
            x = g.x() + (w - new_w)
            w = new_w
        if "right" in d:
            w = max(MIN_W, w + dx)
        if "top" in d:
            new_h = max(MIN_H, h - dy)
            y = g.y() + (h - new_h)
            h = new_h
        if "bottom" in d:
            h = max(MIN_H, h + dy)
        self.setGeometry(x, y, w, h)

    def closeEvent(self, event):
        """主窗口关闭时同步关闭独立设置窗口并清理全局光标。"""
        self._cancel_active_drag()
        self._idle_timer.stop()
        self._dock_watchdog.stop()
        if self._tray is not None:
            self._tray.hide()  # 退出前收掉图标,免得通知区域留下残影
        if self._edge_dock is not None:
            self._edge_dock.close()  # 无父顶层窗口,需显式关闭
        win = getattr(self, "_settings_win", None)
        if win is not None:
            win.close()
        self._snapshot_geometry()
        self._settings_dirty = True
        self._flush_settings_save()
        self._apply_edge_cursor(None)
        super().closeEvent(event)

    def keyPressEvent(self, event):
        self._idle_timer.stop()
        if event.key() == Qt.Key_Escape and self._drag_session is not None:
            self._cancel_active_drag()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self._cancel_active_drag()
        super().focusOutEvent(event)

    def changeEvent(self, event):
        """窗口在前台/后台间切换:切到后台满 IDLE_COLLAPSE_MS 后收起。

        只靠鼠标 leaveEvent 判定会漏掉"鼠标还在窗口上、但人已经切到别的
        应用"的情况——那时窗口已失去焦点却收不起来。
        """
        if event.type() == QEvent.ActivationChange:
            if self.isActiveWindow():
                self._idle_timer.stop()      # 回到前台,取消收起倒计时
            elif self.settings.auto_dock_enabled:
                self._idle_timer.start()     # 切到后台,开始倒计时
        super().changeEvent(event)

    # ---- 拖动窗口(点空白区域拖动) + 边缘 resize----
    def mousePressEvent(self, event):
        self._idle_timer.stop()
        if event.button() == Qt.LeftButton:
            direction = self._edge(event.position())
            if direction is not None:
                self._resize_dir = direction
                self._resize_start_geo = self.frameGeometry()
                self._resize_origin = event.globalPosition().toPoint()
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._resize_dir is not None and (event.buttons() & Qt.LeftButton):
            self._do_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        # 无按键:按是否在边缘更新光标
        if not event.buttons():
            direction = self._edge(event.position())
            self._apply_edge_cursor(direction)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_dir = None
        self._resize_start_geo = None
        self._resize_origin = None
        self._apply_edge_cursor(None)

    # ---- 锁定态:鼠标移出窗口隐藏锁头,移入再显示 ----
    def enterEvent(self, event):
        super().enterEvent(event)
        self._cursor_inside = True
        self._idle_timer.stop()  # 鼠标回到窗口,取消收起倒计时
        if self._locked:
            for btn in self._header_icon_btns():
                btn.setVisible(True)


    def leaveEvent(self, event):
        super().leaveEvent(event)
        # 锁定时鼠标移出窗口即隐藏图标按钮(移入时 enterEvent 再显示)
        if self._locked:
            for btn in self._header_icon_btns():
                btn.setVisible(False)
        # 鼠标真正离开窗口且不在缩放中时,复位 resize 光标
        if self._resize_dir is None:
            self._apply_edge_cursor(None)
        # 鼠标离开窗口,开始空闲收起倒计时(超时后 _can_collapse 再作最终判断)
        self._cursor_inside = False
        if self.settings.auto_dock_enabled:
            self._idle_timer.start()

