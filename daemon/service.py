import os
import re

import dbus
import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

A11Y_STATUS_BUS = "org.a11y.Bus"
A11Y_STATUS_PATH = "/org/a11y/bus"
A11Y_STATUS_IFACE = "org.a11y.Status"

KWIN_SCRIPT_ID = "kheetsheet-activewindow"

MENU_ROLES = {"menu", "menu item", "check menu item", "radio menu item"}
MENU_BAR_ROLE = "menu bar"

_GTK_MODIFIER_LABELS = {
    "control": "Ctrl",
    "primary": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "super": "Super",
    "meta": "Meta",
}
_GTK_MODIFIER_TAG = re.compile(r"<(\w+)>")


def _normalize_key_binding(raw):
    if not raw:
        return None
    if ";" not in raw:
        # Qt/KDE apps' ATK-adjacent bridge already returns a clean,
        # human-readable string (e.g. "Ctrl+N") - nothing to parse.
        return raw
    # GTK/ATK's format is "mnemonic;menu-path;accelerator", three fields
    # meant to be parsed rather than displayed verbatim. Only the third
    # field is a real, always-available keyboard shortcut - the other two
    # are Alt-driven menu-navigation aids. Dynamic, non-command menu items
    # (browsing history entries, bookmark lists, ...) share the same
    # "menu item" role as real commands but have no accelerator at all, so
    # requiring a non-empty third field also filters those out.
    parts = raw.split(";")
    accel = parts[2] if len(parts) >= 3 else ""
    if not accel:
        return None
    mods = _GTK_MODIFIER_TAG.findall(accel)
    remainder = _GTK_MODIFIER_TAG.sub("", accel)
    labels = [_GTK_MODIFIER_LABELS.get(mod.lower(), mod) for mod in mods]
    if remainder:
        labels.append(remainder.upper() if len(remainder) == 1 else remainder)
    return "+".join(labels)


def ensure_accessibility_enabled():
    bus = dbus.SessionBus()
    obj = bus.get_object(A11Y_STATUS_BUS, A11Y_STATUS_PATH)
    props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
    if not bool(props.Get(A11Y_STATUS_IFACE, "IsEnabled")):
        props.Set(A11Y_STATUS_IFACE, "IsEnabled", True)


def ensure_kwin_script_loaded():
    # KWin doesn't reliably auto-load an installed+enabled script at its own
    # startup (confirmed: still false after a full reboot) - so the daemon,
    # which does run fresh every login, loads it itself instead of relying
    # on that.
    bus = dbus.SessionBus()
    scripting = dbus.Interface(
        bus.get_object("org.kde.KWin", "/Scripting"), "org.kde.kwin.Scripting"
    )
    if bool(scripting.isScriptLoaded(KWIN_SCRIPT_ID)):
        return

    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    script_path = os.path.join(
        data_home, "kwin", "scripts", KWIN_SCRIPT_ID, "contents", "code", "main.js"
    )
    # dbus-python's high-level Interface proxy resolves overloaded Qt methods
    # to whichever signature the introspection XML lists first, regardless of
    # how many arguments are actually passed - get_dbus_method + an explicit
    # signature sidesteps that ambiguity for loadScript's two overloads.
    load_script = scripting.get_dbus_method("loadScript")
    load_script(script_path, KWIN_SCRIPT_ID, signature="ss")
    scripting.start()


def find_app_node_by_pid(pid, app_id=None):
    # Flatpak-sandboxed apps route their D-Bus traffic through a per-instance
    # xdg-dbus-proxy process, so AT-SPI (and KWin, separately) each end up
    # reporting a different pid for the same window - the proxy's pid, not
    # the real app's - and they're not parent/child of each other, so there's
    # no reliable way to translate one into the other. An exact pid match is
    # still tried first since it's precise and unaffected for normal (non-
    # sandboxed) apps, but when it fails, fall back to a loose match between
    # the AT-SPI app's own name and the window's resourceClass (app_id) -
    # good enough to recover Flatpak apps that would otherwise never be found.
    desktop = Atspi.get_desktop(0)
    normalized_app_id = app_id.strip().lower() if app_id else None
    fallback = None
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        try:
            if app.get_process_id() == pid:
                return app
        except Exception:
            pass
        if fallback is None and normalized_app_id:
            try:
                name = (app.get_name() or "").strip().lower()
            except Exception:
                continue
            if name and (name in normalized_app_id or normalized_app_id in name):
                fallback = app
    return fallback


def collect_shortcuts(app_node, max_depth=15):
    # KDE/Qt menu bars expose top-level entries (File, Edit, ...) as direct
    # children of the window, with the same "menu item" role as their
    # descendants - there is no separate "menu" container node to key off of.
    shortcuts = []

    def walk(acc, group, depth):
        if depth > max_depth:
            return
        try:
            role = acc.get_role_name()
            name = acc.get_name()
        except Exception:
            return

        if role in MENU_ROLES and name and group is not None:
            try:
                key_binding = _normalize_key_binding(acc.get_key_binding(0))
            except Exception:
                key_binding = None
            if key_binding:
                shortcuts.append((group, name, key_binding))

        try:
            child_count = acc.get_child_count()
        except Exception:
            return
        for j in range(child_count):
            try:
                child = acc.get_child_at_index(j)
            except Exception:
                continue
            walk(child, group, depth + 1)

    def find_menu_bars(acc, depth):
        if depth > max_depth:
            return
        try:
            role = acc.get_role_name()
            child_count = acc.get_child_count()
        except Exception:
            return
        if role == MENU_BAR_ROLE:
            for j in range(child_count):
                try:
                    top_menu = acc.get_child_at_index(j)
                    top_name = top_menu.get_name()
                    top_role = top_menu.get_role_name()
                except Exception:
                    continue
                if top_role not in MENU_ROLES or not top_name:
                    continue
                try:
                    sub_count = top_menu.get_child_count()
                except Exception:
                    continue
                for k in range(sub_count):
                    try:
                        sub_child = top_menu.get_child_at_index(k)
                    except Exception:
                        continue
                    walk(sub_child, top_name, 0)
            return
        for j in range(child_count):
            try:
                child = acc.get_child_at_index(j)
            except Exception:
                continue
            find_menu_bars(child, depth + 1)

    find_menu_bars(app_node, 0)
    return shortcuts


def shortcuts_for_pid(pid, app_id=None):
    app_node = find_app_node_by_pid(pid, app_id=app_id)
    if app_node is None:
        return None, []
    try:
        app_name = app_node.get_name()
    except Exception:
        app_name = None
    return app_name, collect_shortcuts(app_node)
