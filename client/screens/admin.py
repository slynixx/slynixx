"""Admin screen: Workshops / All vehicles / My account.

Admin actions are accented red.  The workshop-edit dialog (name + labour
rate) is one of the few small modals allowed by the UI conventions.
"""

import tkinter as tk

import netutil
import theme
import widgets
from api import ApiRequestError, ApiUnavailable
from screens.vehicle_dialog import VehiclePanel

TABS = ("Workshops", "All vehicles", "My account")


class AdminScreen(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=theme.BG)
        self.app = app
        self._content = None
        self._destroyed = False
        self.bind("<Destroy>", self._on_destroy, add="+")

        self.topbar = widgets.TopBar(
            self, "WORKBAY ADMIN", TABS, self._on_tab, accent=theme.RED
        )
        tk.Label(
            self.topbar.right, text=app.api.user["username"],
            bg=theme.BG_PANEL, fg=theme.RED, font=theme.font(10, bold=True),
        ).pack(side="left", padx=8)
        widgets.RoundedButton(
            self.topbar.right, "Log out", command=app.logout,
            colour=theme.BG_HOVER, bg=theme.BG_PANEL, size=9,
            padx=12, pady=5,
        ).pack(side="left")

        self.content = tk.Frame(self, bg=theme.BG)
        self.content.pack(fill="both", expand=True)
        self.search_debounce = netutil.Debouncer(self, delay_ms=300)
        self.topbar.select("Workshops")

    def _on_destroy(self, event):
        if event.widget is self:
            self._destroyed = True

    def _toast_error(self, exc):
        if self._destroyed:
            return
        if isinstance(exc, (ApiRequestError, ApiUnavailable)):
            widgets.toast(self.winfo_toplevel(), str(exc), colour=theme.RED)
        else:
            raise exc

    _tab_name = None

    def _on_tab(self, name):
        self._tab_name = name
        if name == "Workshops":
            self._show_workshops()
        elif name == "All vehicles":
            self._show_vehicles()
        else:
            self._show_account()

    def _swap(self, widget):
        if self._content is not None:
            self._content.destroy()
        self._content = widget
        self._content.pack(fill="both", expand=True)

    # --------------------------------------------------------- workshops

    def _show_workshops(self):
        frame = tk.Frame(self.content, bg=theme.BG)
        tk.Label(
            frame, text="Workshops", bg=theme.BG, fg=theme.FG,
            font=theme.font(16, bold=True),
        ).pack(anchor="w", padx=24, pady=(18, 8))
        self.workshops_list = widgets.ScrollableFrame(frame, bg=theme.BG)
        self.workshops_list.pack(fill="both", expand=True, padx=24,
                                 pady=(0, 12))
        self._swap(frame)
        self._load_workshops()

    def _load_workshops(self):
        api = self.app.api
        self.app.runner.run(
            api.list_workshops,
            on_success=self._render_workshops, on_error=self._toast_error,
        )

    def _render_workshops(self, workshops):
        if self._destroyed or not hasattr(self, "workshops_list"):
            return
        try:
            holder = self.workshops_list.inner
            holder.winfo_exists()
        except tk.TclError:
            return
        for child in holder.winfo_children():
            child.destroy()
        if not workshops:
            tk.Label(
                holder,
                text="No workshops registered yet. Workshops register "
                     "themselves from the sign-in screen.",
                bg=theme.BG, fg=theme.FG_FAINT, font=theme.font(11),
            ).pack(pady=40)
        for workshop in workshops:
            self._workshop_row(holder, workshop)
        self.workshops_list.bind_mousewheel_recursive()

    def _workshop_row(self, holder, workshop):
        row = tk.Frame(
            holder, bg=theme.BG_PANEL, padx=16, pady=12,
            highlightthickness=1, highlightbackground=theme.BORDER,
        )
        row.pack(fill="x", pady=3)
        # Fixed-width name column so the rate/vehicle info starts at the
        # same x in every row.
        tk.Label(
            row, text=workshop["name"], bg=theme.BG_PANEL, fg=theme.FG,
            font=theme.font(12, bold=True), width=22, anchor="w",
        ).pack(side="left")
        rate = workshop.get("labour_rate_cents") or 0
        tk.Label(
            row,
            text=f"labour {theme.format_money(rate)}/h    "
                 f"{workshop['open_count']} open / "
                 f"{workshop['vehicle_count']} total vehicles",
            bg=theme.BG_PANEL, fg=theme.FG_DIM, font=theme.font(10),
        ).pack(side="left", padx=16)

        widgets.RoundedButton(
            row, "Delete",
            command=lambda w=dict(workshop): self._delete_workshop(w),
            colour=theme.RED, bg=theme.BG_PANEL, size=9, padx=12, pady=5,
        ).pack(side="right", padx=4)
        widgets.RoundedButton(
            row, "Edit",
            command=lambda w=dict(workshop): self._edit_workshop(w),
            colour=theme.BG_HOVER, bg=theme.BG_PANEL, size=9,
            padx=12, pady=5,
        ).pack(side="right", padx=4)

    def _edit_workshop(self, workshop):
        dialog = tk.Toplevel(self)
        dialog.title("Edit workshop")
        dialog.configure(bg=theme.BG_PANEL, padx=24, pady=20)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.resizable(False, False)

        tk.Label(
            dialog, text=f"Edit {workshop['name']}", bg=theme.BG_PANEL,
            fg=theme.FG, font=theme.font(12, bold=True),
        ).pack(anchor="w", pady=(0, 10))

        widgets.field_label(dialog, "WORKSHOP NAME").pack(anchor="w")
        name_var = tk.StringVar(value=workshop["name"])
        widgets.styled_entry(dialog, name_var, width=28).pack(
            ipady=5, pady=(2, 10)
        )

        widgets.field_label(dialog, "LABOUR RATE (RAND PER HOUR)").pack(
            anchor="w"
        )
        rate = (workshop.get("labour_rate_cents") or 0) / 100
        rate_var = tk.StringVar(value=f"{rate:.2f}" if rate else "")
        widgets.styled_entry(dialog, rate_var, width=28).pack(
            ipady=5, pady=(2, 4)
        )

        error = tk.Label(
            dialog, text="", bg=theme.BG_PANEL, fg=theme.RED,
            font=theme.font(9),
        )
        error.pack(anchor="w")

        def save():
            name = name_var.get().strip()
            if not name:
                error.configure(text="Name cannot be blank.")
                return
            try:
                cents = theme.parse_money_to_cents(rate_var.get())
            except ValueError as exc:
                error.configure(text=str(exc))
                return
            api = self.app.api
            workshop_id = workshop["id"]

            def done(_result):
                dialog.destroy()
                self._load_workshops()
                widgets.toast(self.winfo_toplevel(), f"{name} updated")

            self.app.runner.run(
                lambda: api.update_workshop(
                    workshop_id, name=name, labour_rate_cents=cents
                ),
                on_success=done,
                on_error=lambda exc: error.configure(text=str(exc)),
            )

        buttons = tk.Frame(dialog, bg=theme.BG_PANEL)
        buttons.pack(pady=(10, 0))
        widgets.RoundedButton(
            buttons, "Save", command=save, colour=theme.RED,
            bg=theme.BG_PANEL,
        ).pack(side="left", padx=4)
        widgets.RoundedButton(
            buttons, "Cancel", command=dialog.destroy,
            colour=theme.BG_HOVER, bg=theme.BG_PANEL,
        ).pack(side="left", padx=4)

        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + 160
        dialog.geometry(f"+{x}+{y}")

    def _delete_workshop(self, workshop):
        from tkinter import messagebox

        if not messagebox.askyesno(
            "Delete workshop",
            f"Delete '{workshop['name']}' and ALL its vehicles, parts and "
            "users?\n\nThis cannot be undone.",
            parent=self.winfo_toplevel(),
        ):
            return
        api = self.app.api
        workshop_id = workshop["id"]
        self.app.runner.run(
            lambda: api.delete_workshop(workshop_id),
            on_success=lambda _r: self._load_workshops(),
            on_error=self._toast_error,
        )

    # ------------------------------------------------------ all vehicles

    def _show_vehicles(self):
        frame = tk.Frame(self.content, bg=theme.BG)
        tk.Label(
            frame, text="All vehicles", bg=theme.BG, fg=theme.FG,
            font=theme.font(16, bold=True),
        ).pack(anchor="w", padx=24, pady=(18, 8))

        search_row = tk.Frame(frame, bg=theme.BG)
        search_row.pack(fill="x", padx=24, pady=(0, 8))
        self.search_var = tk.StringVar()
        entry = widgets.styled_entry(search_row, self.search_var, width=32)
        entry.pack(side="left", ipady=5)
        tk.Label(
            search_row, text="Search every workshop's vehicles",
            bg=theme.BG, fg=theme.FG_FAINT, font=theme.font(9),
        ).pack(side="left", padx=10)
        self.search_var.trace_add(
            "write",
            lambda *a: self.search_debounce.call(self._load_vehicles),
        )

        self.vehicles_list = widgets.ScrollableFrame(frame, bg=theme.BG)
        self.vehicles_list.pack(fill="both", expand=True, padx=24,
                                pady=(0, 12))
        self._swap(frame)
        self._load_vehicles()

    def _load_vehicles(self):
        api = self.app.api
        query = self.search_var.get().strip()
        self.app.runner.run(
            lambda: api.list_vehicles(scope="all", query=query),
            on_success=self._render_vehicles, on_error=self._toast_error,
        )

    def _render_vehicles(self, vehicles):
        if self._destroyed or not hasattr(self, "vehicles_list"):
            return
        try:
            holder = self.vehicles_list.inner
            holder.winfo_exists()
        except tk.TclError:
            return
        for child in holder.winfo_children():
            child.destroy()
        if not vehicles:
            tk.Label(
                holder, text="No matching vehicles.", bg=theme.BG,
                fg=theme.FG_FAINT, font=theme.font(11),
            ).pack(pady=40)
        for vehicle in vehicles:
            self._vehicle_row(holder, vehicle)
        self.vehicles_list.bind_mousewheel_recursive()

    def _vehicle_row(self, holder, vehicle):
        row = tk.Frame(
            holder, bg=theme.BG_PANEL, padx=14, pady=10,
            highlightthickness=1, highlightbackground=theme.BORDER,
            cursor="hand2",
        )
        row.pack(fill="x", pady=3)
        plate = tk.Label(
            row, text=vehicle["registration"], bg=theme.AMBER,
            fg=theme.PLATE_TEXT, font=theme.plate_font(11), padx=6, pady=2,
            cursor="hand2", width=10, anchor="center",
        )
        plate.pack(side="left")
        plate.bind(
            "<Button-1>",
            lambda e, r=vehicle["registration"]: self._copy_reg(r),
        )
        bits = []
        if vehicle.get("year"):
            bits.append(str(vehicle["year"]))
        if vehicle.get("make"):
            bits.append(vehicle["make"])
        if vehicle.get("customer"):
            bits.append(vehicle["customer"])
        mid = tk.Frame(row, bg=theme.BG_PANEL)
        mid.pack(side="left", padx=14, fill="x", expand=True)
        line = tk.Label(
            mid, text="   ".join(bits), bg=theme.BG_PANEL, fg=theme.FG,
            font=theme.font(11, bold=True), anchor="w",
        )
        line.pack(fill="x")
        sub = tk.Label(
            mid,
            text=f"{vehicle['workshop_name']}   \u2022   "
                 + (vehicle.get("job") or "No repair items"),
            bg=theme.BG_PANEL, fg=theme.FG_DIM, font=theme.font(9),
            anchor="w",
        )
        sub.pack(fill="x")

        totals = theme.vehicle_totals(
            vehicle.get("parts", []),
            vehicle.get("labour_hours", 0),
            vehicle.get("labour_rate_cents", 0),
        )
        tk.Label(
            row, text=theme.format_money(totals["total"]),
            bg=theme.BG_PANEL, fg=theme.AMBER, font=theme.font(11, bold=True),
            width=11, anchor="e",
        ).pack(side="right", padx=12)
        tk.Label(
            row, text="DONE" if vehicle.get("status") == "done" else "",
            bg=theme.BG_PANEL, fg=theme.TEAL,
            font=theme.font(9, bold=True), width=5, anchor="e",
        ).pack(side="right")

        open_vehicle = lambda e, i=vehicle["id"]: self._open_vehicle(i)
        for widget in (row, mid, line, sub):
            widget.bind("<Button-1>", open_vehicle)

    def _copy_reg(self, registration):
        widgets.copy_to_clipboard(self.winfo_toplevel(), registration)
        widgets.toast(self.winfo_toplevel(), "Registration copied")

    def _open_vehicle(self, vehicle_id):
        back = lambda: self._on_tab(self._tab_name or "All vehicles")
        self._swap(VehiclePanel(self.content, self.app, vehicle_id, back))

    # --------------------------------------------------------- account

    def _show_account(self):
        frame = tk.Frame(self.content, bg=theme.BG)
        tk.Label(
            frame, text="My account", bg=theme.BG, fg=theme.FG,
            font=theme.font(16, bold=True),
        ).pack(anchor="w", padx=24, pady=(18, 8))
        card = tk.Frame(
            frame, bg=theme.BG_PANEL, padx=24, pady=20,
            highlightthickness=1, highlightbackground=theme.BORDER,
        )
        card.pack(anchor="w", padx=24)
        tk.Label(
            card, text=f"Signed in as {self.app.api.user['username']} (admin)",
            bg=theme.BG_PANEL, fg=theme.FG, font=theme.font(11, bold=True),
        ).pack(anchor="w", pady=(0, 12))

        widgets.field_label(card, "CURRENT PASSWORD").pack(anchor="w")
        self.current_pw = tk.StringVar()
        widgets.styled_entry(
            card, self.current_pw, width=26, show="\u2022"
        ).pack(ipady=5, pady=(2, 8), anchor="w")

        widgets.field_label(card, "NEW PASSWORD").pack(anchor="w")
        self.new_pw = tk.StringVar()
        widgets.styled_entry(
            card, self.new_pw, width=26, show="\u2022"
        ).pack(ipady=5, pady=(2, 8), anchor="w")

        self.account_msg = tk.Label(
            card, text="", bg=theme.BG_PANEL, fg=theme.TEAL,
            font=theme.font(9),
        )
        self.account_msg.pack(anchor="w")
        widgets.RoundedButton(
            card, "Change password", command=self._change_password,
            colour=theme.RED, bg=theme.BG_PANEL,
        ).pack(anchor="w", pady=(8, 0))
        tk.Label(
            card,
            text="Change the default admin password (admin123) as soon "
                 "as the app is in use.",
            bg=theme.BG_PANEL, fg=theme.FG_FAINT, font=theme.font(9),
        ).pack(anchor="w", pady=(10, 0))
        self._swap(frame)

    def _change_password(self):
        current = self.current_pw.get()
        new = self.new_pw.get()
        if not current or not new:
            self.account_msg.configure(
                text="Fill in both fields.", fg=theme.RED
            )
            return
        api = self.app.api

        def done(_result):
            if self._destroyed:
                return
            self.current_pw.set("")
            self.new_pw.set("")
            self.account_msg.configure(
                text="Password changed.", fg=theme.TEAL
            )

        def fail(exc):
            if self._destroyed:
                return
            self.account_msg.configure(text=str(exc), fg=theme.RED)

        self.app.runner.run(
            lambda: api.change_password(current, new),
            on_success=done, on_error=fail,
        )
