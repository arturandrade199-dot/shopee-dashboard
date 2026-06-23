"""
Pipeline JSON: lê os JSONs exportados pelo scraper JS, normaliza e carrega no SQLite.

Fluxo: data/jsons/*.json → merge por ID → filter → score → SQLite
       → move para data/jsons/Carregados/

Uso:
    python -m etl.pipeline_json              # processa data/jsons/*.json
    python -m etl.pipeline_json --dry-run    # sem gravar no SQLite
    python -m etl.pipeline_json --no-move    # não move arquivos processados
    python -m etl.pipeline_json --min-commission 8
"""

import argparse
import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path

from scraper.affiliate import build_shopee_affiliate_url
from scraper.db import Database
from scraper.models import Product

JSON_DIR = Path("data/jsons")
DONE_DIR = JSON_DIR / "Carregados"

MIN_RATING     = 3.5   # 0 = sem avaliação → aceito
MIN_COMMISSION = 5     # % mínima de comissão de afiliado
TOP_N          = 300

_PHASE_ORDER = {"complete": 3, "detail": 2, "list": 1}


# ── Parsers ──────────────────────────────────────────────────────────────────

def _parse_sold(raw: str) -> int:
    if not raw:
        return 0
    raw = raw.lower()
    mil = re.search(r"([\d]+(?:[,.][\d]+)?)\s*mil", raw)
    if mil:
        return int(float(mil.group(1).replace(",", ".")) * 1000)
    num = re.search(r"\d+", raw.replace(".", "").replace(",", ""))
    return int(num.group()) if num else 0


def _parse_ids(url: str) -> tuple[str, str]:
    # formato: shopee.com.br/product/{shop_id}/{platform_id}
    m = re.search(r"/product/(\d+)/(\d+)", url)
    if m:
        return m.group(2), m.group(1)   # platform_id, shop_id
    # formato legado: produto-i.{shop_id}.{platform_id}
    m = re.search(r"-i\.(\d+)\.(\d+)", url)
    if m:
        return m.group(2), m.group(1)
    return "", ""


def _discount_from_item(item: dict) -> int:
    for badge in item.get("coupon_badges", []):
        m = re.search(r"(\d+)%\s*OFF", badge, re.IGNORECASE)
        if m:
            return int(m.group(1))
    p_coupon  = float(item.get("price_coupon") or 0)
    p_regular = float(item.get("price_regular") or 0)
    if p_coupon and p_regular and p_regular > p_coupon:
        return round((1 - p_coupon / p_regular) * 100)
    return 0


def _is_valid_product_url(url: str) -> bool:
    if not url or "shopee.com.br" not in url:
        return False
    if "affiliate" in url or "help.shopee" in url:
        return False
    # aceita /product/{shop}/{item} ou -i.{shop}.{item}
    return bool(
        re.search(r"/product/\d+/\d+", url)
        or re.search(r"-i\.\d+\.\d+", url)
    )


def _score(commission: int, sold: int, rating: float) -> float:
    return round(
        0.40 * commission / 100
        + 0.35 * math.log1p(sold) / 15
        + 0.25 * rating / 5,
        4,
    )


# ── Merge ─────────────────────────────────────────────────────────────────────

