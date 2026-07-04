"""Background-thread helpers for the Tkinter client.

THE RULE: never touch a widget from a worker thread.  Workers must only
receive plain data (extract widget values on the main thread first) and
all UI updates happen in on_success / on_error, which this module always
delivers on the Tk main thread via a queue polled with `after`.
"""

import queue
import threading
import traceback


class AsyncRunner:
    def __init__(self, root, poll_ms=50):
        self.root = root
        self._queue = queue.Queue()
        self._poll_ms = poll_ms
        self._closed = False
        self._poll()

    def close(self):
        self._closed = True

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                callback, arg = self._queue.get_nowait()
                try:
                    callback(arg)
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        try:
            self.root.after(self._poll_ms, self._poll)
        except Exception:
            self._closed = True

    def run(self, work, on_success=None, on_error=None):
        """Run `work()` on a daemon thread; deliver its return value to
        on_success(result) or the exception to on_error(exc) on the main
        thread."""

        def worker():
            try:
                result = work()
            except Exception as exc:
                if on_error:
                    self._queue.put((on_error, exc))
                else:
                    traceback.print_exc()
                return
            if on_success:
                self._queue.put((on_success, result))

        threading.Thread(target=worker, daemon=True).start()


class Debouncer:
    """Delay a callback until the user stops typing."""

    def __init__(self, root, delay_ms=300):
        self.root = root
        self.delay_ms = delay_ms
        self._pending = None

    def call(self, callback):
        self.cancel()
        self._pending = self.root.after(self.delay_ms, callback)

    def cancel(self):
        if self._pending is not None:
            try:
                self.root.after_cancel(self._pending)
            except Exception:
                pass
            self._pending = None
