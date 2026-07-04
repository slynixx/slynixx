"""Embedded vehicle panels.

No popup windows for main flows: BookInPanel (book a vehicle in) and
VehiclePanel (job card with items, parts and invoice totals) are plain
frames the parent screen swaps into its content area, each with a
"back to list" button.
"""

import tkinter as tk

import theme
import widgets
from api import ApiRequestError, ApiUnavailable

STATUS_COLOURS = {
    "Ordered": theme.AMBER,
    "Arrived": theme.TEAL,
    "Fitted": theme.FG_DIM,
}
NEXT_STATUS = {"Ordered": "Arrived", "Arrived": "Fitted", "Fitted": "Ordered"}


class BookInPanel(tk.Frame):
    """Embedded 'book in a vehicle' form."""

    def __init__(self, parent, app, on_done, on_back, workshop_id=None):
        super().__init__(parent, bg=theme.BG)
        self.app = app
        self.on_done = on_done
        self.workshop_id = workshop_id  # admin passes this; workshops don't

        header = tk.Frame(self, bg=theme.BG)
        header.pack(fill="x", padx=24, pady=(18, 6))
        widgets.RoundedButton(
            header, "\u2190 Back to list", command=on_back,
            colour=theme.BG_HOVER, bg=theme.BG, size=10, padx=12, pady=6,
        ).pack(side="left")
        tk.Label(
            header, text="Book in a vehicle", bg=theme.BG, fg=theme.FG,
            font=theme.font(16, bold=True),
        ).pack(side="left", padx=16)

        card = tk.Frame(
            self, bg=theme.BG_PANEL, padx=28, pady=24,
            highlightthickness=1, highlightbackground=theme.BORDER,
        )
        card.pack(padx=24, pady=10, anchor="w")

        self.reg_var = tk.StringVar()
        self.year_var = tk.StringVar()
        self.make_var = tk.StringVar()
        self.customer_var = tk.StringVar()
        self.phone_var = tk.StringVar()
        self.hours_var = tk.StringVar()

        grid = tk.Frame(card, bg=theme.BG_PANEL)
        grid.pack()

        def add_field(row, col, label, var, width=22):
            widgets.field_label(grid, label).grid(
                row=row, column=col, sticky="w", padx=8, pady=(8, 0)
            )
            entry = widgets.styled_entry(grid, var, width=width)
            entry.grid(row=row + 1, column=col, sticky="w", padx=8, ipady=5)
            return entry

        self.reg_entry = add_field(0, 0, "REGISTRATION *", self.reg_var)
        add_field(0, 1, "YEAR", self.year_var, width=10)
        add_field(0, 2, "MAKE / MODEL", self.make_var)
        add_field(2, 0, "CUSTOMER", self.customer_var)
        phone_entry = add_field(2, 1, "PHONE", self.phone_var)
        widgets.attach_phone_formatter(phone_entry, self.phone_var)
        add_field(2, 2, "LABOUR HOURS", self.hours_var, width=10)

        widgets.field_label(
            grid, "REPAIR ITEMS  (separate with commas, semicolons or new lines)"
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=8, pady=(14, 0))
        self.job_text = tk.Text(
            grid, height=3, width=64, bg=theme.BG_FIELD, fg=theme.FG,
            insertbackground=theme.FG, relief="flat", font=theme.font(11),
            highlightthickness=1, highlightbackground=theme.BORDER,
            highlightcolor=theme.RUST, wrap="word",
        )
        self.job_text.grid(row=5, column=0, columnspan=3, sticky="we",
                           padx=8, pady=(2, 4))

        self.error_label = tk.Label(
            card, text="", bg=theme.BG_PANEL, fg=theme.RED,
            font=theme.font(10), justify="left",
        )
        self.error_label.pack(anchor="w", pady=(6, 0))

        buttons = tk.Frame(card, bg=theme.BG_PANEL)
        buttons.pack(anchor="w", pady=(10, 0))
        widgets.RoundedButton(
            buttons, "Book vehicle in", command=self._save,
            colour=theme.RUST, bg=theme.BG_PANEL, padx=26,
        ).pack(side="left")
        widgets.RoundedButton(
            buttons, "Cancel", command=on_back, colour=theme.BG_HOVER,
            bg=theme.BG_PANEL,
        ).pack(side="left", padx=8)

        self.after(100, self.reg_entry.focus_set)

    def _save(self):
        fields = {
            "registration": self.reg_var.get().strip(),
            "year": self.year_var.get().strip(),
            "make": self.make_var.get().strip(),
            "customer": self.customer_var.get().strip(),
            "phone": self.phone_var.get().strip(),
            "labour_hours": self.hours_var.get().strip(),
            "job": self.job_text.get("1.0", "end").strip(),
        }
        if self.workshop_id:
            fields["workshop_id"] = self.workshop_id
        if not fields["registration"]:
            self.error_label.configure(text="Registration is required.")
            return
        api = self.app.api
        self.app.runner.run(
            lambda: api.create_vehicle(fields),
            on_success=lambda vehicle: self.on_done(vehicle),
            on_error=self._show_error,
        )

    def _show_error(self, exc):
        if isinstance(exc, (ApiRequestError, ApiUnavailable)):
            self.error_label.configure(text=str(exc))
        else:
            raise exc


