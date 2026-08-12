from itertools import groupby

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGraphicsDropShadowEffect,
    QScrollArea,
    QFrame,
)

from i18n import _
from service import invoke_shortcut

# How long the pressed/highlighted state stays visible before the overlay
# dismisses - long enough to register as deliberate feedback, short enough
# to not feel like a delay.
CLICK_FEEDBACK_MS = 150

MAX_SCREEN_FRACTION = 0.85
GROUP_SPACING = 36
ROW_SPACING = 10
# Hard cap on a single group's width, with word-wrap on its item names, so
# one long menu name can't blow out a row's width and force the horizontal
# scrolling this whole layout exists to avoid.
MAX_COLUMN_WIDTH = 320
# Covers the outer window margins (24px each side), the container's inner
# margins (28px each side), and a vertical scrollbar's width - all chrome
# between the popup's outer edge and where a row actually gets to draw,
# reserved up front so a row that measures as "just fits" doesn't get
# clipped once that chrome and a scrollbar are actually in place.
CHROME_WIDTH_BUFFER = 130


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
        self._rows_layout = QVBoxLayout(self._grid_holder)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(ROW_SPACING)

        # Long shortcut lists/labels can exceed the screen in either
        # dimension - scrolling (rather than an unbounded popup) is what
        # keeps this usable regardless of how much a given app exposes.
        # Horizontal scrolling is disabled outright: groups are shelf-packed
        # left-to-right into rows that wrap once the next one wouldn't fit
        # (see _pack_columns_into_rows), so there's never content off to the
        # side - only further down, which the vertical scrollbar covers.
        self._scroll = QScrollArea(self._container)
        self._scroll.setWidget(self._grid_holder)
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._layout.addWidget(self._scroll)

    def show_shortcuts(self, app_name, shortcuts):
        self._title.setText(app_name or _("Unknown application"))

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
        self._clear_rows()

        max_size = self._max_popup_size()
        available_width = max_size.width() - CHROME_WIDTH_BUFFER

        if not shortcuts:
            empty = QLabel(
                _(
                    "No AT-SPI-exposed shortcuts found for this application.\n"
                    "GTK app? Try Ctrl+? — many bind their own shortcuts window to it."
                )
            )
            empty.setWordWrap(True)
            self._rows_layout.addWidget(empty)
        else:
            groups = [(g, list(items)) for g, items in groupby(shortcuts, key=lambda s: s[0])]
            columns = [self._build_column(name, items) for name, items in groups]
            self._pack_columns_into_rows(columns, available_width)

        # Clamping the holder's width (rather than just relying on the rows
        # already fitting) keeps adjustSize() from measuring a width wider
        # than what we actually packed for, which is what would otherwise
        # let a horizontal scrollbar sneak back in.
        self._grid_holder.setMaximumWidth(available_width)
        self._grid_holder.adjustSize()
        self._scroll.setWidget(self._grid_holder)
        # QScrollArea's own sizeHint() under-reports its needed width here -
        # even in the original grid-based layout, it settled narrower than
        # the widget it was given, silently relying on a horizontal
        # scrollbar to reach the rest. Forcing a minimum width explicitly is
        # what actually makes the container/window grow to match the real
        # content instead of leaving it clipped now that scrollbar is gone.
        self._scroll.setMinimumWidth(self._grid_holder.width())
        self._scroll.updateGeometry()
        self._container.updateGeometry()

        # Bound the whole popup to a fraction of the screen and let resize()
        # clamp to that; the layout shrinks the (flexible) scroll area to
        # make room rather than the title, so long lists scroll instead of
        # pushing the window off-screen.
        self.setMaximumSize(max_size)
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

    def _pack_columns_into_rows(self, columns, available_width):
        # Shelf-packs groups left-to-right, wrapping to a new row once the
        # next one would exceed available_width - a dynamic count rather
        # than a fixed one, so the popup only ever grows downward regardless
        # of how many groups an app exposes or how wide any of them are.
        row_layout = None
        row_width = 0
        for column in columns:
            column_width = column.sizeHint().width()
            if row_layout is None or row_width + GROUP_SPACING + column_width > available_width:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(GROUP_SPACING)
                row_layout.addStretch()
                self._rows_layout.addWidget(row_widget)
                row_width = 0
            # Inserted before the trailing stretch so columns stay packed to
            # the left instead of spreading out across the row.
            row_layout.insertWidget(row_layout.count() - 1, column, 0, Qt.AlignmentFlag.AlignTop)
            row_width += column_width + (GROUP_SPACING if row_width else 0)

    def _set_elided_text(self, label, text, max_width):
        elided = label.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max_width)
        label.setText(elided)
        if elided != text:
            label.setToolTip(text)

    def _build_column(self, group_name, items):
        column = QWidget()
        column.setMaximumWidth(MAX_COLUMN_WIDTH)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel()
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        self._set_elided_text(header, group_name, MAX_COLUMN_WIDTH)
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
            name_label = QLabel()
            # Elided (not word-wrapped) so this label's width is a fixed,
            # known quantity - a wrapped QLabel reports an elastic sizeHint
            # that Qt happily shrinks well past what _pack_columns_into_rows
            # measured, which is what let a row overflow its budget and
            # squeeze itself into an unreadable sliver in testing.
            name_max_width = (
                MAX_COLUMN_WIDTH - row_layout.contentsMargins().left()
                - row_layout.contentsMargins().right() - row_layout.spacing()
                - key_label.sizeHint().width()
            )
            self._set_elided_text(name_label, item_name, name_max_width)
            row_layout.addWidget(key_label)
            row_layout.addWidget(name_label)
            row_layout.addStretch()

            row.clicked.connect(lambda acc=accessible: self._on_shortcut_clicked(acc))
            layout.addWidget(row)

        return column

    def _on_shortcut_clicked(self, accessible):
        invoke_shortcut(accessible)
        QTimer.singleShot(CLICK_FEEDBACK_MS, self.hide)

    def _clear_rows(self):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
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
