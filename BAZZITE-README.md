# Installing KheetSheet on Bazzite

**Status: verified** on a real Bazzite (Kinoite) machine, Plasma 6 / Wayland.
Bazzite is built on Fedora Atomic (rpm-ostree) — the base OS image is
immutable, so `dnf install` doesn't work the way `apt install` does on
Kubuntu/Debian. Persistent system packages have to be *layered* onto the image
with `rpm-ostree install`, which requires a reboot to take effect. Fedora's
package names also don't all match Debian/Ubuntu's — same underlying
software, different names.

Everything else about KheetSheet (the daemon, the KWin script, `install.sh`,
the manual shortcut-binding step) is standard KDE Plasma machinery, not
Kubuntu-specific — none of that needs to change for Bazzite.

## Screenshots

See the main [README.md](README.md#screenshots) — same overlay, same output,
verified working on this distro too.

## 1. Install dependencies

```
rpm-ostree install python3-pyqt6 python3-dbus python3-gobject \
    at-spi2-core kf6-kpackage kf6-kconfig qt6-qttools
```

Then reboot for the layered packages to take effect:

```
systemctl reboot
```

If your image already has some of these layered (check with `rpm-ostree
status`) or ships them as part of the base Plasma spin, this step may be a
partial or full no-op — `install.sh` (next step) tells you exactly what's
still missing, so it's safe to just try running it first and only reach for
`rpm-ostree install` if it reports a gap.

Package name notes:

- `python3-pyqt6`, `python3-dbus` — match Debian's naming.
- `python3-gobject` — Fedora's name for what Debian calls `python3-gi`.
- `at-spi2-core` — provides the AT-SPI GObject-introspection typelib that
  Debian ships separately as `gir1.2-atspi-2.0`.
- `kf6-kpackage`, `kf6-kconfig` — provide `kpackagetool6` and
  `kwriteconfig6`/`kreadconfig6`. On most Plasma spins these are already part
  of the base image.
- `qt6-qttools` — provides the Qt6 D-Bus CLI tool, but as **`qdbus-qt6`**, not
  `qdbus6` (Debian's binary name for the same tool). `install.sh` checks for
  either name automatically, so this naming difference doesn't require any
  action from you.
- **`python3-dbus.mainloop.pyqt6`** — no separate Fedora package; the module
  it provides (`dbus.mainloop.pyqt6`, imported by `daemon/__main__.py`) came
  through as part of `python3-pyqt6` in testing. If `install.sh` still
  reports this one missing after installing the above, that means your image
  needs it from `pip` instead.

## 2. Run the installer

Same as Kubuntu — nothing distro-specific in the script itself:

```
./install.sh
```

If it reports a missing dependency, that means the guess above was wrong for
that one. Find the real package with:

```
dnf provides '*/<missing-binary-or-file>'
```

e.g. `dnf provides '*/kwriteconfig6'` to find whatever package actually ships
that binary on Bazzite, then `rpm-ostree install` it and reboot again.

## 3. Bind the global shortcut

Identical manual step to the Kubuntu install — System Settings → Shortcuts →
Add New → Command or Script. See [README.md](README.md#3-bind-the-global-shortcut-manual-step)
for the exact command to bind. This part of `kglobalaccel` is Plasma-level,
not distro-specific, and behaves the same here.

## 4. Try it

Press your bound shortcut over a running Qt/KDE app. Verified end-to-end on
this distro: the daemon starts, registers on the session bus, AT-SPI
extraction returns real shortcut data (confirmed against Dolphin and Kate),
and the overlay renders correctly as an XWayland client over the Wayland
session.

## Updating

Same process as Kubuntu — see [README.md](README.md#updating). Nothing
Bazzite-specific about it; `install.sh` handles re-checking dependencies,
reinstalling, and restarting the daemon regardless of distro.

## Things confirmed working on Bazzite

- **AT-SPI extraction** — walking a running app's accessible tree and pulling
  real shortcuts (group, name, keybinding) works exactly as on Kubuntu.
- **`QT_QPA_PLATFORM=xcb` requirement** — the overlay renders correctly as an
  XWayland client over the Wayland session; no extra setup needed for
  XWayland itself.
- **D-Bus / systemd wiring** — the daemon registers `com.kheetsheet.Daemon`,
  enables `org.a11y.Status.IsEnabled` itself, and the KWin script loads and
  reports active-window changes, all via the same systemd user service setup
  as Kubuntu.
- **Flatpak apps** (common on Bazzite, which leans heavily on Flatpak for
  browsers and other user apps) — found and fixed a real bug here: every
  Flatpak app routes its D-Bus traffic through a per-instance
  `xdg-dbus-proxy`, so AT-SPI sees the *proxy's* pid for a window, not the
  real app's, while KWin reports the real one — they never matched, so
  Flatpak apps were silently unsupported regardless of whether they exposed
  a menu at all. The daemon now falls back to matching the AT-SPI app's name
  against the window's `resourceClass` when the exact pid lookup misses.
  Confirmed working end-to-end against Firefox and Vivaldi (both Flatpak).

## Things not yet checked on Bazzite

- **SELinux vs AppArmor.** The Kubuntu install found that AppArmor blocked one
  snap-confined app (VS Code) from querying another snap's (Vivaldi's)
  AT-SPI tree — this didn't affect KheetSheet's own use case, but SELinux
  (enabled by default on Fedora/Bazzite) enforces differently and hasn't been
  checked against this daemon's AT-SPI queries specifically.
