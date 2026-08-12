import sys

import dbus
import dbus.service
from dbus.mainloop.pyqt6 import DBusQtMainLoop
from PyQt6.QtWidgets import QApplication

from i18n import _
from overlay import KheetSheetOverlay
from service import (
    ensure_accessibility_enabled,
    ensure_kwin_script_loaded,
    shortcuts_for_pid,
)

BUS_NAME = "com.kheetsheet.Daemon"
OBJECT_PATH = "/KheetSheet"
IFACE = "com.kheetsheet.Daemon"


class KheetSheetService(dbus.service.Object):
    def __init__(self, bus_name, overlay):
        super().__init__(bus_name, OBJECT_PATH)
        self._overlay = overlay
        self._active_pid = None
        self._active_app_id = None

    @dbus.service.method(IFACE, in_signature="iss", out_signature="")
    def NotifyActiveWindow(self, pid, app_id, caption):
        self._active_pid = int(pid)
        self._active_app_id = str(app_id)

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Toggle(self):
        if self._overlay.isVisible():
            self._overlay.hide()
            return
        if self._active_pid is None:
            self._overlay.show_shortcuts(_("No active window known"), [])
            return
        app_name, shortcuts = shortcuts_for_pid(self._active_pid, self._active_app_id)
        self._overlay.show_shortcuts(app_name or self._active_app_id, shortcuts)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    DBusQtMainLoop(set_as_default=True)
    ensure_accessibility_enabled()

    overlay = KheetSheetOverlay()

    bus = dbus.SessionBus()
    bus_name = dbus.service.BusName(BUS_NAME, bus)
    KheetSheetService(bus_name, overlay)

    # Must come after the service above claims BUS_NAME: the KWin script
    # reports the current window immediately on load, and that first
    # callDBus is silently dropped if com.kheetsheet.Daemon doesn't exist on
    # the bus yet.
    try:
        ensure_kwin_script_loaded()
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
