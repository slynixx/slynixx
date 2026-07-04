"""Workbay entry point -- the whole app lives in this one program/exe.

Run with:  py -3 app.py               the workshop app (single-PC mode:
                                      auto-starts a hidden local server
                                      and stops it on close)
           py -3 app.py --server      LAN host mode: runs only the shared
                                      server with a small status window;
                                      other PCs point their Workbay at
                                      this PC's address

LAN clients: click the "Server:" link on the sign-in screen and enter the
host PC's address; the setting persists in client_config.json.

Errors are never silent: Tk callback exceptions and startup crashes show
a dialog and are appended to error.log in the Workbay data folder.
"""

import ctypes
import json
import os
import sys
import traceback

APP_NAME = "Workbay"


def data_dir():
    explicit = os.environ.get("WORKBAY_DB_DIR")
    if explicit:
        path = explicit
    else:
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = os.path.join(appdata, APP_NAME)
        else:
            path = os.path.join(
                os.path.expanduser("~"), ".local", "share", APP_NAME
            )
    os.makedirs(path, exist_ok=True)
    return path


def log_error(text):
    try:
        import datetime

        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(
            os.path.join(data_dir(), "error.log"), "a", encoding="utf-8"
        ) as f:
            f.write(f"\n[{stamp}]\n{text}\n")
    except Exception:
        pass


def load_config():
    path = os.path.join(data_dir(), "client_config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(config):
    path = os.path.join(data_dir(), "client_config.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception:
        log_error("Could not save client config:\n" + traceback.format_exc())


def enable_windows_dpi_awareness():
    """Ask Windows not to blur-scale us; keeps geometry crisp on HiDPI."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class WorkbayApp:
    def __init__(self):
        import tkinter as tk

        import api
        import netutil
        import server_manager
        import theme

        self.tk = tk
        self.config = load_config()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.configure(bg=theme.BG)
        self.root.minsize(980, 620)
        self._centre_window(1120, 700)
        self.root.report_callback_exception = self._on_tk_exception
        self._set_icon()

        self.runner = netutil.AsyncRunner(self.root)
        self.api = api.ApiClient(self.config.get("server") or api.DEFAULT_SERVER)
        self.server_manager = server_manager.ServerManager()
        self._current_screen = None

        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        if self._is_local_server():
            if not self.server_manager.ensure_running(self.api):
                self._fatal(
                    "Workbay could not start its local server.\n\n"
                    "Check error.log in the Workbay data folder:\n"
                    + data_dir()
                )
                return

        self.root.deiconify()
        self.show_login()

    # ------------------------------------------------------------ infra

    def _is_local_server(self):
        host = self.api.server.split("://")[-1].split(":")[0].strip()
        return host in ("127.0.0.1", "localhost", "")

    def _centre_window(self, width, height):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(width, screen_w - 40)
        height = min(height, screen_h - 80)
        x = max((screen_w - width) // 2, 0)
        y = max((screen_h - height) // 2 - 12, 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _set_icon(self):
        try:
            icon = os.path.join(assets_dir(), "workbay.ico")
            if os.path.exists(icon) and sys.platform == "win32":
                self.root.iconbitmap(icon)
        except Exception:
            pass

    def _on_tk_exception(self, exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log_error(text)
        try:
            from tkinter import messagebox

            messagebox.showerror(
                APP_NAME,
                f"Something went wrong:\n\n{exc}\n\n"
                f"Details were saved to error.log in\n{data_dir()}",
                parent=self.root,
            )
        except Exception:
            pass

    def _fatal(self, message):
        log_error(message)
        try:
            from tkinter import messagebox

            self.root.deiconify()
            messagebox.showerror(APP_NAME, message, parent=self.root)
        except Exception:
            pass
        self.root.destroy()

    def set_server(self, server):
        self.api.server = server
        self.config["server"] = server
        save_config(self.config)

    # ---------------------------------------------------------- screens

    def _swap_screen(self, factory):
        if self._current_screen is not None:
            self._current_screen.destroy()
        self._current_screen = factory()
        self._current_screen.pack(fill="both", expand=True)

    def show_login(self):
        from screens.login import LoginScreen

        self._swap_screen(lambda: LoginScreen(self.root, self))

    def show_workshop(self):
        from screens.workshop import WorkshopScreen

        self._swap_screen(lambda: WorkshopScreen(self.root, self))

    def show_admin(self):
        from screens.admin import AdminScreen

        self._swap_screen(lambda: AdminScreen(self.root, self))

    def on_logged_in(self):
        if self.api.user and self.api.user.get("role") == "admin":
            self.show_admin()
        else:
            self.show_workshop()

    def logout(self):
        self.runner.run(self.api.logout, on_success=lambda _r: self.show_login())

    def quit(self):
        try:
            self.server_manager.stop()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def assets_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "assets")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def lan_addresses():
    """Best-effort list of this PC's LAN IP addresses."""
    import socket

    addresses = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))  # no traffic actually sent
            addresses.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in addresses:
                addresses.append(ip)
    except OSError:
        pass
    return addresses


