"""
Gold layer + load

Lê o silver do dia, aplica filtros de qualidade e score,
gera data/lake/gold/shopee/latest.csv e carrega no SQLite
(mesmo banco usado pelo bot).

Score = 0.4 * discount_norm + 0.35 * sold_norm + 0.25 * rating_norm
"""

import csv
import math
from datetime import datetime
from pathlib import Path

from scraper.affiliate import build_shopee_affiliate_url
from scraper.db import Database
from scraper.models import Product

SILVER_ROOT = Path("data/lake/silver/shopee")
GOLD_ROOT   = Path("data/lake/gold/shopee")

# Filtros mínimos para entrar no gold
MIN_PRICE    = 5.0
MIN_DISCOUNT = 10      # %
MIN_RATING   = 3.5     # 0 = sem avaliação (aceito)
TOP_N        = 100     # máximo de produtos no gold/latest


def _normalize(values: list[float]) -> list[float]:
    vmax = max(values) if values else 1
    vmin = min(values) if values else 0
    spread = vmax - vmin or 1
    return [(v - vmin) / spread for v in values]


def _score(discount: int, sold: int, rating: float) -> float:
    return round(0.4 * discount / 100 + 0.35 * math.log1p(sold) / 15 + 0.25 * rating / 5, 4)


def load(batch_date: str | None = None, dry_run: bool = False) -> Path:
    if batch_date is None:
        batch_date = datetime.now().strftime("%Y-%m-%d")

    silver_file = SILVER_ROOT / batch_date / "products.csv"
    if not silver_file.exists():
        raise FileNotFoundError(f"Silver não encontrado: {silver_file}")

    with open(silver_file, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # --- filtros de qualidade ---
    filtered = []
    for r in rows:
        price    = float(r["price"] or 0)
        discount = int(r["discount"] or 0)
        rating   = float(r["rating"] or 0)

        if price < MIN_PRICE:
            continue
        if discount < MIN_DISCOUNT:
            continue
        if rating and rating < MIN_RATING:   # rating=0 → sem avaliação, passa
            continue
        if not r.get("url"):
            continue

        filtered.append(r)

    if not filtered:
        print(f"[gold] Nenhum produto passou nos filtros. Revise MIN_DISCOUNT={MIN_DISCOUNT}%")
        return Path()

    # --- score e ranking ---
    for r in filtered:
        r["_score"] = _score(int(r["discount"] or 0), int(r["sold"] or 0), float(r["rating"] or 0))

    ranked = sorted(filtered, key=lambda r: r["_score"], reverse=True)[:TOP_N]

    # --- gold CSV ---
    GOLD_ROOT.mkdir(parents=True, exist_ok=True)
    gold_file = GOLD_ROOT / "latest.csv"

    gold_cols = [
        "rank", "title", "price", "original_price", "discount",
        "sold", "rating", "badge", "url", "image",
        "platform_id", "shop_id", "batch_date", "score",
    ]

    with open(gold_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=gold_cols)
        writer.writeheader()
        for i, r in enumerate(ranked, 1):
            writer.writerow({
                "rank":           i,
                "title":          r["title"],
                "price":          r["price"],
                "original_price": r["original_price"],
                "discount":       r["discount"],
                "sold":           r["sold"],
                "rating":         r["rating"],
                "badge":          r["badge"],
                "url":            r["url"],
                "image":          r["image"],
                "platform_id":    r["platform_id"],
                "shop_id":        r["shop_id"],
                "batch_date":     r["batch_date"],
                "score":          r["_score"],
            })

    print(f"[gold] {len(ranked)} produtos → {gold_file}")

    if dry_run:
        return gold_file

    # --- carrega no SQLite ---
    db = Database()
    saved = 0
    for r in ranked:
        try:
            affiliate_url = build_shopee_affiliate_url(r["url"])
        except Exception:
            affiliate_url = r["url"]

        product = Product(
            source         = "shopee",
            platform_id    = r["platform_id"] or r["url"],
            shop_id        = r["shop_id"] or "",
            name           = r["title"],
            price          = float(r["price"] or 0),
            original_price = float(r["original_price"] or 0) or float(r["price"] or 0),
            discount_pct   = int(r["discount"] or 0),
            image_url      = r["image"],
            product_url    = r["url"],
            affiliate_url  = affiliate_url,
            rating         = float(r["rating"] or 0),
            sold           = int(r["sold"] or 0),
        )
        db.save_product(product)
        saved += 1

    db.close()
    print(f"[db]   {saved} produtos salvos no SQLite")
    return gold_file


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date",    default=None,  help="YYYY-MM-DD (padrão: hoje)")
    p.add_argument("--dry-run", action="store_true", help="Não grava no SQLite")
    args = p.parse_args()
    load(args.date, dry_run=args.dry_run)
