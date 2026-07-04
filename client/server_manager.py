"""Auto-start the Workbay server for single-PC use.

From source: spawn a hidden python subprocess running server/server.py
(no console window on Windows) and stop it when the client closes.

Frozen (PyInstaller onefile): spawning Python from a frozen exe is
unreliable, so instead load server/server.py out of sys._MEIPASS and run
it in-process on a daemon thread.
"""

import os
import subprocess
import sys


def is_frozen():
    return getattr(sys, "frozen", False)


def server_dir():
    if is_frozen():
        return os.path.join(sys._MEIPASS, "server")
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server")
    )


class ServerManager:
    """Starts the local server if nothing is listening yet, and stops it
    (subprocess mode only) when the client exits."""

    def __init__(self, port=8642):
        self.port = port
        self.process = None
        self.httpd = None
        self.started_by_us = False

    def ensure_running(self, api_client):
        """Return True if a server is (now) reachable."""
        try:
            api_client.ping(retry=False)
            return True
        except Exception:
            pass
        if is_frozen():
            self._start_in_process()
        else:
            self._start_subprocess()
        try:
            api_client.ping(retry=True)  # retries ~3s while it boots
            self.started_by_us = True
            return True
        except Exception:
            return False

    def _start_in_process(self):
        directory = server_dir()
        if directory not in sys.path:
            sys.path.insert(0, directory)
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "workbay_server", os.path.join(directory, "server.py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["workbay_server"] = module
        spec.loader.exec_module(module)
        self.httpd = module.run_in_thread(host="127.0.0.1", port=self.port)

    def _start_subprocess(self):
        script = os.path.join(server_dir(), "server.py")
        kwargs = {
            "cwd": server_dir(),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            # CREATE_NO_WINDOW keeps the server invisible even when the
            # client itself was started from a console python.exe.
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        self.process = subprocess.Popen(
            [sys.executable, script, str(self.port)], **kwargs
        )

    def stop(self):
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
            self.httpd = None
