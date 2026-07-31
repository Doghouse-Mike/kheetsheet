
# KheetSheet

A KDE Plasma clone of the ([discontinued](https://www.mediaatelier.com/en/LandingCheatSheet/)) Mac app Cheatsheet.

The idea is that you press a hotkey, and see the focused app's keyboard shortcuts in an overlay, grouped by menu. Shortcut data comes entirely from AT-SPI (the accessibility tree) which has some limitations. If an app *doesn't* expose its menu via AT-SPI (many GTK4/Electron apps), you'll get a simple "no shortcuts found". I've not been able to find a workaround that wasn't super creepy or likely to serve stale data. Or both. Yet?

> I have an idea for Obsidian, but it'd mean accessing the vault to read custom & plugin keybinds and might not get anywhere.

Many GTK4 apps *do* institute their own version though, `CTRL+?` (Or `CTRL+SHIFT+/`) will bring up *their* native overlay.

## AI Disclosure

I, the human writing *this*, barely touched the actual code, that's all Clanker. If that grinds your gears, this may not be for you, but hopefully we can all move on with our lives.

## Screenshots

| Real shortcuts (Dolphin) | App with no AT-SPI menu (VS Code) |
| --- | --- |
| ![Overlay showing Dolphin's File and Edit shortcuts](screenshots/example-dolphin.png) | ![Overlay showing the honest "no shortcuts" message](screenshots/example-no-shortcuts.png) |

## Supported Systems

Any(?) KDE Plasma 6 desktop. I've only tested Kubuntu and Bazzite, installation may differ slightly for not those.

Distro-specific install steps:

- **Kubuntu / Debian / Ubuntu-based** — this page, you're here.
- **Bazzite / Fedora Atomic** — see [BAZZITE-README.md](BAZZITE-README.md). (*slightly* different steps)

## Install (Kubuntu/Debian/Ubuntu-based Plasma 6)

### 1. Install Dependencies

```
sudo apt install python3-pyqt6 python3-dbus python3-dbus.mainloop.pyqt6 \
    python3-gi gir1.2-atspi-2.0 kpackagetool6 libkf6config-bin qdbus-qt6
```

These are all standard KDE/Plasma 6 packages, nothing project-specific.

`install.sh` checks for them by the binaries/Python modules they provide and will flag what's missing rather than installing anything itself. It also won't get partway through and leave things in a broken state.

### 2. Run the Installer

```
./install.sh
```

This installs the KWin active-window watcher script and the `kheetsheet-daemon` systemd user service, then starts the daemon itself.

Accessibility (AT-SPI) is enabled by the daemon itself at every startup via org.a11y.Status.IsEnabled`

### 3. Bind the Global Shortcut (Manual Step)

This step is done through the GUI:

1. Open **System Settings → Shortcuts**.
2. Click **"Add New"** (top right) → **"Command or Script"**.
3. I'd suggest naming it "KheetSheet" and set the command to:

   ```
   gdbus call --session --dest com.kheetsheet.Daemon --object-path /KheetSheet --method com.kheetsheet.Daemon.Toggle
   ```

4. Set your preferred trigger key
5. Click **Apply**.

> Double-check the key that actually lands in the trigger field before saving, it can end up different from what you pressed if the recording widget catches extra held modifiers or has a moment. I use `META+/`

### 4. Try it

Press your bound shortcut over any Qt/KDE app (Dolphin, Kate, Konsole, etc). Pressing it again, hitting `ESC`, or clicking anywhere will dismiss the overlay.

On a non-apt distro not covered by a dedicated guide (Arch, etc.), just run `./install.sh`, it'll tell you exactly which binaries/modules it couldn't find, which you can then map to that distro's package names. If anyone wants to contribute a guide for a distro not already covered, go nuts.

## Updating

1. **If you previously downloaded a `.zip`, delete that old extracted folder first.** Grabbing a fresh copy alongside an old one just leaves two copies lying around — only one is ever wired up to actually run, and it's easy to lose track of which. (If you cloned with `git` instead, skip this — just`git pull` in the same folder.)
2. Get the new version (fresh `.zip` extract, or `git pull`).
3. Run `./install.sh` again **from the new copy.**

`install.sh` re-checks dependencies (skipping anything already satisfied), reinstalls the KWin script and systemd service, and always restarts the daemon *even if it was already running* immediately instead of silently waiting for your next login. If it notices the systemd service previously pointed at a *different* directory (meaning you ran it from a new location rather than updating in place), it'll say so at the end and name the old directory. That one's now safe to delete.

## Usage

Press your bound shortcut to show the current app's shortcuts; press it again (or Esc) to dismiss. You can also click any listed shortcut to run it directly

> Clicking a command invokes the app's actual command handler via AT-SPI's `Action`interface, the same mechanism a screen reader uses to activate something, rather than simulating a keypress. The overlay dismisses shortly after.

## Privacy and Network Access

KheetSheet makes no network calls of any kind, and doesn't write logs, files, or any other record of what you've done. Everything it touches is local:

- Shortcut data comes from AT-SPI's accessible tree of whatever app is
  currently focused, held in memory only for as long as the overlay is open, and never written to disk.
- The only IPC involved (the KWin script notifying the daemon of the active window, `kglobalaccel` triggering `Toggle`) is local D-Bus on your own session bus, it never reaches outside the machine.
- `install.sh` only uses your distro's package manager (`apt`/`rpm-ostree`) for dependencies; there's no separate download step, no bundled telemetry SDK, and no phone-home of any kind.
- The installed systemd service (`systemd/kheetsheet-daemon.service`) sets `RestrictAddressFamilies=AF_UNIX`, so the "no network calls" property isn't just a claim about the current code, the kernel refuses any socket that isn't `AF_UNIX` (the family D-Bus, AT-SPI, and the local X11 socket all use anyway), so even a future bug can't make the daemon reach the network.
- AT-SPI access is inherently broad — it's the same mechanism a screen reader uses, so the daemon *can* see the menu structure of whatever app is focused. KheetSheet only ever reads menu/shortcut names and key bindings to render the overlay, and only for the currently active app; it doesn't monitor keystrokes, read document content, or retain anything about apps once you dismiss the overlay.

## Known Limitations

- Only apps that expose their menu via AT-SPI will show anything. Traditional Qt/KDE apps (Dolphin, Kate, Konsole, ...) generally work well. Many GTK4 apps (header-bar-only, no traditional menu bar) and Electron apps expose little or nothing. The overlay will say so rather than try to guess.
- Flatpak apps are matched by pid first, falling back to matching the AT-SPI app's name against the window's `resourceClass` — needed because every Flatpak app's D-Bus traffic goes through a per-instance `xdg-dbus-proxy`, so AT-SPI sees the proxy's pid for a window rather than the real app's.
- This recovers real shortcut data for Flatpak apps that expose a normal menu, but some (like Firefox) *only* populate a given submenu's accessible items after it's been opened once in the running session. They'll show as empty until you've clicked into each menu manually. Like an animal.
- Verified on Kubuntu/Plasma 6.6/Wayland and on Bazzite (Fedora Atomic) see [BAZZITE-README.md](BAZZITE-README.md) for the Fedora-specific notes.

## Unknown Limitations

- Localisation. I assume that as I'm tapping the accessibility features of the OS, the popover will display in the system language. Assuming though, we know where that gets us. Let me know if you spot any jankiness, I'll do my best auto translate dance and see what can be done.

## App Compatibility

A quick reference for popular apps. "Verified" means actually tested during development, everything else is inferred from the same underlying mechanism. If all that makes sense to you *and* an app you think should work doesn't, let me know and I'll see if I can fix it, but it might be a "I do weird things and don't tell AT-SPI about it" situation.

### Works Well

| App                                                 | Why                                                                                                                                                                                     |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dolphin                                             | Verified.                                                                                                                                                                               |
| Konsole                                             | Verified.                                                                                                                                                                               |
| Kate, Okular, KCalc, Krita                          | Same Qt/KDE Frameworks menu bar mechanism as Dolphin/Konsole.                                                                                                                           |
| LibreOffice                                         | Its own toolkit, but long-standing first-class AT-SPI accessibility support exposes a traditional menu bar                                                                              |
| Older GTK apps with a real menu bar (e.g. GIMP 2.x) | GTK's AT-SPI bridge exposes `GtkMenuBar` items with accelerators — the accelerator string needs parsing (GTK's format is different from Qt's), which is handled in `daemon/service.py`. |

### Partially Works

| App     | Why                                                                                                                                                                                                                                                                                                                                                                          |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Firefox | Flatpak sandboxing breaks the usual pid-based window match (falls back to a looser name match — see Known Limitations). On top of that, each submenu's items only populate in the accessible tree after you've opened that specific submenu at least once in the running session, shortcuts in menus you haven't opened yet won't show up until you've opened them manually. |

### Won't Work

| App                                      | Why                                                                                                                           |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| VS Code                                  | Electron renders its own menu as web content; there's no native menu widget for anything to read from, AT-SPI or otherwise.   |
| Obsidian                                 | Verified. Same reason, Electron.                                                                                              |
| Discord, Slack, Microsoft Teams, Spotify | Same Electron/Chromium-embedded pattern as VS Code and Obsidian.                                                              |
| GNOME Text Editor, Nautilus (Files)      | Same modern GTK4 "libadwaita" header-bar-only design as Baobab (verified), no traditional menu bar for AT-SPI to steal from.. |
| Steam                                    | Custom-rendered UI, not built with any standard accessible toolkit.                                                           |

## Architecture

- **`daemon/`** a Python D-Bus service (`com.kheetsheet.Daemon` at
  `/KheetSheet`) that walks AT-SPI's accessible tree for the active app and renders a translucent overlay (PyQt6) of its real shortcuts. Runs under `QT_QPA_PLATFORM=xcb` under KWin/Wayland, a native Qt-Wayland window doesn't honour always-on-top or absolute positioning, so the overlay runs as an XWayland client instead, where both work correctly.
- **`kwin-script/`** a KWin script (shock, horror) watching active-window changes, reporting them to the daemon via `NotifyActiveWindow`.
- **`systemd/kheetsheet-daemon.service`** the installed user unit (a
  template; `install.sh` writes the real one with the correct path baked in).
- **`install.sh`** installs both of the above; the global shortcut is a
  manual step (see Install section).
