"""Reusable Tk widgets for Workbay: RoundedButton, TopBar, ScrollableFrame,
toasts and the live phone-number formatter."""

import tkinter as tk

import theme


class RoundedButton(tk.Canvas):
    """Flat rounded-rectangle button used for every action in the app."""

    def __init__(self, parent, text, command=None, colour=theme.RUST,
                 hover=None, fg="#ffffff", padx=18, pady=8, size=11,
                 bold=True, **kwargs):
        self._font = theme.font(size, bold=bold)
        width = self._font.measure(text) + padx * 2
        height = self._font.metrics("linespace") + pady * 2
        super().__init__(
            parent, width=width, height=height, highlightthickness=0,
            bg=kwargs.pop("bg", parent.cget("bg")), bd=0, cursor="hand2",
            **kwargs,
        )
        self.command = command
        self.colour = colour
        self.hover_colour = hover or _lighten(colour)
        self._fg = fg
        self._text = text
        self._radius = min(12, height // 2)
        self._draw(self.colour)
        self.bind("<Enter>", lambda e: self._draw(self.hover_colour))
        self.bind("<Leave>", lambda e: self._draw(self.colour))
        self.bind("<Button-1>", self._on_click)

    def _draw(self, fill):
        self.delete("all")
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        r = self._radius
        self.create_arc(0, 0, r * 2, r * 2, start=90, extent=90,
                        fill=fill, outline=fill)
        self.create_arc(w - r * 2, 0, w, r * 2, start=0, extent=90,
                        fill=fill, outline=fill)
        self.create_arc(0, h - r * 2, r * 2, h, start=180, extent=90,
                        fill=fill, outline=fill)
        self.create_arc(w - r * 2, h - r * 2, w, h, start=270, extent=90,
                        fill=fill, outline=fill)
        self.create_rectangle(r, 0, w - r, h, fill=fill, outline=fill)
        self.create_rectangle(0, r, w, h - r, fill=fill, outline=fill)
        self.create_text(w // 2, h // 2, text=self._text, fill=self._fg,
                         font=self._font)

    def _on_click(self, _event):
        if self.command:
            self.command()

    def set_text(self, text):
        self._text = text
        width = self._font.measure(text) + 36
        self.configure(width=width)
        self._draw(self.colour)


class TopBar(tk.Frame):
    """Top navigation bar with accent-underlined tabs plus a right-hand
    area for user info / logout."""

    def __init__(self, parent, title, tabs, on_tab, accent=theme.RUST):
        super().__init__(parent, bg=theme.BG_PANEL)
        self.on_tab = on_tab
        self.accent = accent
        self._tabs = {}
        self._current = None

        tk.Label(
            self, text=title, bg=theme.BG_PANEL, fg=theme.FG,
            font=theme.font(14, bold=True), padx=18, pady=12,
        ).pack(side="left")

        self.right = tk.Frame(self, bg=theme.BG_PANEL)
        self.right.pack(side="right", padx=12)

        tab_holder = tk.Frame(self, bg=theme.BG_PANEL)
        tab_holder.pack(side="left", padx=16)
        for name in tabs:
            cell = tk.Frame(tab_holder, bg=theme.BG_PANEL)
            cell.pack(side="left", padx=6)
            label = tk.Label(
                cell, text=name, bg=theme.BG_PANEL, fg=theme.FG_DIM,
                font=theme.font(11, bold=True), padx=10, pady=10,
                cursor="hand2",
            )
            label.pack()
            underline = tk.Frame(cell, bg=theme.BG_PANEL, height=3)
            underline.pack(fill="x")
            label.bind("<Button-1>", lambda e, n=name: self.select(n))
            self._tabs[name] = (label, underline)
        border = tk.Frame(parent, bg=theme.BORDER, height=1)
        self.pack(side="top", fill="x")
        border.pack(side="top", fill="x")

    def select(self, name, fire=True):
        if name == self._current:
            return
        self._current = name
        for tab_name, (label, underline) in self._tabs.items():
            active = tab_name == name
            label.configure(fg=theme.FG if active else theme.FG_DIM)
            underline.configure(bg=self.accent if active else theme.BG_PANEL)
        if fire:
            self.on_tab(name)


class ScrollableFrame(tk.Frame):
    """Vertical scrolling container; put children in `.inner`."""

    def __init__(self, parent, bg=theme.BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        for widget in (self.canvas, self.inner):
            widget.bind("<MouseWheel>", self._on_mousewheel)
            widget.bind("<Button-4>", self._on_mousewheel)
            widget.bind("<Button-5>", self._on_mousewheel)

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    def bind_mousewheel_recursive(self, widget=None):
        """Attach wheel scrolling to every descendant so scrolling works
        wherever the pointer is."""
        widget = widget or self.inner
        for handler in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(handler, self._on_mousewheel)
        for child in widget.winfo_children():
            self.bind_mousewheel_recursive(child)


def toast(root, message, colour=theme.TEAL, ms=1800):
    """Small transient notification at the bottom of the window."""
    note = tk.Label(
        root, text=message, bg=colour, fg="#ffffff",
        font=theme.font(11, bold=True), padx=18, pady=8,
    )
    note.place(relx=0.5, rely=0.94, anchor="center")
    note.lift()
    root.after(ms, note.destroy)


def format_phone_digits(digits):
    """Format up to 10 digits as `000 000 0000`."""
    digits = digits[:10]
    if len(digits) > 6:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    if len(digits) > 3:
        return f"{digits[:3]} {digits[3:]}"
    return digits


def attach_phone_formatter(entry, var):
    """Live-format a phone entry as the user types: digits only, max 10,
    spaced 000 000 0000."""
    state = {"busy": False}

    def on_change(*_args):
        if state["busy"]:
            return
        state["busy"] = True
        try:
            digits = "".join(ch for ch in var.get() if ch.isdigit())
            formatted = format_phone_digits(digits)
            if formatted != var.get():
                var.set(formatted)
                entry.icursor("end")
        finally:
            state["busy"] = False

    var.trace_add("write", on_change)


def copy_to_clipboard(root, text):
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update_idletasks()


def styled_entry(parent, textvariable=None, width=24, show=None, size=11):
    entry = tk.Entry(
        parent, textvariable=textvariable, width=width, show=show,
        bg=theme.BG_FIELD, fg=theme.FG, insertbackground=theme.FG,
        relief="flat", font=theme.font(size),
        highlightthickness=1, highlightbackground=theme.BORDER,
        highlightcolor=theme.RUST,
    )
    return entry


def field_label(parent, text, size=10):
    return tk.Label(
        parent, text=text, bg=parent.cget("bg"), fg=theme.FG_DIM,
        font=theme.font(size, bold=True), anchor="w",
    )


def _lighten(colour):
    mapping = {
        theme.RUST: theme.RUST_HOVER,
        theme.TEAL: theme.TEAL_HOVER,
        theme.RED: theme.RED_HOVER,
        theme.AMBER: "#f0b83e",
    }
    if colour in mapping:
        return mapping[colour]
    value = colour.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (
        min(r + 24, 255), min(g + 24, 255), min(b + 24, 255)
    )
