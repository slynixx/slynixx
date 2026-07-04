import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "client")
)

import theme  # noqa: E402


def totals(parts, hours, rate_cents):
    return theme.vehicle_totals(parts, hours, rate_cents)


class FormatMoneyTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(theme.format_money(123450), "R1,234.50")
        self.assertEqual(theme.format_money(0), "R0.00")
        self.assertEqual(theme.format_money(207000), "R2,070.00")
        self.assertEqual(theme.format_money(258750), "R2,587.50")
        self.assertEqual(theme.format_money(-5000), "-R50.00")
        self.assertEqual(theme.format_money(100000000), "R1,000,000.00")

    def test_parse(self):
        self.assertEqual(theme.parse_money_to_cents("R1,234.50"), 123450)
        self.assertEqual(theme.parse_money_to_cents("1000"), 100000)
        self.assertEqual(theme.parse_money_to_cents("450"), 45000)
        self.assertEqual(theme.parse_money_to_cents("1 234.5"), 123450)
        self.assertEqual(theme.parse_money_to_cents(""), 0)
        with self.assertRaises(ValueError):
            theme.parse_money_to_cents("abc")
        with self.assertRaises(ValueError):
            theme.parse_money_to_cents("-5")


class VehicleTotalsTests(unittest.TestCase):
    """The known-good maths from the spec, verified exactly."""

    PART = {"cost_cents": 100000, "discount_pct": 10}  # R1,000 at 10%
    RATE = 45000  # R450/h

    def test_r1000_10pct_2h_r450(self):
        t = totals([self.PART], 2, self.RATE)
        self.assertEqual(t["parts_gross"], 100000)
        self.assertEqual(t["discount"], 10000)
        self.assertEqual(t["labour"], 90000)
        self.assertEqual(t["subtotal"], 180000)
        self.assertEqual(t["vat"], 27000)
        self.assertEqual(t["total"], 207000)
        self.assertEqual(theme.format_money(t["total"]), "R2,070.00")

    def test_change_hours_to_3(self):
        t = totals([self.PART], 3, self.RATE)
        self.assertEqual(t["total"], 258750)
        self.assertEqual(theme.format_money(t["total"]), "R2,587.50")

    def test_change_cost_to_1200(self):
        part = {"cost_cents": 120000, "discount_pct": 10}
        t = totals([part], 2, self.RATE)
        self.assertEqual(t["total"], 227700)
        self.assertEqual(theme.format_money(t["total"]), "R2,277.00")

    def test_vat_is_15_pct_of_discounted_parts_plus_labour(self):
        t = totals([self.PART], 2, self.RATE)
        self.assertEqual(t["vat"], round(t["subtotal"] * 0.15))

    def test_empty(self):
        t = totals([], 0, 0)
        self.assertEqual(t["total"], 0)


class PhoneFormatterTests(unittest.TestCase):
    def test_progressive(self):
        import widgets

        self.assertEqual(widgets.format_phone_digits(""), "")
        self.assertEqual(widgets.format_phone_digits("082"), "082")
        self.assertEqual(widgets.format_phone_digits("0821"), "082 1")
        self.assertEqual(widgets.format_phone_digits("0821234"), "082 123 4")
        self.assertEqual(
            widgets.format_phone_digits("0821234567"), "082 123 4567"
        )
        self.assertEqual(
            widgets.format_phone_digits("08212345679999"), "082 123 4567"
        )


if __name__ == "__main__":
    unittest.main()
