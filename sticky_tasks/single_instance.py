"""单实例锁:防止多开程序导致两个实例互相覆盖数据文件。

除 QLockFile 的锁文件外,还持有一个 Windows 命名互斥体:安装程序
(Inno Setup 的 [Setup] AppMutex)在安装/卸载前会检测它,从而拦住
"程序还开着就卸载"——那种情况下 Qt 的插件 DLL 被进程占用删不掉,
卸载会剩下 _internal 的空目录。
互斥体名必须与 微清单.iss 的 AppMutex 保持一致,改名要两处同步。
"""

import ctypes
from pathlib import Path

from PySide6.QtCore import QLockFile

APP_MUTEX_NAME = "MicroTodo_SingleInstance_Mutex"


def _create_app_mutex():
    """创建命名互斥体并返回句柄;非 Windows 或失败时返回 None。

    句柄不显式释放:进程退出时系统自动关闭,互斥体随之销毁。
    它只是给安装程序看的"程序正在运行"信号,创建失败不影响单实例控制。
    """
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    try:
        return windll.kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
    except OSError:
        return None


class SingleInstance:
    """进程存活期间持有锁文件;进程退出(含崩溃)后锁自动释放。"""

    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(str(data_dir / "app.lock"))
        self._lock.setStaleLockTime(0)  # 崩溃残留锁由 QLockFile 自动识别清理
        self._mutex = None

    def try_acquire(self, timeout_ms: int = 0) -> bool:
        # 0 = 不等待,拿不到立即返回;重启场景传正值等待旧进程释放锁
        if not self._lock.tryLock(timeout_ms):
            return False
        self._mutex = _create_app_mutex()
        return True
