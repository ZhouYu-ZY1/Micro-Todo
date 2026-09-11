"""系统托盘图标:主窗口收起成贴边条后,仍能在通知区域找回并退出程序。

Windows 默认把新图标折叠进通知区域的溢出面板(点任务栏的 ^ 展开),
用户在那里右键即可唤出窗口或退出,不必再去找屏幕边缘的贴边条。
"""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import app_name
from .app_paths import assets_dir
from .i18n import t

APP_ICON_NAME = "icon.ico"   # 与任务栏/exe 同一个图标


def _app_icon() -> QIcon:
    """托盘图标直接用 ico:它内含 16/32/48/256 多档,系统会挑合适的一帧,
    比缩放大图更清晰。文件缺失时返回空图标(托盘区显示空白,不崩)。"""
    path = assets_dir() / APP_ICON_NAME
    return QIcon(str(path)) if path.exists() else QIcon()


class TrayIcon(QSystemTrayIcon):
    """常驻通知区域的托盘图标,左键唤出窗口,右键弹出操作菜单。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setIcon(_app_icon())
        self.setToolTip(app_name())
        self.activated.connect(self._on_activated)
        self.setContextMenu(self._build_menu())

    def _build_menu(self) -> QMenu:
        # 菜单挂在主窗口上:窗口销毁时菜单一并释放,不留顶层孤儿
        menu = QMenu(self._window)
        menu.addAction(t("main.menu_open"), self._window.summon)

        dock_action = menu.addAction(t("main.menu_autodock"))
        dock_action.setCheckable(True)
        dock_action.setChecked(self._window.settings.auto_dock_enabled)
        dock_action.toggled.connect(self._window.set_auto_dock_enabled)
        # 勾选态与主窗口右键菜单里的同名项保持一致
        self._dock_action = dock_action

        menu.addSeparator()
        menu.addAction(t("main.menu_quit"), QApplication.quit)
        return menu

    def _on_activated(self, reason):
        # 右键交给 setContextMenu 的菜单处理,这里只接管左键
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._window.summon()