def run_server_mode(port):
    """LAN host mode: run only the shared server, with a small dark status
    window (the exe is --windowed, so there is no console to print to)."""
    import tkinter as tk

    import server_manager
    import theme
    import widgets

    module = server_manager.load_server_module()
    try:
        httpd = module.make_server("0.0.0.0", port)
    except OSError as exc:
        _startup_error_dialog(
            f"Workbay server could not start on port {port}.\n\n{exc}\n\n"
            "Is another Workbay (or its hidden server) already running "
            "on this PC?"
        )
        raise SystemExit(1)
    import threading

    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    root = tk.Tk()
    root.title("Workbay Server")
    root.configure(bg=theme.BG, padx=28, pady=24)
    root.resizable(False, False)

    tk.Label(
        root, text="WORKBAY SERVER", bg=theme.BG, fg=theme.RUST,
        font=theme.font(18, bold=True),
    ).pack(anchor="w")
    tk.Label(
        root, text=f"Running \u2022 sharing this PC's job book on port {port}",
        bg=theme.BG, fg=theme.TEAL, font=theme.font(11, bold=True),
    ).pack(anchor="w", pady=(4, 12))

    addresses = lan_addresses()
    connect_lines = "\n".join(
        f"    {ip}:{port}" for ip in addresses
    ) or "    (no LAN address found -- check the network)"
    tk.Label(
        root,
        text="Workshops on other PCs: open Workbay, click the\n"
             "'Server:' link on the sign-in screen and enter:\n"
             + connect_lines,
        bg=theme.BG, fg=theme.FG, font=theme.font(10), justify="left",
    ).pack(anchor="w")
    tk.Label(
        root, text=f"Database: {os.path.join(data_dir(), 'workbay.db')}",
        bg=theme.BG, fg=theme.FG_FAINT, font=theme.font(9),
    ).pack(anchor="w", pady=(10, 14))

    def stop():
        try:
            httpd.shutdown()
        except Exception:
            pass
        root.destroy()

    widgets.RoundedButton(
        root, "Stop server", command=stop, colour=theme.RED, bg=theme.BG,
    ).pack(anchor="w")
    root.protocol("WM_DELETE_WINDOW", stop)
    root.mainloop()


def _startup_error_dialog(message):
    log_error(message)
    try:
        import tkinter as tk
        from tkinter import messagebox

        hidden = tk.Tk()
        hidden.withdraw()
        messagebox.showerror(APP_NAME, message)
        hidden.destroy()
    except Exception:
        pass


def main():
    enable_windows_dpi_awareness()
    args = sys.argv[1:]
    if "--server" in args:
        port = 8642
        for arg in args:
            if arg.isdigit():
                port = int(arg)
        try:
            run_server_mode(port)
        except SystemExit:
            raise
        except Exception:
            text = traceback.format_exc()
            log_error(text)
            _startup_error_dialog(
                "Workbay server failed to start.\n\n"
                f"{text.splitlines()[-1]}\n\n"
                f"Full details in error.log in\n{data_dir()}"
            )
            raise SystemExit(1)
        return
    try:
        app = WorkbayApp()
    except Exception:
        text = traceback.format_exc()
        log_error(text)
        _startup_error_dialog(
            "Workbay failed to start.\n\n"
            f"{text.splitlines()[-1]}\n\n"
            f"Full details in error.log in\n{data_dir()}"
        )
        raise SystemExit(1)
    app.run()


if __name__ == "__main__":
    main()
