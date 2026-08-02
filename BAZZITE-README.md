
# Installing KheetSheet on Bazzite

Tested on a real Bazzite (Kinoite) machine (or two), Plasma 6 / Wayland.

Bazzite is built on Fedora Atomic (rpm-ostree) — the base OS image is immutable, so `dnf install` doesn't work the way `apt install` does on Kubuntu/Debian. Persistent system packages have to be *layered* onto the image with `rpm-ostree install`, which requires a reboot to take effect. Fedora's package names also don't all match Debian/Ubuntu's — same underlying software, different names.

Everything else about KheetSheet (the daemon, the KWin script, `install.sh`, the manual shortcut-binding step) is standard KDE Plasma fare and doesn't need to change for Bazzite.

## 1. Install Dependencies

```
rpm-ostree install python3-pyqt6 python3-dbus python3-gobject \
    at-spi2-core kf6-kpackage kf6-kconfig qt6-qttools
```

Then reboot for the layered packages to take effect:

```
systemctl reboot
```

(Or just press the button)

If your image already has some of these layered (check with `rpm-ostree

status`) or ships them as part of the base Plasma spin, this step may be a partial or full no-op — `install.sh` (next step) tells you exactly what's still missing, so it's safe to just try running it first and only reach for `rpm-ostree install` if it reports a gap.

### Package Name Notes:

- `python3-pyqt6`, `python3-dbus` match Debian's naming.
- `python3-gobject` Fedora's name for what Debian calls `python3-gi`.
- `at-spi2-core` provides the AT-SPI GObject-introspection typelib that Debian ships separately as `gir1.2-atspi-2.0`.
- `kf6-kpackage`, `kf6-kconfig` provide `kpackagetool6` and
  `kwriteconfig6`/`kreadconfig6`. On most Plasma spins these are already part of the base image.
- `qt6-qttools` provides the Qt6 D-Bus CLI tool, but as **`qdbus-qt6`**, not
  `qdbus6` (Debian's binary name for the same tool). `install.sh` checks for either name automatically, so this naming difference doesn't require any action.
- **`python3-dbus.mainloop.pyqt6`** — no separate Fedora package, the module it provides (`dbus.mainloop.pyqt6`, imported by `daemon/__main__.py`) came through as part of `python3-pyqt6` in testing. If `install.sh` still reports this one missing after installing the above, that means your image needs it from `pip` instead.

## 2. Run the Installer

Nothing distro-specific in the script itself:

```
./install.sh
```

If it reports a missing dependency, that means the guess above was wrong. Find the real package with:

```
dnf provides '*/<missing-binary-or-file>'
```

e.g. `dnf provides '*/kwriteconfig6'` to find whatever package actually ships that binary on Bazzite, then `rpm-ostree install` it and reboot again.

## 3. Bind the Global Shortcut

Identical manual step to the Kubuntu install, this step is done through the GUI:

1. Open **System Settings → Shortcuts**.
2. Click **"Add New"** (top right) → **"Command or Script"**.
3. I'd suggest naming it "KheetSheet" and set the command to:

   ```
   gdbus call --session --dest com.kheetsheet.Daemon --object-path /KheetSheet --method com.kheetsheet.Daemon.Toggle
   ```

4. Set your preferred trigger key
5. Click **Apply**.

> Double-check the key that actually lands in the trigger field before saving, it can end up different from what you pressed if the recording widget catches extra held modifiers or has a moment. I use `META+/`

## 4. Try it

Press your bound shortcut over a running Qt/KDE app.

## Updating

Same process as Kubuntu — see [README.md](README.md#updating). Nothing Bazzite-specific about it; `install.sh` handles re-checking dependencies, reinstalling, and restarting the daemon regardless of distro.

## Things Confirmed Working on Bazzite

- **AT-SPI extraction** walking a running app's accessible tree and pulling real shortcuts (group, name, keybinding) works exactly as on Kubuntu.
- **`QT_QPA_PLATFORM=xcb` requirement** the overlay renders correctly as an XWayland client over the Wayland session; no extra setup needed for XWayland itself.
- **D-Bus / systemd wiring** the daemon registers `com.kheetsheet.Daemon`, enables `org.a11y.Status.IsEnabled` itself, and the KWin script loads and reports active-window changes, all via the same systemd user service setup as Kubuntu.
- **Flatpak apps** (common on Bazzite, which leans heavily on Flatpak for browsers and other user apps) every Flatpak app routes its D-Bus traffic through a per-instance `xdg-dbus-proxy`, so AT-SPI sees the *proxy's* pid for a window, not the real app's, while KWin reports the real one, they never matched, so Flatpak apps were silently unsupported regardless of whether they exposed a menu at all. The daemon now falls back to matching the AT-SPI app's name against the window's `resourceClass` when the exact pid lookup misses.
  Confirmed working end-to-end against Firefox and Vivaldi (both Flatpak).

## Things Not yet Checked on Bazzite

- **SELinux vs AppArmor.** The Kubuntu install found that AppArmor blocked one snap-confined app (VS Code) from querying another snap's (Vivaldi's) AT-SPI tree — this didn't affect KheetSheet's own use case, but SELinux (enabled by default on Fedora/Bazzite) enforces differently and hasn't been checked against this daemon's AT-SPI queries specifically. - Doesn't seem to be an issue.