class VehiclePanel(tk.Frame):
    """Embedded job card: vehicle details, repair items with tick-offs,
    parts (with in-place editing) and live invoice totals."""

    def __init__(self, parent, app, vehicle_id, on_back):
        super().__init__(parent, bg=theme.BG)
        self.app = app
        self.vehicle_id = vehicle_id
        self.on_back = on_back
        self.vehicle = None
        self._editing_part = None   # None = closed, 0 = new, else part dict
        self._destroyed = False

        self.scroll = widgets.ScrollableFrame(self, bg=theme.BG)
        self.scroll.pack(fill="both", expand=True)
        self.body = self.scroll.inner
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.refresh()

    def _on_destroy(self, event):
        if event.widget is self:
            self._destroyed = True

    # ------------------------------------------------------------- data

    def refresh(self):
        api = self.app.api
        vehicle_id = self.vehicle_id
        self.app.runner.run(
            lambda: api.get_vehicle(vehicle_id),
            on_success=self._on_loaded,
            on_error=self._show_error,
        )

    def _on_loaded(self, vehicle):
        if self._destroyed:
            return
        self.vehicle = vehicle
        self._render()

    def _show_error(self, exc):
        if self._destroyed:
            return
        if isinstance(exc, (ApiRequestError, ApiUnavailable)):
            widgets.toast(self.winfo_toplevel(), str(exc), colour=theme.RED)
        else:
            raise exc

    def _mutate(self, work):
        """Run an API mutation; the server answers with the fresh vehicle,
        which we re-render."""
        self.app.runner.run(
            work, on_success=self._on_loaded, on_error=self._show_error
        )

    # ----------------------------------------------------------- render

    def _render(self):
        for child in self.body.winfo_children():
            child.destroy()
        vehicle = self.vehicle

        header = tk.Frame(self.body, bg=theme.BG)
        header.pack(fill="x", padx=24, pady=(18, 8))
        widgets.RoundedButton(
            header, "\u2190 Back to list", command=self.on_back,
            colour=theme.BG_HOVER, bg=theme.BG, size=10, padx=12, pady=6,
        ).pack(side="left")

        plate = tk.Label(
            header, text=" " + vehicle["registration"] + " ",
            bg=theme.AMBER, fg=theme.PLATE_TEXT, font=theme.plate_font(15),
            padx=10, pady=4, cursor="hand2",
            highlightthickness=2, highlightbackground=theme.AMBER_DARK,
        )
        plate.pack(side="left", padx=16)
        plate.bind("<Button-1>", lambda e: self._copy_registration())

        summary_bits = []
        if vehicle.get("year"):
            summary_bits.append(str(vehicle["year"]))
        if vehicle.get("make"):
            summary_bits.append(vehicle["make"])
        tk.Label(
            header, text="  ".join(summary_bits), bg=theme.BG, fg=theme.FG,
            font=theme.font(13, bold=True),
        ).pack(side="left", padx=4)

        status_open = vehicle["status"] == "open"
        widgets.RoundedButton(
            header,
            "Mark job done" if status_open else "Reopen job",
            command=self._toggle_status,
            colour=theme.TEAL if status_open else theme.BG_HOVER,
            bg=theme.BG, size=10, padx=14, pady=6,
        ).pack(side="right")

        # customer strip
        strip = tk.Frame(self.body, bg=theme.BG)
        strip.pack(fill="x", padx=26, pady=(0, 8))
        info = []
        if vehicle.get("customer"):
            info.append(vehicle["customer"])
        if vehicle.get("phone"):
            info.append(vehicle["phone"])
        if not status_open:
            info.append("JOB DONE")
        tk.Label(
            strip, text="   \u2022   ".join(info) if info else "",
            bg=theme.BG, fg=theme.FG_DIM, font=theme.font(11),
        ).pack(side="left")

        columns = tk.Frame(self.body, bg=theme.BG)
        columns.pack(fill="both", expand=True, padx=24, pady=4)
        columns.columnconfigure(0, weight=3)
        columns.columnconfigure(1, weight=2)

        left = tk.Frame(columns, bg=theme.BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = tk.Frame(columns, bg=theme.BG)
        right.grid(row=0, column=1, sticky="nsew")

        self._render_items(left)
        self._render_parts(left)
        self._render_labour(right)
        self._render_totals(right)
        self.scroll.bind_mousewheel_recursive()

    # ------------------------------------------------------ repair items

    def _render_items(self, parent):
        card = self._card(parent, "REPAIR ITEMS")
        items = self.vehicle.get("items", [])
        if not items:
            tk.Label(
                card, text="No repair items yet.", bg=theme.BG_PANEL,
                fg=theme.FG_FAINT, font=theme.font(10),
            ).pack(anchor="w", pady=4)
        for item in items:
            row = tk.Frame(card, bg=theme.BG_PANEL)
            row.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=bool(item["done"]))
            box = tk.Checkbutton(
                row, variable=var, bg=theme.BG_PANEL,
                activebackground=theme.BG_PANEL, selectcolor=theme.BG_FIELD,
                fg=theme.TEAL, bd=0, highlightthickness=0,
                command=lambda i=item["id"], v=var: self._tick_item(i, v.get()),
            )
            box.pack(side="left")
            done = bool(item["done"])
            label = tk.Label(
                row, text=item["description"], bg=theme.BG_PANEL,
                fg=theme.FG_FAINT if done else theme.FG,
                font=theme.font(11),
            )
            if done:
                label.configure(font=_overstrike(11))
            label.pack(side="left", padx=4)
            remove = tk.Label(
                row, text="\u00d7", bg=theme.BG_PANEL, fg=theme.FG_FAINT,
                font=theme.font(12, bold=True), cursor="hand2", padx=8,
            )
            remove.pack(side="right")
            remove.bind(
                "<Button-1>", lambda e, i=item["id"]: self._delete_item(i)
            )

        add_row = tk.Frame(card, bg=theme.BG_PANEL)
        add_row.pack(fill="x", pady=(10, 2))
        self.new_item_var = tk.StringVar()
        entry = widgets.styled_entry(add_row, self.new_item_var, width=34)
        entry.pack(side="left", ipady=4)
        entry.bind("<Return>", lambda e: self._add_items())
        widgets.RoundedButton(
            add_row, "Add", command=self._add_items, colour=theme.RUST,
            bg=theme.BG_PANEL, size=10, padx=16, pady=5,
        ).pack(side="left", padx=8)
        tk.Label(
            card, text="Tip: 'brake pads, oil change; wheel alignment' "
                       "becomes three items.",
            bg=theme.BG_PANEL, fg=theme.FG_FAINT, font=theme.font(9),
        ).pack(anchor="w", pady=(4, 0))

    def _tick_item(self, item_id, done):
        api = self.app.api
        self._mutate(lambda: api.set_item_done(item_id, done))

    def _delete_item(self, item_id):
        api = self.app.api
        self._mutate(lambda: api.delete_item(item_id))

    def _add_items(self):
        text = self.new_item_var.get().strip()
        if not text:
            return
        api = self.app.api
        vehicle_id = self.vehicle_id
        self._mutate(lambda: api.add_items(vehicle_id, text))

    # -------------------------------------------------------------- parts

    # Parts table columns: (heading, minimum px, stretch weight, anchor).
    # Money columns are right-aligned so amounts line up on the decimal.
    PART_COLUMNS = (
        ("PART NO.", 72, 0, "w"),
        ("NAME", 120, 3, "w"),
        ("SUPPLIER", 90, 2, "w"),
        ("COST", 86, 0, "e"),
        ("DISC", 48, 0, "e"),
        ("NET", 86, 0, "e"),
        ("STATUS", 76, 0, "w"),
        ("", 34, 0, "e"),   # edit
        ("", 22, 0, "e"),   # delete
    )

    def _render_parts(self, parent):
        card = self._card(parent, "PARTS")
        parts = self.vehicle.get("parts", [])

        if parts:
            table = tk.Frame(card, bg=theme.BG_PANEL)
            table.pack(fill="x")
            for col, (heading, minsize, weight, anchor) in enumerate(
                self.PART_COLUMNS
            ):
                table.columnconfigure(col, minsize=minsize, weight=weight)
                tk.Label(
                    table, text=heading, bg=theme.BG_PANEL,
                    fg=theme.FG_FAINT, font=theme.font(8, bold=True),
                    anchor=anchor,
                ).grid(row=0, column=col, sticky="ew",
                       padx=(0, 8), pady=(0, 2))
            for index, part in enumerate(parts):
                self._render_part_row(table, part, index + 1)
        else:
            tk.Label(
                card, text="No parts yet.", bg=theme.BG_PANEL,
                fg=theme.FG_FAINT, font=theme.font(10),
            ).pack(anchor="w", pady=4)

        if self._editing_part is not None:
            self._render_part_editor(card)
        else:
            widgets.RoundedButton(
                card, "+ Add part", command=lambda: self._open_editor(0),
                colour=theme.RUST, bg=theme.BG_PANEL, size=10,
                padx=16, pady=6,
            ).pack(anchor="w", pady=(10, 2))

    def _render_part_row(self, table, part, grid_row):
        editing = (
            isinstance(self._editing_part, dict)
            and self._editing_part["id"] == part["id"]
        )
        bg = theme.BG_HOVER if editing else theme.BG_PANEL
        net = theme.part_net_cents(part)
        cells = (
            (part["part_number"], theme.FG, theme.font(10)),
            (part["name"], theme.FG, theme.font(10)),
            (part["supplier"], theme.FG_DIM, theme.font(10)),
            (theme.format_money(part["cost_cents"]), theme.AMBER,
             theme.font(10)),
            (f"{part['discount_pct']:g}%" if part["discount_pct"] else "-",
             theme.FG_DIM, theme.font(10)),
            (theme.format_money(net), theme.AMBER, theme.font(10)),
        )
        for col, (text, colour, font) in enumerate(cells):
            anchor = self.PART_COLUMNS[col][3]
            tk.Label(
                table, text=text, bg=bg, fg=colour, font=font,
                anchor=anchor,
            ).grid(row=grid_row, column=col, sticky="ew",
                   padx=(0, 8), pady=1)
        status = tk.Label(
            table, text=part["status"], bg=bg,
            fg=STATUS_COLOURS.get(part["status"], theme.FG),
            font=theme.font(9, bold=True), anchor="w", cursor="hand2",
        )
        status.grid(row=grid_row, column=6, sticky="ew", padx=(0, 8), pady=1)
        status.bind(
            "<Button-1>",
            lambda e, p=dict(part): self._advance_status(p),
        )
        edit = tk.Label(
            table, text="edit", bg=bg, fg=theme.TEAL,
            font=theme.font(9, bold=True), cursor="hand2", anchor="e",
        )
        edit.grid(row=grid_row, column=7, sticky="ew", padx=(0, 8), pady=1)
        edit.bind(
            "<Button-1>", lambda e, p=dict(part): self._open_editor(p)
        )
        remove = tk.Label(
            table, text="\u00d7", bg=bg, fg=theme.FG_FAINT,
            font=theme.font(11, bold=True), cursor="hand2", anchor="e",
        )
        remove.grid(row=grid_row, column=8, sticky="ew", pady=1)
        remove.bind(
            "<Button-1>", lambda e, i=part["id"]: self._delete_part(i)
        )

    def _advance_status(self, part):
        api = self.app.api
        part_id = part["id"]
        new_status = NEXT_STATUS[part["status"]]
        self._mutate(lambda: api.update_part(part_id, status=new_status))

    def _delete_part(self, part_id):
        api = self.app.api
        self._mutate(lambda: api.delete_part(part_id))

    def _open_editor(self, part):
        self._editing_part = part  # 0 = new part, dict = existing
        self._render()

    def _render_part_editor(self, card):
        part = self._editing_part if isinstance(self._editing_part, dict) else None
        editor = tk.Frame(
            card, bg=theme.BG_FIELD, padx=14, pady=12,
            highlightthickness=1, highlightbackground=theme.RUST,
        )
        editor.pack(fill="x", pady=(10, 2))
        tk.Label(
            editor, text="Edit part" if part else "New part",
            bg=theme.BG_FIELD, fg=theme.FG, font=theme.font(11, bold=True),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        self.part_vars = {
            "part_number": tk.StringVar(value=part["part_number"] if part else ""),
            "name": tk.StringVar(value=part["name"] if part else ""),
            "supplier": tk.StringVar(value=part["supplier"] if part else ""),
            "cost": tk.StringVar(
                value=(f"{part['cost_cents'] / 100:.2f}" if part else "")
            ),
            "discount": tk.StringVar(
                value=(f"{part['discount_pct']:g}" if part else "")
            ),
            "status": tk.StringVar(value=part["status"] if part else "Ordered"),
        }

        def cell(row, col, label, key, width=14, numeric=False):
            holder = tk.Frame(editor, bg=theme.BG_FIELD)
            holder.grid(row=row, column=col, sticky="w", padx=4, pady=2)
            tk.Label(
                holder, text=label, bg=theme.BG_FIELD, fg=theme.FG_FAINT,
                font=theme.font(8, bold=True),
            ).pack(anchor="w")
            entry = widgets.styled_entry(
                holder, self.part_vars[key], width=width,
                select_on_focus=numeric,
            )
            entry.configure(bg=theme.BG_PANEL)
            entry.pack(ipady=3)
            return entry

        first = cell(1, 0, "PART NUMBER", "part_number")
        cell(1, 1, "NAME", "name", width=18)
        cell(1, 2, "SUPPLIER", "supplier")
        cell(2, 0, "COST (RAND)", "cost", numeric=True)
        cell(2, 1, "DISCOUNT %", "discount", width=8, numeric=True)

        status_holder = tk.Frame(editor, bg=theme.BG_FIELD)
        status_holder.grid(row=2, column=2, sticky="w", padx=4)
        tk.Label(
            status_holder, text="STATUS", bg=theme.BG_FIELD,
            fg=theme.FG_FAINT, font=theme.font(8, bold=True),
        ).pack(anchor="w")
        status_menu = tk.OptionMenu(
            status_holder, self.part_vars["status"],
            "Ordered", "Arrived", "Fitted",
        )
        status_menu.configure(
            bg=theme.BG_PANEL, fg=theme.FG, activebackground=theme.BG_HOVER,
            activeforeground=theme.FG, highlightthickness=1,
            highlightbackground=theme.BORDER, relief="flat",
            font=theme.font(10),
        )
        status_menu["menu"].configure(
            bg=theme.BG_PANEL, fg=theme.FG, activebackground=theme.RUST,
            font=theme.font(10),
        )
        status_menu.pack()

        self.part_error = tk.Label(
            editor, text="", bg=theme.BG_FIELD, fg=theme.RED,
            font=theme.font(9),
        )
        self.part_error.grid(row=3, column=0, columnspan=4, sticky="w")

        buttons = tk.Frame(editor, bg=theme.BG_FIELD)
        buttons.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        widgets.RoundedButton(
            buttons, "Save part",
            command=lambda: self._save_part(part["id"] if part else None),
            colour=theme.RUST, bg=theme.BG_FIELD, size=10, padx=16, pady=5,
        ).pack(side="left")
        widgets.RoundedButton(
            buttons, "Cancel", command=lambda: self._open_editor(None),
            colour=theme.BG_HOVER, bg=theme.BG_FIELD, size=10,
            padx=14, pady=5,
        ).pack(side="left", padx=6)
        first.focus_set()

    def _open_editor_close(self):
        self._editing_part = None

    def _save_part(self, part_id):
        try:
            cost_cents = theme.parse_money_to_cents(
                self.part_vars["cost"].get()
            )
            discount_text = self.part_vars["discount"].get().strip() or "0"
            discount = float(discount_text.replace("%", ""))
            if not 0 <= discount <= 100:
                raise ValueError("Discount must be between 0 and 100")
        except ValueError as exc:
            self.part_error.configure(text=str(exc))
            return
        fields = {
            "part_number": self.part_vars["part_number"].get().strip(),
            "name": self.part_vars["name"].get().strip(),
            "supplier": self.part_vars["supplier"].get().strip(),
            "cost_cents": cost_cents,
            "discount_pct": discount,
            "status": self.part_vars["status"].get(),
        }
        if not fields["name"] and not fields["part_number"]:
            self.part_error.configure(
                text="Give the part a number or a name."
            )
            return
        api = self.app.api
        vehicle_id = self.vehicle_id
        self._editing_part = None
        if part_id:
            self._mutate(lambda: api.update_part(part_id, **fields))
        else:
            self._mutate(lambda: api.add_part(vehicle_id, fields))

    # ------------------------------------------------------------ labour

    def _render_labour(self, parent):
        card = self._card(parent, "LABOUR")
        rate = self.vehicle.get("labour_rate_cents") or 0
        row = tk.Frame(card, bg=theme.BG_PANEL)
        row.pack(fill="x", pady=2)
        tk.Label(
            row, text="Hours:", bg=theme.BG_PANEL, fg=theme.FG,
            font=theme.font(11),
        ).pack(side="left")
        self.hours_var = tk.StringVar(
            value=f"{self.vehicle['labour_hours']:g}"
        )
        entry = widgets.styled_entry(row, self.hours_var, width=7)
        entry.pack(side="left", padx=8, ipady=3)
        entry.bind("<Return>", lambda e: self._save_hours())
        widgets.RoundedButton(
            row, "Update", command=self._save_hours, colour=theme.RUST,
            bg=theme.BG_PANEL, size=9, padx=12, pady=4,
        ).pack(side="left")
        tk.Label(
            card,
            text=f"Rate: {theme.format_money(rate)}/h "
                 "(set in the workshop's Settings tab)",
            bg=theme.BG_PANEL, fg=theme.FG_FAINT, font=theme.font(9),
        ).pack(anchor="w", pady=(6, 0))

    def _save_hours(self):
        text = self.hours_var.get().strip()
        try:
            hours = float(text or 0)
            if hours < 0:
                raise ValueError
        except ValueError:
            widgets.toast(
                self.winfo_toplevel(), "Labour hours must be a number",
                colour=theme.RED,
            )
            return
        api = self.app.api
        vehicle_id = self.vehicle_id
        self._mutate(
            lambda: api.update_vehicle(vehicle_id, labour_hours=hours)
        )

    # ------------------------------------------------------------ totals

    def _render_totals(self, parent):
        card = self._card(parent, "INVOICE TOTALS")
        totals = theme.vehicle_totals(
            self.vehicle.get("parts", []),
            self.vehicle.get("labour_hours", 0),
            self.vehicle.get("labour_rate_cents", 0),
        )
        rows = (
            ("Parts", totals["parts_gross"], theme.FG),
            ("Discount", -totals["discount"], theme.TEAL),
            ("Labour", totals["labour"], theme.FG),
            ("Subtotal", totals["subtotal"], theme.FG),
            ("VAT (15%)", totals["vat"], theme.FG),
        )
        for label, cents, colour in rows:
            row = tk.Frame(card, bg=theme.BG_PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(
                row, text=label, bg=theme.BG_PANEL, fg=theme.FG_DIM,
                font=theme.font(10),
            ).pack(side="left")
            tk.Label(
                row, text=theme.format_money(cents), bg=theme.BG_PANEL,
                fg=colour, font=theme.font(10),
            ).pack(side="right")
        divider = tk.Frame(card, bg=theme.BORDER, height=1)
        divider.pack(fill="x", pady=6)
        row = tk.Frame(card, bg=theme.BG_PANEL)
        row.pack(fill="x")
        tk.Label(
            row, text="TOTAL", bg=theme.BG_PANEL, fg=theme.FG,
            font=theme.font(12, bold=True),
        ).pack(side="left")
        tk.Label(
            row, text=theme.format_money(totals["total"]),
            bg=theme.BG_PANEL, fg=theme.AMBER, font=theme.font(14, bold=True),
        ).pack(side="right")

    # ------------------------------------------------------------ misc

    def _toggle_status(self):
        new_status = "done" if self.vehicle["status"] == "open" else "open"
        api = self.app.api
        vehicle_id = self.vehicle_id
        self._mutate(lambda: api.update_vehicle(vehicle_id, status=new_status))

    def _copy_registration(self):
        widgets.copy_to_clipboard(
            self.winfo_toplevel(), self.vehicle["registration"]
        )
        widgets.toast(self.winfo_toplevel(), "Registration copied")

    def _card(self, parent, title):
        card = tk.Frame(
            parent, bg=theme.BG_PANEL, padx=16, pady=12,
            highlightthickness=1, highlightbackground=theme.BORDER,
        )
        card.pack(fill="x", pady=6)
        tk.Label(
            card, text=title, bg=theme.BG_PANEL, fg=theme.RUST,
            font=theme.font(9, bold=True),
        ).pack(anchor="w", pady=(0, 6))
        return card


def _overstrike(size):
    base = theme.font(size)
    import tkinter.font as tkfont

    return tkfont.Font(
        family=base.cget("family"), size=size, overstrike=True
    )
