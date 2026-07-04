"""Workbay client entry point.

Run with:  py -3 app.py     (or pythonw app.py for no console)

Single-PC mode: auto-starts a hidden local server and stops it on close.
LAN mode: point the client at another machine via the "Server address"
link on the login screen; the setting persists in client_config.json.

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


def main():
    enable_windows_dpi_awareness()
    try:
        app = WorkbayApp()
    except Exception:
        text = traceback.format_exc()
        log_error(text)
        try:
            import tkinter as tk
            from tkinter import messagebox

            hidden = tk.Tk()
            hidden.withdraw()
            messagebox.showerror(
                APP_NAME,
                "Workbay failed to start.\n\n"
                f"{text.splitlines()[-1]}\n\n"
                f"Full details in error.log in\n{data_dir()}",
            )
            hidden.destroy()
        except Exception:
            pass
        raise SystemExit(1)
    app.run()


if __name__ == "__main__":
    main()
