"""SVG 线性图标加载与主题着色。

高分屏(Windows 常见 125%/150%/200% 缩放)下,如果只生成 1x 位图,
系统会把整张图放大到物理像素,细线条就会发虚、发灰。这里按缩放率
直接渲染物理分辨率的位图,并给 QIcon 提供多档缩放版本,让 Qt 在各种
屏幕上都能取到足够清晰的位图。

另外 assets/icons 下的 SVG 统一是 24 的 viewBox、1.8 的描边:直接按
16px 渲染时描边只剩约 1.2 个逻辑像素,抗锯齿会把线条摊成一团灰,
看起来同样发虚。因此小尺寸下会自动加粗描边(光学补偿),保证线条
至少占约 1.8 个物理像素。
"""

import math
import re
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .app_paths import assets_dir

# QIcon 内置的缩放档位:覆盖 100%/150%/200%/300% 等常见缩放;
# 当前屏幕的缩放率(如 125%)始终会额外加进去,保证本机取到的是原尺寸位图,
# 换成别的缩放率的显示器时也能从邻近档位平滑缩小,而不是放大 1x 图。
ICON_SCALES = (1.0, 1.5, 2.0, 3.0)

VIEWBOX = 24          # assets/icons 下所有 SVG 的 viewBox 边长
BASE_STROKE = 1.8     # 这些 SVG 的基础描边宽度
MIN_STROKE_PX = 1.8   # 线条至少要占的物理像素,低于它抗锯齿会把线摊灰

_STROKE_RE = re.compile(r'stroke-width="[^"]*"')


@lru_cache(maxsize=None)
def _svg_text(name: str) -> str:
    """读取 SVG 源码;文件缺失或损坏时返回空串(渲染为空白,不抛异常)。"""
    try:
        path = assets_dir() / "icons" / f"{name}.svg"
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


@lru_cache(maxsize=None)
def _renderer(name: str, stroke: str) -> QSvgRenderer:
    """按「名称 + 描边宽度」缓存渲染器;stroke 为空表示用 SVG 原始描边。"""
    text = _svg_text(name)
    if stroke and text:
        text = _STROKE_RE.sub(f'stroke-width="{stroke}"', text)
    return QSvgRenderer(QByteArray(text.encode("utf-8")))


def screen_scale() -> float:
    """当前屏幕缩放率(1.0 表示 100%)。"""
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def _stroke_for(physical: int) -> str:
    """按物理尺寸给出描边宽度;不需要加粗时返回空串(用原始描边)。"""
    stroke = max(BASE_STROKE, MIN_STROKE_PX * VIEWBOX / physical)
    return "" if stroke <= BASE_STROKE + 1e-6 else f"{stroke:.2f}"


def _render(name: str, color: QColor, size: int, scale: float) -> QPixmap:
    """按物理分辨率渲染并染色,返回的位图逻辑尺寸严格等于 size。

    物理尺寸取 ceil(size * scale):18 * 1.25 = 22.5 这类半像素值
    向下取整会少一像素,Qt 还得再重采样一次,线条又会发糊。
    而 devicePixelRatio 取 physical / size(不是屏幕缩放率本身):
    ceil 之后逻辑尺寸会变成 physical / 缩放率 ≠ size(如 18 / 1.25
    = 14.4),控件按 size 逻辑像素绘制时 Qt 仍会缩放这张位图,同样发糊。
    """
    physical = max(1, math.ceil(size * scale))
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.transparent)
    renderer = _renderer(name, _stroke_for(physical))
    if renderer.isValid():
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, physical, physical))
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()
    pixmap.setDevicePixelRatio(physical / size)
    return pixmap


def svg_pixmap(
    name: str, color: QColor, size: int = 16, scale: float | None = None
) -> QPixmap:
    """渲染单张位图;默认按当前屏幕缩放率渲染,适合 setPixmap 的场景。"""
    return _render(name, color, size, screen_scale() if scale is None else scale)


def svg_icon(name: str, color: QColor, size: int = 16) -> QIcon:
    """加载 assets/icons 下的 SVG,并渲染为指定主题颜色的 QIcon。"""
    icon = QIcon()
    for scale in sorted({screen_scale(), *ICON_SCALES}):
        icon.addPixmap(_render(name, color, size, scale))
    return icon


def _render_color(name: str, size: int, scale: float) -> QPixmap:
    """按物理分辨率渲染,保留 SVG 自带颜色(不做单色染色)。

    与 _render 的区别只在于跳过 SourceIn 填色;其余高分屏处理一致。
    也不改描边:自带颜色的 mark 是块面为主,加粗描边反而会糊。
    """
    physical = max(1, math.ceil(size * scale))
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.transparent)
    renderer = _renderer(name, "")
    if renderer.isValid():
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, physical, physical))
        painter.end()
    pixmap.setDevicePixelRatio(physical / size)
    return pixmap


def color_svg_pixmap(name: str, size: int = 16, scale: float | None = None) -> QPixmap:
    """渲染自带颜色的 SVG(如品牌 mark),不套主题色。"""
    return _render_color(name, size, screen_scale() if scale is None else scale)


APP_ICON_NAME = "icon.ico"   # 与任务栏/exe 同一个应用图标


@lru_cache(maxsize=None)
def _app_icon_source() -> QPixmap:
    """读取 assets/icon.ico 中最大的一帧;文件缺失时返回空位图。"""
    path = assets_dir() / APP_ICON_NAME
    if not path.exists():
        return QPixmap()
    icon = QIcon(str(path))
    # ico 是多尺寸位图集合,取最大的那帧(小帧本身就是重绘过的粗糙版)
    for side in (256, 128, 64, 48, 32, 16):
        pixmap = icon.pixmap(side, side)
        if not pixmap.isNull():
            return pixmap
    return QPixmap()


def app_icon_pixmap(size: int = 20, scale: float | None = None) -> QPixmap:
    """应用图标(assets/icon.ico)按逻辑尺寸渲染的位图。

    ico 没有矢量源,由最大帧平滑缩放而来,质量比让 QIcon 自己挑档位稳定;
    缩放同样按物理像素做,避免高分屏下被系统放大导致发糊。
    """
    source = _app_icon_source()
    if source.isNull():
        return source
    ratio = screen_scale() if scale is None else scale
    physical = max(1, math.ceil(size * ratio))
    pixmap = source.scaled(
        physical, physical, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    pixmap.setDevicePixelRatio(physical / size)
    return pixmap
