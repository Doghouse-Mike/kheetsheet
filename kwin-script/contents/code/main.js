function notifyActiveWindow(window) {
    if (!window) {
        return;
    }
    callDBus(
        "com.kheetsheet.Daemon",
        "/KheetSheet",
        "com.kheetsheet.Daemon",
        "NotifyActiveWindow",
        window.pid,
        window.resourceClass ? window.resourceClass.toString() : "",
        window.caption ? window.caption.toString() : ""
    );
}

workspace.windowActivated.connect(notifyActiveWindow);
notifyActiveWindow(workspace.activeWindow);
