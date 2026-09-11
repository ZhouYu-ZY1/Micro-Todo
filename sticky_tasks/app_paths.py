"""软件目录与本地数据文件路径。

用户数据存放在 %APPDATA%\\Micro Todo,与安装目录解耦:
安装/更新/卸载覆盖程序文件时不会碰到数据。
旧版数据(程序目录内的 .sticky_tasks,或旧的 %APPDATA%\\MyToDo)
在首次启动时一次性迁入。
"""

import os
import shutil
import sys
from pathlib import Path

APP_DIR_NAME = "Micro Todo"
DATABASE_NAME = "Micro Todo.db"
# 数据目录里的提示文件:文件名即提示语,内容为空
NOTICE_FILE_NAME = "请勿删除Micro Todo.db文件，否则清单数据会丢失.txt"
# 便携版数据目录(相对程序目录)与旧版数据目录(相对 %APPDATA%)
LEGACY_PORTABLE_DIR = ".sticky_tasks"
LEGACY_APP_DIR = "MyToDo"
# 旧数据文件名 -> 当前文件名
_LEGACY_FILES = {
    "mytodo.db": DATABASE_NAME,
    DATABASE_NAME: DATABASE_NAME,
    "tasks.json": "tasks.json",
    "settings.json": "settings.json",
}


def software_dir() -> Path:
    """返回源码入口或打包后可执行文件所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    """返回图形资源目录(icon.ico 与 icons/*.svg)。

    PyInstaller onedir 会把 datas 放进 exe 同级的 _internal 子目录,
    该目录正是 sys._MEIPASS;资源不在 software_dir() 下,所以必须在这里抹平,
    否则打包后所有图标都读不到文件而渲染成空白。
    源码态没有 _MEIPASS,直接用程序目录下的 assets/。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        packaged = Path(meipass) / "assets"
        if packaged.is_dir():
            return packaged
    return software_dir() / "assets"


def roaming_dir() -> Path:
    """返回 %APPDATA% 目录(缺失时回退到用户主目录)。"""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base)


def _legacy_data_dirs() -> tuple:
    """可能存放旧版数据的目录,按优先级排列。"""
    return (
        software_dir() / LEGACY_PORTABLE_DIR,
        roaming_dir() / LEGACY_APP_DIR,
    )


def _migrate_legacy_data(target: Path) -> None:
    """新数据目录为空且存在旧版数据时,复制数据库/tasks/settings 过来。

    只迁一次:目标目录已有任何文件即跳过;只复制不删除旧文件,
    失败静默(不影响启动,用户仍得到全新空数据)。
    """
    try:
        if any(target.iterdir()):
            return
    except FileNotFoundError:
        pass
    except OSError:
        return
    for legacy in _legacy_data_dirs():
        for old_name, new_name in _LEGACY_FILES.items():
            src = legacy / old_name
            if not src.is_file():
                continue
            try:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target / new_name)
            except OSError:
                pass


def data_dir() -> Path:
    """用户数据目录(%APPDATA%\\Micro Todo),取用时顺带做旧数据迁移。"""
    target = roaming_dir() / APP_DIR_NAME
    _migrate_legacy_data(target)
    return target


DATA_DIR = data_dir()
DATABASE_FILE = DATA_DIR / DATABASE_NAME
SETTINGS_FILE = DATA_DIR / "settings.json"


def ensure_data_notice() -> None:
    """在数据目录放置一个空的提示文件(文件名即提示)。

    提醒用户不要误删数据库;创建失败静默,不影响启动。
    """
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / NOTICE_FILE_NAME).touch(exist_ok=True)
    except OSError:
        pass

