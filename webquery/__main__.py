"""Belépési pont: python -m webquery [check|history|test-mail]"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from decimal import Decimal
from pathlib import Path

import requests
import yaml

from . import amazon, db, notify

ROOT = Path(__file__).resolve().parent.parent
PARSERS = {"amazon": amazon}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9,de;q=0.8",
}

log = logging.getLogger("webquery")


def fmt_price(price: Decimal, currency: str | None) -> str:
    return f"{price:.2f}".replace(".", ",") + (f" {currency}" if currency else "")


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def fetch(url: str, parser, timeout: int) -> str:
    resp = requests.get(
        url, headers=HEADERS, cookies=getattr(parser, "COOKIES", None), timeout=timeout
    )
    if resp.status_code in (403, 503):
        raise amazon.BlockedError(f"HTTP {resp.status_code} (valószínűleg tiltás)")
    resp.raise_for_status()
    return resp.text


def should_notify(conn, product: dict, price: Decimal) -> bool:
    """Csak akkor küldünk, ha most ment a limit alá, vagy tovább esett az utolsó értesítés óta."""
    url, limit = product["url"], Decimal(str(product["limit"]))
    prev = db.previous_ok_check(conn, url)
    prev_below = (
        prev is not None and prev["available"] and prev["price"] is not None
        and Decimal(prev["price"]) < limit
    )
    if not prev_below:
        return True
    last = db.last_notification(conn, url)
    return last is None or price < Decimal(last["price"])


def check_product(conn, product: dict, settings: dict, dry_run: bool) -> bool:
    name, url = product.get("name", product["url"]), product["url"]
    parser = PARSERS[product.get("parser", "amazon")]
    limit = Decimal(str(product["limit"]))
    try:
        html = fetch(url, parser, settings.get("request_timeout", 30))
        offer = parser.parse(html)
    except amazon.BlockedError as exc:
        log.warning("%s: az oldal nem olvasható (%s). Nem kerüljük meg.", name, exc)
        db.record_check(conn, url=url, name=name, status="blocked", message=str(exc))
        return False
    except Exception as exc:  # hálózati vagy szerkezeti hiba
        log.error("%s: hiba: %s", name, exc)
        if isinstance(exc, amazon.ParseError) and "html" in locals():
            debug = ROOT / "debug"
            debug.mkdir(exist_ok=True)
            (debug / f"{int(time.time())}.html").write_text(html, encoding="utf-8")
        db.record_check(conn, url=url, name=name, status="error", message=str(exc))
        return False

    want = product.get("currency")
    if offer.price is not None and want and offer.currency != want:
        msg = f"Váratlan pénznem: {offer.currency or 'ismeretlen'} (várt: {want})"
        log.error("%s: %s", name, msg)
        db.record_check(conn, url=url, name=name, status="error", price=offer.price,
                        currency=offer.currency, message=msg)
        return False

    db.record_check(conn, url=url, name=name, status="ok", price=offer.price,
                    currency=offer.currency, available=offer.available,
                    availability=offer.availability_text)

    if offer.price is None or not offer.available:
        log.info("%s: nem elérhető (%s)", name, offer.availability_text or "nincs ár")
        return True

    price_txt = fmt_price(offer.price, offer.currency)
    if offer.price >= limit:
        log.info("%s: %s, limit %s, nincs teendő", name, price_txt, fmt_price(limit, want))
        return True

    log.info("%s: %s, a limit (%s) ALATT!", name, price_txt, fmt_price(limit, want))
    if not should_notify(conn, product, offer.price):
        log.info("%s: erről az árról már ment értesítés.", name)
        return True
    if dry_run:
        log.info("%s: próbafutás, e-mail nem megy ki.", name)
        return True
    subject = f"{name} most {price_txt} (limit {fmt_price(limit, want)} alatt)"
    body = f"{subject}\n\nElérhetőség: {offer.availability_text}\n{url}\n"
    try:
        notify.send_mail(subject, body)
        db.record_notification(conn, url, offer.price, limit)
        log.info("%s: e-mail elküldve.", name)
    except Exception as exc:
        log.error("%s: az e-mail küldése nem sikerült: %s", name, exc)
        return False
    return True


def cmd_check(args, config) -> int:
    settings = config.get("settings", {})
    conn = db.connect(ROOT / settings.get("db_path", "data/prices.sqlite3"))
    ok = True
    for i, product in enumerate(config.get("products", [])):
        if i:
            time.sleep(settings.get("delay_between_products", 5))
        ok &= check_product(conn, product, settings, args.dry_run)
    return 0 if ok else 1


def cmd_history(args, config) -> int:
    settings = config.get("settings", {})
    conn = db.connect(ROOT / settings.get("db_path", "data/prices.sqlite3"))
    for r in db.history(conn, args.n):
        price = fmt_price(Decimal(r["price"]), r["currency"]) if r["price"] else "-"
        avail = {1: "elérhető", 0: "nem elérhető"}.get(r["available"], "")
        print(f"{r['checked_at']}  {r['status']:<7} {price:>12}  {avail:<12} "
              f"{r['name']} {r['message'] or ''}")
    return 0


def cmd_test_mail(args, config) -> int:
    notify.send_mail("webquery próba e-mail", "Ha ezt látod, az SMTP-beállítás működik.\n")
    print("Próba e-mail elküldve.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="webquery", description="Óránkénti árfigyelő")
    ap.add_argument("-c", "--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--env", default=str(ROOT / ".env"))
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("check", help="árak lekérése (alapértelmezett)")
    p.add_argument("--dry-run", action="store_true", help="e-mail küldése nélkül")
    p = sub.add_parser("history", help="utolsó mérések listája")
    p.add_argument("-n", type=int, default=20)
    sub.add_parser("test-mail", help="próba e-mail küldése")
    args = ap.parse_args(argv)
    if args.cmd is None:
        args.cmd, args.dry_run = "check", False

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stdout)
    notify.load_env(args.env)
    config = load_config(Path(args.config))
    return {"check": cmd_check, "history": cmd_history, "test-mail": cmd_test_mail}[args.cmd](
        args, config
    )


if __name__ == "__main__":
    sys.exit(main())
