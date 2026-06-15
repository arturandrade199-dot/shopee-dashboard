#!/usr/bin/env python3
"""
Ponto de entrada do scraper.

Pré-requisito: execute 'python setup_session.py' para autenticar na Shopee.

Uso:
    python main.py              # coleta + exibe melhores ofertas
    python main.py --dry-run    # coleta mas nao salva no banco
    python main.py --limit 5    # limita a N ofertas exibidas
"""

import argparse
import logging
import os
import sys

# Força UTF-8 no terminal Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

from pathlib import Path
from scraper import Database, ShopeeScraper, format_whatsapp_message, quality_filter

SESSION_FILE = Path("data/shopee_session.json")


def main():
    parser = argparse.ArgumentParser(description="Shopee deal scraper")
    parser.add_argument("--dry-run", action="store_true", help="Nao salva no banco")
    parser.add_argument("--limit",   type=int, default=10, help="Max de ofertas exibidas")
    args = parser.parse_args()

    if not SESSION_FILE.exists():
        print()
        print("AVISO: Sessao Shopee nao encontrada.")
        print("Execute primeiro: python setup_session.py")
        print()
        print("Tentando sem autenticacao (pode nao coletar produtos)...")
        print()

    db = Database()
    seen_ids = db.get_announced_last_24h()

    with ShopeeScraper() as scraper:
        products = scraper.fetch_all()

    good = [p for p in products if quality_filter(p, seen_ids)]
    good.sort(key=lambda p: p.discount_pct, reverse=True)

    print()
    print("-" * 50)
    print(f"  Coletados : {len(products)}")
    print(f"  Aprovados : {len(good)}")
    print(f"  Ja vistos : {len(seen_ids)}")
    print("-" * 50)
    print()

    for i, product in enumerate(good[: args.limit], start=1):
        print(f"[{i}/{min(args.limit, len(good))}] {product.name[:60]}")
        print(f"     Preco: R$ {product.price:.2f}  |  -{product.discount_pct}%  |  Avaliacao: {product.rating:.1f}")
        print()
        print(format_whatsapp_message(product))
        print("-" * 50)
        print()

        if not args.dry_run:
            db.save_product(product)

    db.close()
    print(f"Concluido. {len(good)} oferta(s) aprovada(s).")


if __name__ == "__main__":
    main()
