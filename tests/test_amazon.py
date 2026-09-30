import unittest
from decimal import Decimal
from pathlib import Path

from webquery import amazon

FIX = Path(__file__).parent / "fixtures"


class ParsePriceTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(amazon.parse_price("€42.68"), (Decimal("42.68"), "EUR"))
        self.assertEqual(amazon.parse_price("42,68\xa0€"), (Decimal("42.68"), "EUR"))
        self.assertEqual(amazon.parse_price("1.234,56 €"), (Decimal("1234.56"), "EUR"))
        self.assertEqual(amazon.parse_price("HUF 13,930.55"), (Decimal("13930.55"), "HUF"))
        self.assertEqual(amazon.parse_price("HUF15,650.33"), (Decimal("15650.33"), "HUF"))


class ParsePageTest(unittest.TestCase):
    def test_in_stock_takes_new_offer_not_subscription(self):
        offer = amazon.parse((FIX / "amazon_in_stock.html").read_text())
        self.assertEqual(offer.price, Decimal("42.68"))
        self.assertEqual(offer.currency, "EUR")
        self.assertTrue(offer.available)

    def test_unavailable(self):
        offer = amazon.parse((FIX / "amazon_unavailable.html").read_text())
        self.assertIsNone(offer.price)
        self.assertFalse(offer.available)

    def test_captcha_is_blocked(self):
        html = '<form action="/errors/validateCaptcha">Enter the characters you see below</form>'
        with self.assertRaises(amazon.BlockedError):
            amazon.parse(html)


if __name__ == "__main__":
    unittest.main()
