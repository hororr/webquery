"""Amazon termékoldal: a fő ajánlat (Buy Box) árának és elérhetőségének kiolvasása."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

# Az Amazon a látogató országa szerint vált pénznemet (pl. HUF); ez a süti rögzíti az eurót.
COOKIES = {"i18n-prefs": "EUR"}

# A fő (egyszeri vásárlás, "NEW") ajánlat árának helye, fontossági sorrendben.
PRICE_SELECTORS = [
    '#corePrice_feature_div [data-csa-c-buying-option-type="NEW"] .apex-pricetopay-value .a-offscreen',
    '#corePrice_feature_div [data-csa-c-buying-option-type="NEW"] .a-price .a-offscreen',
    "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .apex-pricetopay-value .a-offscreen",
    "#price_inside_buybox",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
]

UNAVAILABLE_PATTERNS = [
    "currently unavailable",
    "derzeit nicht verfügbar",
    "temporarily out of stock",
    "vorübergehend nicht auf lager",
]


class BlockedError(Exception):
    """Az Amazon CAPTCHA-t vagy tiltó oldalt adott vissza. Nem kerüljük meg."""


class ParseError(Exception):
    """Az oldal szerkezete nem a várt (pl. megváltozott a szelektor)."""


@dataclass
class Offer:
    title: str | None
    price: Decimal | None
    currency: str | None
    available: bool
    availability_text: str | None


def parse_price(text: str) -> tuple[Decimal, str | None]:
    """'€42.68', '42,68 €', 'EUR 1.234,56' -> (Decimal, pénznem)."""
    raw = text.replace("\xa0", " ").strip()
    currency = None
    if "€" in raw or "EUR" in raw:
        currency = "EUR"
    else:
        m = re.search(r"([A-Z]{3})", raw)
        if m:
            currency = m.group(1)
    num = re.sub(r"[^\d.,]", "", raw)
    if not num:
        raise ParseError(f"Nem értelmezhető ár: {text!r}")
    # Az utolsó elválasztó a tizedesjel, ha utána 1-2 számjegy áll.
    m = re.match(r"^(.*?)[.,](\d{1,2})$", num)
    if m:
        whole, frac = re.sub(r"[.,]", "", m.group(1)), m.group(2)
        num = f"{whole or '0'}.{frac}"
    else:
        num = re.sub(r"[.,]", "", num)
    try:
        return Decimal(num), currency
    except InvalidOperation as exc:
        raise ParseError(f"Nem értelmezhető ár: {text!r}") from exc


def check_blocked(html: str) -> None:
    lowered = html[:200_000].lower()
    if (
        "validatecaptcha" in lowered
        or "/errors/validatecaptcha" in lowered
        or "enter the characters you see below" in lowered
        or "geben sie die zeichen unten ein" in lowered
        or "api-services-support@amazon.com" in lowered
    ):
        raise BlockedError("Az Amazon CAPTCHA-t vagy robotellenőrzést adott vissza.")


def parse(html: str) -> Offer:
    check_blocked(html)
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("#productTitle")
    title = title_el.get_text(" ", strip=True) if title_el else None

    price = currency = None
    for sel in PRICE_SELECTORS:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            price, currency = parse_price(el.get_text(strip=True))
            break

    avail_el = soup.select_one("#availability")
    availability_text = avail_el.get_text(" ", strip=True) if avail_el else None
    has_cart_button = soup.select_one("#add-to-cart-button") is not None
    unavailable = bool(availability_text) and any(
        p in availability_text.lower() for p in UNAVAILABLE_PATTERNS
    )
    available = price is not None and has_cart_button and not unavailable

    if title is None and price is None and avail_el is None:
        raise ParseError("Nem található sem cím, sem ár, sem elérhetőség az oldalon.")

    return Offer(title, price, currency, available, availability_text)