def _load_and_merge(json_files: list[Path]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for f in json_files:
        try:
            products = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [warn] {f.name}: {e}")
            continue
        for item in products:
            pid = item.get("id") or ""
            if not pid:
                continue
            existing = merged.get(pid)
            if existing is None:
                merged[pid] = item
            else:
                old_phase = _PHASE_ORDER.get(existing.get("_phase", "list"), 1)
                new_phase = _PHASE_ORDER.get(item.get("_phase", "list"), 1)
                if new_phase > old_phase:
                    # Higher phase wins, but preserve list-only fields (e.g. commission_rate)
                    merged[pid] = {**existing, **item}
                elif new_phase == old_phase:
                    old_ts = existing.get("product_scraped_at") or existing.get("list_scraped_at") or ""
                    new_ts = item.get("product_scraped_at") or item.get("list_scraped_at") or ""
                    if new_ts > old_ts:
                        merged[pid] = {**existing, **item}
    return merged


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(min_commission: int = MIN_COMMISSION, dry_run: bool = False, move_files: bool = True):
    json_files = sorted(JSON_DIR.glob("*.json"))
    if not json_files:
        print(f"[json] Nenhum JSON em {JSON_DIR}")
        return

    print(f"[json] {len(json_files)} arquivo(s) encontrado(s)")

    all_items = _load_and_merge(json_files)
    print(f"[json] {len(all_items)} produtos únicos após merge")

    candidates = []
    skipped_no_url = skipped_rating = skipped_commission = 0

    for item in all_items.values():
        url = item.get("product_url") or ""
        if not _is_valid_product_url(url):
            skipped_no_url += 1
            continue

        commission = int(item.get("commission_rate") or item.get("commission_extra_pct") or 0)
        if commission < min_commission:
            skipped_commission += 1
            continue

        rating = float(item.get("rating") or 0)
        if rating and rating < MIN_RATING:
            skipped_rating += 1
            continue

        candidates.append(item)

    print(
        f"[json] {len(candidates)} candidatos "
        f"(sem URL válida: {skipped_no_url}, "
        f"comissão baixa: {skipped_commission}, "
        f"rating baixo: {skipped_rating})"
    )

    if not candidates:
        print("[json] Nada para carregar.")
        return

    # Score e ranking
    for item in candidates:
        sold = int(item.get("sold_num") or 0) or _parse_sold(item.get("sold_raw", ""))
        commission = int(item.get("commission_rate") or item.get("commission_extra_pct") or 0)
        rating = float(item.get("rating") or 0)
        item["_score"] = _score(commission, sold, rating)

    ranked = sorted(candidates, key=lambda x: x["_score"], reverse=True)[:TOP_N]
    print(f"[json] Top {len(ranked)} produtos para carregar no SQLite")

    if dry_run:
        for i, item in enumerate(ranked[:10], 1):
            name = (item.get("title") or item.get("name") or "")[:55]
            comm = item.get("commission_rate") or item.get("commission_extra_pct") or 0
            price = item.get("price_coupon") or item.get("price") or 0
            print(f"  {i:>3}. [{item['_score']:.3f}] {name} — R${price} — {comm}% comissão")
        print("[dry-run] SQLite não atualizado.")
        return

    db = Database()
    saved = 0
    collected_at = datetime.now()

    for item in ranked:
        url = item["product_url"]
        platform_id, shop_id = _parse_ids(url)
        name = (item.get("title") or item.get("name") or "").strip()
        price = float(item.get("price_coupon") or item.get("price") or 0)
        original_price = float(item.get("price_regular") or item.get("price") or price)
        discount_pct = _discount_from_item(item)
        sold = int(item.get("sold_num") or 0) or _parse_sold(item.get("sold_raw", ""))
        rating = float(item.get("rating") or 0)
        shop_name = (item.get("store") or {}).get("name", "")
        commission = int(item.get("commission_rate") or item.get("commission_extra_pct") or 0)

        product = Product(
            source         = "shopee",
            platform_id    = platform_id or url,
            shop_id        = shop_id,
            name           = name,
            price          = price,
            original_price = original_price,
            discount_pct   = discount_pct,
            image_url      = "",
            product_url    = url,
            shop_name      = shop_name,
            rating         = rating,
            sold           = sold,
            collected_at   = collected_at,
        )
        product.affiliate_url = build_shopee_affiliate_url(product)

        db.save_product(product)
        saved += 1

    db.close()
    print(f"[db]   {saved} produtos salvos no SQLite")

    if move_files:
        DONE_DIR.mkdir(parents=True, exist_ok=True)
        for f in json_files:
            dest = DONE_DIR / f.name
            if dest.exists():
                ts = datetime.now().strftime("%H%M%S")
                dest = DONE_DIR / f"{f.stem}_{ts}{f.suffix}"
            shutil.move(str(f), dest)
        print(f"[json] {len(json_files)} arquivo(s) movido(s) para {DONE_DIR}")

    print(f"\nPipeline JSON concluido: {saved} produtos")


def _cli():
    p = argparse.ArgumentParser(description="Pipeline JSON → SQLite")
    p.add_argument("--min-commission", type=int, default=MIN_COMMISSION,
                   help=f"Comissão mínima %% (padrão: {MIN_COMMISSION})")
    p.add_argument("--dry-run",  action="store_true", help="Não grava no SQLite nem move arquivos")
    p.add_argument("--no-move",  action="store_true", help="Não move arquivos após processar")
    args = p.parse_args()
    run(
        min_commission = args.min_commission,
        dry_run        = args.dry_run,
        move_files     = not args.no_move and not args.dry_run,
    )


if __name__ == "__main__":
    _cli()
