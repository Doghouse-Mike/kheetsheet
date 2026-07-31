from itertools import groupby

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QScrollArea,
    QFrame,
)

from service import invoke_shortcut

# How long the pressed/highlighted state stays visible before the overlay
# dismisses - long enough to register as deliberate feedback, short enough
# to not feel like a delay.
CLICK_FEEDBACK_MS = 150

MAX_COLUMNS = 4
MAX_SCREEN_FRACTION = 0.85


class ShortcutRow(QFrame):
    # A plain QWidget/QFrame sizes itself from its layout's sizeHint, unlike
    # QAbstractButton (including a flat QPushButton with a custom layout set
    # on it), whose sizeHint comes from its own text/icon metrics regardless
    # of what's actually inside it - that mismatch was squeezing the real
    # content (esp. the name label) into a too-small button and truncating
    # it. This gets the click/hover/press behavior back without that.
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("shortcutRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._pressed = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._repolish()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._repolish()
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _repolish(self):
        self.setProperty("pressed", self._pressed)
        self.style().unpolish(self)
        self.style().polish(self)


class KheetSheetOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KheetSheet")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._container = QWidget(self)
        self._container.setObjectName("container")
        self._container.setStyleSheet(
            "#container { background-color: rgba(20, 20, 20, 235); border-radius: 14px; }"
            "QLabel { color: #eeeeee; }"
            "QFrame#shortcutRow { background: transparent; border-radius: 6px; }"
            "QFrame#shortcutRow:hover { background-color: rgba(255,255,255,25); }"
            "QFrame#shortcutRow[pressed=\"true\"] { background-color: rgba(120,170,255,70); }"
        )
        shadow = QGraphicsDropShadowEffect(blurRadius=40, xOffset=0, yOffset=8)
        self._container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(self._container)

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(28, 20, 28, 24)
        self._layout.setSpacing(14)

        self._title = QLabel()
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self._title.setFont(title_font)
        self._layout.addWidget(self._title)

        self._grid_holder = QWidget()
        self._grid = QGridLayout(self._grid_holder)
        self._grid.setHorizontalSpacing(36)
        self._grid.setVerticalSpacing(10)

        # Long shortcut lists/labels can exceed the screen in either
        # dimension - scrolling (rather than an unbounded popup) is what
        # keeps this usable regardless of how much a given app exposes.
        self._scroll = QScrollArea(self._container)
        self._scroll.setWidget(self._grid_holder)
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._layout.addWidget(self._scroll)

    def show_shortcuts(self, app_name, shortcuts):
        self._title.setText(app_name or "Unknown application")

        # QScrollArea (in setWidgetResizable(False) mode) silently freezes
        # _grid_holder's effective size after the first show_shortcuts() call
        # - adjustSize() stops taking effect once the scroll area has adopted
        # the widget, so later calls with differently-sized content (e.g. the
        # single "no shortcuts" label after a big real shortcut list, or vice
        # versa) get stuck at whatever size was shown first. Detaching the
        # widget before rebuilding and resizing it, then reattaching, avoids
        # that. The scroll area's own sizeHint() also doesn't propagate to
        # the window's layout on its own - updateGeometry() forces that.
        self._scroll.takeWidget()
        self._clear_grid()

        if not shortcuts:
            empty = QLabel(
                "No AT-SPI-exposed shortcuts found for this application.\n"
                "GTK app? Try Ctrl+? — many bind their own shortcuts window to it."
            )
            self._grid.addWidget(empty, 0, 0)
        else:
            groups = [(g, list(items)) for g, items in groupby(shortcuts, key=lambda s: s[0])]
            for col, (group_name, items) in enumerate(groups):
                row = col // MAX_COLUMNS
                grid_col = col % MAX_COLUMNS
                column_widget = self._build_column(group_name, items)
                self._grid.addWidget(column_widget, row, grid_col, Qt.AlignmentFlag.AlignTop)

        self._grid_holder.adjustSize()
        self._scroll.setWidget(self._grid_holder)
        self._scroll.updateGeometry()
        self._container.updateGeometry()

        # Bound the whole popup to a fraction of the screen and let resize()
        # clamp to that; the layout shrinks the (flexible) scroll area to
        # make room rather than the title, so long lists scroll instead of
        # pushing the window off-screen.
        self.setMaximumSize(self._max_popup_size())
        self.adjustSize()
        self._center_on_active_screen()
        self.show()
        self.raise_()
        self.activateWindow()

    def _max_popup_size(self):
        screen = self.screen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        return QSize(
            int(available.width() * MAX_SCREEN_FRACTION),
            int(available.height() * MAX_SCREEN_FRACTION),
        )

    def _build_column(self, group_name, items):
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel(group_name)
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        for _, item_name, key_binding, accessible in items:
            row = ShortcutRow()

            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(12)
            key_label = QLabel(key_binding)
            key_label.setStyleSheet(
                "background-color: rgba(255,255,255,30); border-radius: 4px;"
                "padding: 1px 6px; font-family: monospace;"
            )
            name_label = QLabel(item_name)
            row_layout.addWidget(key_label)
            row_layout.addWidget(name_label)
            row_layout.addStretch()

            row.clicked.connect(lambda acc=accessible: self._on_shortcut_clicked(acc))
            layout.addWidget(row)

        return column

    def _on_shortcut_clicked(self, accessible):
        invoke_shortcut(accessible)
        QTimer.singleShot(CLICK_FEEDBACK_MS, self.hide)

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _center_on_active_screen(self):
        screen = self.screen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        rect = QRect(0, 0, self.width(), self.height())
        rect.moveCenter(geometry.center())
        self.move(rect.topLeft())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.hide()
        super().changeEvent(event)
