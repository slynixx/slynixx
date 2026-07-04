"""Login screen: sign in, register a new workshop, change server address."""

import tkinter as tk

import theme
import widgets
from api import ApiRequestError, ApiUnavailable


class LoginScreen(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=theme.BG)
        self.app = app
        self._registering = False

        outer = tk.Frame(self, bg=theme.BG)
        outer.place(relx=0.5, rely=0.45, anchor="center")

        tk.Label(
            outer, text="WORKBAY", bg=theme.BG, fg=theme.RUST,
            font=theme.font(30, bold=True),
        ).pack(pady=(0, 2))
        tk.Label(
            outer, text="Vehicle & parts job book", bg=theme.BG,
            fg=theme.FG_DIM, font=theme.font(11),
        ).pack(pady=(0, 22))

        self.card = tk.Frame(
            outer, bg=theme.BG_PANEL, padx=34, pady=28,
            highlightthickness=1, highlightbackground=theme.BORDER,
        )
        self.card.pack()

        self.heading = tk.Label(
            self.card, text="Sign in", bg=theme.BG_PANEL, fg=theme.FG,
            font=theme.font(15, bold=True),
        )
        self.heading.grid(row=0, column=0, sticky="w", pady=(0, 14))

        self.workshop_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        self.workshop_label = widgets.field_label(self.card, "WORKSHOP NAME")
        self.workshop_entry = widgets.styled_entry(
            self.card, self.workshop_var, width=30
        )

        widgets.field_label(self.card, "USERNAME").grid(
            row=3, column=0, sticky="w"
        )
        self.username_entry = widgets.styled_entry(
            self.card, self.username_var, width=30
        )
        self.username_entry.grid(row=4, column=0, pady=(2, 12), ipady=5)

        widgets.field_label(self.card, "PASSWORD").grid(
            row=5, column=0, sticky="w"
        )
        self.password_entry = widgets.styled_entry(
            self.card, self.password_var, width=30, show="\u2022"
        )
        self.password_entry.grid(row=6, column=0, pady=(2, 6), ipady=5)

        self.error_label = tk.Label(
            self.card, text="", bg=theme.BG_PANEL, fg=theme.RED,
            font=theme.font(10), wraplength=260, justify="left",
        )
        self.error_label.grid(row=7, column=0, sticky="w")

        self.submit = widgets.RoundedButton(
            self.card, "Sign in", command=self._submit, colour=theme.RUST,
            padx=40, bg=theme.BG_PANEL,
        )
        self.submit.grid(row=8, column=0, pady=(12, 4))

        self.toggle_label = tk.Label(
            self.card, text="New here?  Register a workshop",
            bg=theme.BG_PANEL, fg=theme.TEAL, font=theme.font(10, bold=True),
            cursor="hand2",
        )
        self.toggle_label.grid(row=9, column=0, pady=(10, 0))
        self.toggle_label.bind("<Button-1>", lambda e: self._toggle_mode())

        server_label = tk.Label(
            outer, text=f"Server: {self.app.api.server}", bg=theme.BG,
            fg=theme.FG_FAINT, font=theme.font(9), cursor="hand2",
        )
        server_label.pack(pady=(14, 0))
        server_label.bind("<Button-1>", lambda e: self._server_dialog())
        self.server_label = server_label

        for entry in (self.username_entry, self.password_entry,
                      self.workshop_entry):
            entry.bind("<Return>", lambda e: self._submit())
        self.after(100, self.username_entry.focus_set)

    # ------------------------------------------------------------ modes

    def _toggle_mode(self):
        self._registering = not self._registering
        self.error_label.configure(text="")
        if self._registering:
            self.heading.configure(text="Register a workshop")
            self.workshop_label.grid(row=1, column=0, sticky="w")
            self.workshop_entry.grid(row=2, column=0, pady=(2, 12), ipady=5)
            self.submit.set_text("Register")
            self.toggle_label.configure(
                text="Already registered?  Sign in instead"
            )
            self.workshop_entry.focus_set()
        else:
            self.heading.configure(text="Sign in")
            self.workshop_label.grid_forget()
            self.workshop_entry.grid_forget()
            self.submit.set_text("Sign in")
            self.toggle_label.configure(
                text="New here?  Register a workshop"
            )
            self.username_entry.focus_set()

    # ----------------------------------------------------------- submit

    def _submit(self):
        # Extract values on the main thread -- never in the worker.
        username = self.username_var.get().strip()
        password = self.password_var.get()
        workshop = self.workshop_var.get().strip()
        registering = self._registering
        self.error_label.configure(text="")

        if not username or not password or (registering and not workshop):
            self.error_label.configure(text="Please fill in every field.")
            return

        api = self.app.api

        def work():
            if registering:
                return api.register(workshop, username, password)
            return api.login(username, password)

        self.app.runner.run(
            work,
            on_success=lambda _r: self.app.on_logged_in(),
            on_error=self._on_error,
        )

    def _on_error(self, exc):
        if isinstance(exc, (ApiRequestError, ApiUnavailable)):
            self.error_label.configure(text=str(exc))
        else:
            raise exc

    # ---------------------------------------------- server address modal

    def _server_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Server address")
        dialog.configure(bg=theme.BG_PANEL, padx=24, pady=20)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.resizable(False, False)

        tk.Label(
            dialog, text="Workbay server address", bg=theme.BG_PANEL,
            fg=theme.FG, font=theme.font(12, bold=True),
        ).pack(anchor="w")
        tk.Label(
            dialog,
            text="Use 127.0.0.1:8642 for this PC, or the host PC's\n"
                 "address (e.g. 192.168.0.10:8642) to share on the LAN.",
            bg=theme.BG_PANEL, fg=theme.FG_DIM, font=theme.font(9),
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        var = tk.StringVar(value=self.app.api.server)
        entry = widgets.styled_entry(dialog, var, width=32)
        entry.pack(ipady=5)
        entry.focus_set()

        def apply():
            value = var.get().strip()
            if value:
                self.app.set_server(value)
                self.server_label.configure(text=f"Server: {value}")
            dialog.destroy()

        row = tk.Frame(dialog, bg=theme.BG_PANEL)
        row.pack(pady=(14, 0))
        widgets.RoundedButton(
            row, "Save", command=apply, colour=theme.RUST, bg=theme.BG_PANEL,
        ).pack(side="left", padx=4)
        widgets.RoundedButton(
            row, "Cancel", command=dialog.destroy, colour=theme.BG_HOVER,
            bg=theme.BG_PANEL,
        ).pack(side="left", padx=4)
        entry.bind("<Return>", lambda e: apply())

        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + 200
        dialog.geometry(f"+{x}+{y}")
