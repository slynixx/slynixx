"""Dark palette, fonts and South African Rand / VAT maths for Workbay.

All money maths uses integer cents so totals never drift.  VAT is 15%,
charged on discounted parts plus labour.
"""

import tkinter.font as tkfont

# ------------------------------------------------------------- palette

BG = "#15171a"          # window background
BG_PANEL = "#1d2025"    # cards / panels
BG_FIELD = "#24282e"    # entry fields
BG_HOVER = "#2b3037"    # hover rows
BORDER = "#33383f"

FG = "#e8e6e3"          # main text
FG_DIM = "#9aa0a6"      # secondary text
FG_FAINT = "#6b7076"    # hints

RUST = "#d9622b"        # primary action
RUST_HOVER = "#e97a44"
AMBER = "#e0a526"       # money and number plates
AMBER_DARK = "#b8860f"
TEAL = "#2fa98c"        # success / positive
TEAL_HOVER = "#3fc4a4"
RED = "#c8443c"         # admin / destructive
RED_HOVER = "#da5a52"

PLATE_TEXT = "#1a1200"  # dark text on the amber plate

VAT_RATE = 0.15

_FONT_CACHE = {}


def font(size=11, bold=False):
    """Return a cached tkinter font; prefers Segoe UI (Windows) and falls
    back to whatever the platform offers."""
    key = (size, bold)
    if key not in _FONT_CACHE:
        families = set(tkfont.families())
        for family in ("Segoe UI", "DejaVu Sans", "Helvetica", "Arial"):
            if family in families:
                break
        else:
            family = "TkDefaultFont"
        _FONT_CACHE[key] = tkfont.Font(
            family=family, size=size, weight="bold" if bold else "normal"
        )
    return _FONT_CACHE[key]


def plate_font(size=14):
    families = set(tkfont.families())
    for family in ("Consolas", "Courier New", "DejaVu Sans Mono", "Courier"):
        if family in families:
            return tkfont.Font(family=family, size=size, weight="bold")
    return font(size, bold=True)


# --------------------------------------------------------- money maths

def parse_money_to_cents(text):
    """Parse user input like 'R1,234.50', '1234.5' or '1 234' into cents.

    Raises ValueError with a friendly message on bad input.
    """
    cleaned = (text or "").strip().replace("R", "").replace("r", "")
    cleaned = cleaned.replace(",", "").replace(" ", "")
    if not cleaned:
        return 0
    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError(f"'{text}' is not an amount, e.g. 1250 or R1,250.00")
    if value < 0:
        raise ValueError("Amounts cannot be negative")
    return int(round(value * 100))


def format_money(cents):
    """R1,234.50 style South African Rand formatting."""
    cents = int(round(cents))
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    rand, remainder = divmod(cents, 100)
    return f"{sign}R{rand:,}.{remainder:02d}"


def part_net_cents(part):
    """Cost of one part after its discount, in cents."""
    cost = int(part.get("cost_cents") or 0)
    discount = float(part.get("discount_pct") or 0)
    return int(round(cost * (1 - discount / 100.0)))


def labour_cents(hours, rate_cents):
    return int(round(float(hours or 0) * int(rate_cents or 0)))


def vehicle_totals(parts, labour_hours, labour_rate_cents):
    """Invoice-style totals, all in cents.

    Order: Parts (gross) -> Discount -> Labour -> Subtotal -> VAT (15%)
    -> Total.
    """
    parts_gross = sum(int(p.get("cost_cents") or 0) for p in parts)
    parts_net = sum(part_net_cents(p) for p in parts)
    discount = parts_gross - parts_net
    labour = labour_cents(labour_hours, labour_rate_cents)
    subtotal = parts_net + labour
    vat = int(round(subtotal * VAT_RATE))
    total = subtotal + vat
    return {
        "parts_gross": parts_gross,
        "discount": discount,
        "labour": labour,
        "subtotal": subtotal,
        "vat": vat,
        "total": total,
    }
