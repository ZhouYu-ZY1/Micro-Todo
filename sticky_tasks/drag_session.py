"""Reusable visual drag session for sortable Qt widgets."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPixmap, QRegion
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QLabel, QLayout, QVBoxLayout, QWidget,
)


class DragSession:
    """Drag one widget with a floating snapshot and a layout placeholder.

    The session owns only temporary Qt widgets. The caller decides the target
    index and persists the final order after ``finish``.
    """

    def __init__(
        self,
        widget: QWidget,
        layout: QLayout,
        indicator_host: QWidget,
        global_pos: QPoint,
        accent: QColor,
        sortable_widgets: Callable[[], list[QWidget]],
        background: QColor = None,
    ):
        self.widget = widget
        self.layout = layout
        self.indicator_host = indicator_host
        self.items = list(sortable_widgets())
        self.others = [item for item in self.items if item is not widget]
        self.original_index = self.items.index(widget) if widget in self.items else 0
        self.target_index = self.original_index
        self._closed = False
        self._grab_offset = global_pos - widget.mapToGlobal(QPoint(0, 0))
        self._original_visible = widget.isVisible()

        self.placeholder = QFrame(indicator_host)
        self.placeholder.setObjectName("dragPlaceholder")
        self.placeholder.setFixedHeight(max(1, widget.height()))
        self.placeholder.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.placeholder.setStyleSheet(
            "QFrame#dragPlaceholder {"
            f"background: rgba({accent.red()}, {accent.green()}, {accent.blue()}, 28);"
            f"border: 1px dashed rgba({accent.red()}, {accent.green()}, {accent.blue()}, 180);"
            "border-radius: 7px;"
            "}"
        )

        self.indicator = QFrame(indicator_host)
        self.indicator.setObjectName("dragIndicator")
        self.indicator.setFixedHeight(2)
        self.indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.indicator.setStyleSheet(
            "QFrame#dragIndicator {"
            f"background: rgba({accent.red()}, {accent.green()}, {accent.blue()}, 230);"
            "border-radius: 1px;"
            "}"
        )

        pixmap = self._snapshot(widget, background)
        self.overlay = QLabel()
        self.overlay.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
        )
        self.overlay.setAttribute(Qt.WA_TranslucentBackground)
        self.overlay.setAttribute(Qt.WA_ShowWithoutActivating)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.overlay.setStyleSheet(
            "QLabel {"
            f"border: 1px solid rgba({accent.red()}, {accent.green()}, {accent.blue()}, 220);"
            "border-radius: 8px; background: transparent;"
            "}"
        )
        self.overlay.setPixmap(pixmap)
        self.overlay.resize(pixmap.size())
        self.overlay.setWindowOpacity(0.85)
        shadow = QGraphicsDropShadowEffect(self.overlay)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.overlay.setGraphicsEffect(shadow)

        self.layout.removeWidget(widget)
        self._replace_with_placeholder(self.target_index)
        widget.hide()
        self.placeholder.show()
        self.indicator.show()
        self.overlay.move(global_pos - self._grab_offset)
        self.overlay.show()
        self.overlay.raise_()
        self._update_indicator()

    @staticmethod
    def _snapshot(widget, background):
        """快照被拖控件。

        任务行自身背景透明(容器统一绘制),直接 grab() 会得到未初始化的
        白底。先用主题背景色铺底再渲染,浮层外观才和列表里一致。
        """
        dpr = widget.devicePixelRatioF()
        pixmap = QPixmap(int(widget.width() * dpr), int(widget.height() * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(background if background is not None else Qt.transparent)
        widget.render(pixmap, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return pixmap

    @property
    def is_active(self):
        return not self._closed

    @property
    def overlay_visible(self):
        return self.overlay.isVisible() if not self._closed else False

    @property
    def indicator_visible(self):
        return self.indicator.isVisible() if not self._closed else False

    def _layout_index_for_target(self, target_index):
        target_index = max(0, min(target_index, len(self.others)))
        if target_index == len(self.others):
            indices = [self.layout.indexOf(item) for item in self.others]
            return (max(indices) + 1) if indices else self.layout.count()
        return self.layout.indexOf(self.others[target_index])

    def _replace_with_placeholder(self, target_index):
        old_index = self.layout.indexOf(self.placeholder)
        if old_index >= 0:
            self.layout.removeWidget(self.placeholder)
        index = self._layout_index_for_target(target_index)
        self.layout.insertWidget(index, self.placeholder)
        self.layout.activate()
        self.target_index = target_index

    def move(self, global_pos: QPoint, target_index: int):
        if self._closed:
            return
        self.overlay.move(global_pos - self._grab_offset)
        target_index = max(0, min(target_index, len(self.others)))
        if target_index != self.target_index:
            self._replace_with_placeholder(target_index)
        self._update_indicator()

    def _update_indicator(self):
        others = self.others
        if not others:
            y_global = self.placeholder.mapToGlobal(QPoint(0, 0)).y()
        elif self.target_index >= len(others):
            y_global = others[-1].mapToGlobal(QPoint(0, others[-1].height())).y()
        else:
            y_global = others[self.target_index].mapToGlobal(QPoint(0, 0)).y()
        host_pos = self.indicator_host.mapFromGlobal(QPoint(0, y_global))
        self.indicator.setGeometry(
            8, host_pos.y(), max(1, self.indicator_host.width() - 16), 2,
        )
        self.indicator.raise_()

    def _remove_placeholder(self):
        if self.layout.indexOf(self.placeholder) >= 0:
            self.layout.removeWidget(self.placeholder)

    def finish(self):
        if self._closed:
            return self.target_index
        target = self.target_index
        self._remove_placeholder()
        self._cleanup()
        index = self._layout_index_for_target(target)
        self.layout.insertWidget(index, self.widget)
        self.widget.show()
        self.layout.activate()
        self._closed = True
        return target

    def cancel(self):
        if self._closed:
            return
        self._remove_placeholder()
        self._cleanup()
        index = self._layout_index_for_target(self.original_index)
        self.layout.insertWidget(index, self.widget)
        self.widget.show()
        self.layout.activate()
        self._closed = True

    def _cleanup(self):
        if self.overlay is not None:
            self.overlay.hide()
            self.overlay.deleteLater()
        self.indicator.hide()
        self.indicator.deleteLater()
        self.placeholder.hide()
        self.placeholder.deleteLater()
        try:
            self.widget.releaseMouse()
        except RuntimeError:
            pass
