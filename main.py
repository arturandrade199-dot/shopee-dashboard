#!/usr/bin/env python3
"""
Ponto de entrada do scraper.

Uso:
    python main.py              # coleta + exibe melhores ofertas
    python main.py --dry-run    # coleta mas não salva no banco
    python main.py --limit 5    # limita a N ofertas exibidas
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

from scraper import Database, ShopeeScraper, format_whatsapp_message, quality_filter


def main():
    parser = argparse.ArgumentParser(description="Shopee deal scraper")
    parser.add_argument("--dry-run", action="store_true", help="Não salva no banco")
    parser.add_argument("--limit",   type=int, default=10, help="Máx. de ofertas exibidas")
    args = parser.parse_args()

    db = Database()
    seen_ids = db.get_announced_last_24h()

    scraper  = ShopeeScraper()
    products = scraper.fetch_all()

    good = [p for p in products if quality_filter(p, seen_ids)]
    good.sort(key=lambda p: p.discount_pct, reverse=True)

    print(f"\n{'─'*50}")
    print(f"  Coletados : {len(products)}")
    print(f"  Aprovados : {len(good)}")
    print(f"  Já vistos : {len(seen_ids)}")
    print(f"{'─'*50}\n")

    for i, product in enumerate(good[: args.limit], start=1):
        print(f"[{i}/{min(args.limit, len(good))}] {product.name[:60]}")
        print(f"     Preço: R$ {product.price:.2f}  |  -{product.discount_pct}%  |  ⭐ {product.rating:.1f}")
        print()
        print(format_whatsapp_message(product))
        print("─" * 50)
        print()

        if not args.dry_run:
            db.save_product(product)

    db.close()
    print(f"✅ Concluído. {len(good)} oferta(s) aprovada(s).")


if __name__ == "__main__":
    main()
