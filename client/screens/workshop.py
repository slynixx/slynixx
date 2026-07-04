"""Workshop screen: Current jobs / Vehicle history / Settings tabs, with
the embedded book-in and vehicle panels swapped into the content area."""

import tkinter as tk

import netutil
import theme
import widgets
from api import ApiRequestError, ApiUnavailable
from screens.vehicle_dialog import BookInPanel, VehiclePanel

TABS = ("Current jobs", "Vehicle history", "Settings")


class WorkshopScreen(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=theme.BG)
        self.app = app
        self.workshop = None
        self._content = None
        self._destroyed = False
        self.bind("<Destroy>", self._on_destroy, add="+")

        self.topbar = widgets.TopBar(self, "WORKBAY", TABS, self._on_tab)
        tk.Label(
            self.topbar.right, text=app.api.user["username"],
            bg=theme.BG_PANEL, fg=theme.FG_DIM, font=theme.font(10),
        ).pack(side="left", padx=8)
        widgets.RoundedButton(
            self.topbar.right, "Log out", command=app.logout,
            colour=theme.BG_HOVER, bg=theme.BG_PANEL, size=9,
            padx=12, pady=5,
        ).pack(side="left")

        self.content = tk.Frame(self, bg=theme.BG)
        self.content.pack(fill="both", expand=True)

        self.search_debounce = netutil.Debouncer(self, delay_ms=300)
        self._load_workshop()
        self.topbar.select("Current jobs")

    def _on_destroy(self, event):
        if event.widget is self:
            self._destroyed = True

    def _load_workshop(self):
        api = self.app.api
        workshop_id = api.user["workshop_id"]

        def done(workshop):
            if self._destroyed:
                return
            self.workshop = workshop
            if self._tab_name == "Settings":
                self._show_settings()

        self.app.runner.run(
            lambda: api.get_workshop(workshop_id),
            on_success=done, on_error=self._toast_error,
        )

    def _toast_error(self, exc):
        if self._destroyed:
            return
        if isinstance(exc, (ApiRequestError, ApiUnavailable)):
            widgets.toast(self.winfo_toplevel(), str(exc), colour=theme.RED)
        else:
            raise exc

    # -------------------------------------------------------------- tabs

    _tab_name = None

    def _on_tab(self, name):
        self._tab_name = name
        if name == "Current jobs":
            self._show_jobs()
        elif name == "Vehicle history":
            self._show_history()
        else:
            self._show_settings()

    def _swap(self, widget):
        if self._content is not None:
            self._content.destroy()
        self._content = widget
        self._content.pack(fill="both", expand=True)

    # ----------------------------------------------------- current jobs

    def _show_jobs(self):
        frame = tk.Frame(self.content, bg=theme.BG)
        header = tk.Frame(frame, bg=theme.BG)
        header.pack(fill="x", padx=24, pady=(18, 8))
        tk.Label(
            header, text="Current jobs", bg=theme.BG, fg=theme.FG,
            font=theme.font(16, bold=True),
        ).pack(side="left")
        widgets.RoundedButton(
            header, "+ Book vehicle in", command=self._show_book_in,
            colour=theme.RUST, bg=theme.BG,
        ).pack(side="right")

        self.jobs_list = widgets.ScrollableFrame(frame, bg=theme.BG)
        self.jobs_list.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        self._swap(frame)
        self._load_jobs()

    def _load_jobs(self):
        api = self.app.api
        self.app.runner.run(
            lambda: api.list_vehicles(scope="open"),
            on_success=self._render_jobs, on_error=self._toast_error,
        )

    def _render_jobs(self, vehicles):
        if self._destroyed or not hasattr(self, "jobs_list"):
            return
        holder = self.jobs_list.inner
        for child in holder.winfo_children():
            child.destroy()
        if not vehicles:
            tk.Label(
                holder, text="No vehicles booked in. "
                             "Use '+ Book vehicle in' to add the first one.",
                bg=theme.BG, fg=theme.FG_FAINT, font=theme.font(11),
            ).pack(pady=40)
        for vehicle in vehicles:
            self._vehicle_row(holder, vehicle)
        self.jobs_list.bind_mousewheel_recursive()

    def _vehicle_row(self, holder, vehicle, show_workshop=False):
        row = tk.Frame(
            holder, bg=theme.BG_PANEL, padx=14, pady=10,
            highlightthickness=1, highlightbackground=theme.BORDER,
            cursor="hand2",
        )
        row.pack(fill="x", pady=3)

        plate = tk.Label(
            row, text=" " + vehicle["registration"] + " ", bg=theme.AMBER,
            fg=theme.PLATE_TEXT, font=theme.plate_font(11), padx=6, pady=2,
            cursor="hand2",
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
        if show_workshop and vehicle.get("workshop_name"):
            bits.append("[" + vehicle["workshop_name"] + "]")
        mid = tk.Frame(row, bg=theme.BG_PANEL)
        mid.pack(side="left", padx=14, fill="x", expand=True)
        top_line = tk.Label(
            mid, text="   ".join(bits), bg=theme.BG_PANEL, fg=theme.FG,
            font=theme.font(11, bold=True), anchor="w",
        )
        top_line.pack(fill="x")
        job = vehicle.get("job") or "No repair items"
        sub = tk.Label(
            mid, text=job, bg=theme.BG_PANEL, fg=theme.FG_DIM,
            font=theme.font(9), anchor="w",
        )
        sub.pack(fill="x")

        done_text = f"{vehicle['item_done_count']}/{vehicle['item_count']}"
        badge_colour = (
            theme.TEAL
            if vehicle["item_count"]
            and vehicle["item_done_count"] == vehicle["item_count"]
            else theme.FG_DIM
        )
        status_bits = f"items {done_text}   parts {vehicle['part_count']}"
        if vehicle.get("status") == "done":
            status_bits += "   DONE"
        tk.Label(
            row, text=status_bits, bg=theme.BG_PANEL, fg=badge_colour,
            font=theme.font(9, bold=True),
        ).pack(side="right")

        totals = theme.vehicle_totals(
            vehicle.get("parts", []),
            vehicle.get("labour_hours", 0),
            vehicle.get("labour_rate_cents", 0),
        )
        tk.Label(
            row, text=theme.format_money(totals["total"]), bg=theme.BG_PANEL,
            fg=theme.AMBER, font=theme.font(11, bold=True),
        ).pack(side="right", padx=12)

        open_vehicle = lambda e, i=vehicle["id"]: self._open_vehicle(i)
        for widget in (row, mid, top_line, sub):
            widget.bind("<Button-1>", open_vehicle)

    def _copy_reg(self, registration):
        widgets.copy_to_clipboard(self.winfo_toplevel(), registration)
        widgets.toast(self.winfo_toplevel(), "Registration copied")

    def _open_vehicle(self, vehicle_id):
        back = lambda: self._on_tab(self._tab_name or "Current jobs")
        self._swap(VehiclePanel(self.content, self.app, vehicle_id, back))

    def _show_book_in(self):
        def done(vehicle):
            self._open_vehicle(vehicle["id"])
            widgets.toast(
                self.winfo_toplevel(),
                f"{vehicle['registration']} booked in",
            )

        self._swap(BookInPanel(
            self.content, self.app, on_done=done,
            on_back=lambda: self._on_tab("Current jobs"),
        ))

    # --------------------------------------------------------- history

    def _show_history(self):
        frame = tk.Frame(self.content, bg=theme.BG)
        header = tk.Frame(frame, bg=theme.BG)
        header.pack(fill="x", padx=24, pady=(18, 8))
        tk.Label(
            header, text="Vehicle history", bg=theme.BG, fg=theme.FG,
            font=theme.font(16, bold=True),
        ).pack(side="left")

        search_row = tk.Frame(frame, bg=theme.BG)
        search_row.pack(fill="x", padx=24, pady=(0, 8))
        self.search_var = tk.StringVar()
        entry = widgets.styled_entry(search_row, self.search_var, width=32)
        entry.pack(side="left", ipady=5)
        tk.Label(
            search_row,
            text="Search by registration, customer or job",
            bg=theme.BG, fg=theme.FG_FAINT, font=theme.font(9),
        ).pack(side="left", padx=10)
        self.search_var.trace_add(
            "write",
            lambda *a: self.search_debounce.call(self._load_history),
        )
        entry.focus_set()

        self.history_list = widgets.ScrollableFrame(frame, bg=theme.BG)
        self.history_list.pack(fill="both", expand=True, padx=24,
                               pady=(0, 12))
        self._swap(frame)
        self._load_history()

    def _load_history(self):
        api = self.app.api
        query = self.search_var.get().strip()
        self.app.runner.run(
            lambda: api.list_vehicles(scope="all", query=query),
            on_success=self._render_history, on_error=self._toast_error,
        )

    def _render_history(self, vehicles):
        if self._destroyed or not hasattr(self, "history_list"):
            return
        try:
            holder = self.history_list.inner
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
        self.history_list.bind_mousewheel_recursive()

    # --------------------------------------------------------- settings

    def _show_settings(self):
        frame = tk.Frame(self.content, bg=theme.BG)
        tk.Label(
            frame, text="Settings", bg=theme.BG, fg=theme.FG,
            font=theme.font(16, bold=True),
        ).pack(anchor="w", padx=24, pady=(18, 8))

        card = tk.Frame(
            frame, bg=theme.BG_PANEL, padx=24, pady=20,
            highlightthickness=1, highlightbackground=theme.BORDER,
        )
        card.pack(anchor="w", padx=24)

        name = self.workshop["name"] if self.workshop else "..."
        tk.Label(
            card, text=f"Workshop: {name}", bg=theme.BG_PANEL, fg=theme.FG,
            font=theme.font(12, bold=True),
        ).pack(anchor="w", pady=(0, 12))

        rate_cents = (self.workshop or {}).get("labour_rate_cents") or 0
        widgets.field_label(card, "LABOUR RATE (RAND PER HOUR)").pack(
            anchor="w"
        )
        row = tk.Frame(card, bg=theme.BG_PANEL)
        row.pack(anchor="w", pady=(2, 4))
        self.rate_var = tk.StringVar(
            value=f"{rate_cents / 100:.2f}" if rate_cents else ""
        )
        entry = widgets.styled_entry(row, self.rate_var, width=12)
        entry.pack(side="left", ipady=5)
        widgets.RoundedButton(
            row, "Save rate", command=self._save_rate, colour=theme.RUST,
            bg=theme.BG_PANEL, size=10, padx=16, pady=6,
        ).pack(side="left", padx=10)
        entry.bind("<Return>", lambda e: self._save_rate())
        tk.Label(
            card,
            text="Labour cost on every job card = hours \u00d7 this rate.\n"
                 "Changing it updates totals everywhere, immediately.",
            bg=theme.BG_PANEL, fg=theme.FG_FAINT, font=theme.font(9),
            justify="left",
        ).pack(anchor="w", pady=(6, 14))

        # password change
        widgets.field_label(card, "CHANGE PASSWORD").pack(
            anchor="w", pady=(8, 2)
        )
        pw_row = tk.Frame(card, bg=theme.BG_PANEL)
        pw_row.pack(anchor="w")
        self.current_pw = tk.StringVar()
        self.new_pw = tk.StringVar()
        widgets.styled_entry(
            pw_row, self.current_pw, width=16, show="\u2022"
        ).pack(side="left", ipady=4)
        tk.Label(
            pw_row, text="\u2192", bg=theme.BG_PANEL, fg=theme.FG_DIM,
        ).pack(side="left", padx=6)
        widgets.styled_entry(
            pw_row, self.new_pw, width=16, show="\u2022"
        ).pack(side="left", ipady=4)
        widgets.RoundedButton(
            pw_row, "Change", command=self._change_password,
            colour=theme.BG_HOVER, bg=theme.BG_PANEL, size=9,
            padx=12, pady=5,
        ).pack(side="left", padx=10)
        tk.Label(
            card, text="current password \u2192 new password",
            bg=theme.BG_PANEL, fg=theme.FG_FAINT, font=theme.font(8),
        ).pack(anchor="w")

        self._swap(frame)
        if self.workshop is None:
            self._load_workshop()

    def _save_rate(self):
        text = self.rate_var.get()
        try:
            cents = theme.parse_money_to_cents(text)
        except ValueError as exc:
            widgets.toast(self.winfo_toplevel(), str(exc), colour=theme.RED)
            return
        api = self.app.api
        workshop_id = api.user["workshop_id"]

        def done(workshop):
            if self._destroyed:
                return
            self.workshop = workshop
            widgets.toast(
                self.winfo_toplevel(),
                f"Labour rate set to {theme.format_money(cents)}/h",
            )

        self.app.runner.run(
            lambda: api.update_workshop(workshop_id, labour_rate_cents=cents),
            on_success=done, on_error=self._toast_error,
        )

    def _change_password(self):
        current = self.current_pw.get()
        new = self.new_pw.get()
        if not current or not new:
            widgets.toast(
                self.winfo_toplevel(),
                "Fill in both password fields", colour=theme.RED,
            )
            return
        api = self.app.api

        def done(_result):
            if self._destroyed:
                return
            self.current_pw.set("")
            self.new_pw.set("")
            widgets.toast(self.winfo_toplevel(), "Password changed")

        self.app.runner.run(
            lambda: api.change_password(current, new),
            on_success=done, on_error=self._toast_error,
        )
