"""
Carrega o JSON exportado pelo scraper_afiliados_shopee.js para o Supabase.

Fluxo:
  JSONs (qualquer fase) → merge por id → Bronze (raw_scrapes) → Silver → Gold (views)

Uso — arquivo único:
  python -m etl.load_supabase --file data/jsons/shopee_affiliate_2026-06-18.json

Uso — pasta inteira (mescla fases automaticamente):
  python -m etl.load_supabase --folder data/jsons --date 2026-06-18
"""

import argparse
import json
import math
import os
import re
from datetime import date
from pathlib import Path

from scraper.supabase_client import get_client

_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "")
_SUB_ID       = os.getenv("SHOPEE_SUB_ID", "bot_default")


def _affiliate_url(product_url: str) -> str:
    if not _AFFILIATE_ID:
        return product_url
    sep    = "&" if "?" in product_url else "?"
    params = f"af_siteid={_AFFILIATE_ID}&sub_id={_SUB_ID}&smtt=0.0.9"
    return f"{product_url}{sep}{params}"


def _parse_ids(url: str) -> tuple[str, str]:
    """
    Extrai (shop_id, platform_id) de URLs Shopee.
    Suporta dois formatos:
      - slug: /nome-do-produto-i.SHOPID.ITEMID
      - direto: /product/SHOPID/ITEMID
    """
    url = url or ''
    m = re.search(r'-i\.(\d+)\.(\d+)', url)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r'/product/(\d+)/(\d+)', url)
    if m:
        return m.group(1), m.group(2)
    tail = url.rstrip('/').split('/')[-1]
    return '', tail


def _score(commission: int, commission_extra: int, sold: int,
           rating: float, video_count: int | None) -> float:
    """
    Score de oportunidade:
      40% comissão total | 30% volume de vendas | 20% rating | 10% ausência de vídeos
    """
    total_comm  = (commission or 0) + (commission_extra or 0)
    comm_norm   = min(total_comm / 100, 1.0)
    sold_norm   = math.log1p(sold or 0) / 15
    rating_norm = (rating or 0) / 5
    video_pen   = min((video_count or 0) / 10, 1.0) * 0.10 if video_count else 0
    return round(0.40 * comm_norm + 0.30 * sold_norm + 0.20 * rating_norm - video_pen, 4)


# ── Merge de fases ────────────────────────────────────────────
# Quando o usuário exporta em momentos diferentes, o mesmo produto aparece
# em arquivos distintos com fases diferentes (_phase: list, detail, complete).
# A fusão garante que commission_rate (fase 1) não seja perdido se o produto
# chegou ao banco só como 'complete' (fase 3).

_PHASE_PRIORITY = {'complete': 3, 'detail': 2, 'list': 1}

def _merge_products(files: list[Path]) -> tuple[list[dict], list[dict]]:
    """
    Lê todos os JSONs e mescla por `id`.
    Retorna (merged_complete, all_raw) onde:
      - merged_complete: produtos com `product_url` (fase 3 confirmada)
      - all_raw: lista crua de todos os produtos de todos os arquivos (para bronze)
    """
    by_id: dict[str, dict] = {}
    all_raw: list[dict]    = []

    for f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as e:
            print(f"  [aviso] não foi possível ler {f.name}: {e}")
            continue

        products = data if isinstance(data, list) else list(data.values())
        all_raw.extend(products)

        for p in products:
            pid   = p.get('id') or ''
            phase = p.get('_phase', 'list')
            if not pid:
                continue

            existing = by_id.get(pid)
            if existing is None:
                by_id[pid] = dict(p)
                continue

            existing_pri = _PHASE_PRIORITY.get(existing.get('_phase', 'list'), 0)
            new_pri      = _PHASE_PRIORITY.get(phase, 0)

            if new_pri >= existing_pri:
                # Novo arquivo é mais completo: começa com ele mas preenche
                # campos que só o arquivo antigo tinha (ex: commission_rate da fase 1)
                merged = dict(p)
                for key, val in existing.items():
                    if merged.get(key) in (None, '', 0, [], {}):
                        merged[key] = val
                by_id[pid] = merged
            else:
                # Arquivo antigo é mais completo: só preenche buracos com o novo
                for key, val in p.items():
                    if existing.get(key) in (None, '', 0, [], {}):
                        existing[key] = val

    # Só processa produtos que têm page de produto (têm product_url real)
    complete = [p for p in by_id.values() if p.get('product_url')]
    return complete, all_raw


# ── Principal ─────────────────────────────────────────────────

def load_affiliate(files: list[Path], batch_date: str | None = None) -> int:
    batch     = batch_date or date.today().isoformat()
    complete, all_raw = _merge_products(files)

    print(f"[merge] {len(complete)} produtos com page data (de {len(all_raw)} registros em {len(files)} arquivo(s))")

    supabase = get_client()

    # ── Bronze: todos os arquivos brutos ──────────────────────
    for f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                raw = json.load(fh)
        except Exception:
            continue
        supabase.table('raw_scrapes').upsert({
            'source':     'shopee_affiliate',
            'batch_date': batch,
            'filename':   f.name,
            'raw_data':   raw,
        }, on_conflict='source,batch_date,filename').execute()
    print(f"[bronze] {len(files)} arquivo(s) arquivados em raw_scrapes")

    # ── Silver + Gold ─────────────────────────────────────────
    saved = 0
    for p in complete:
        product_url = p.get('product_url', '')
        shop_id, platform_id = _parse_ids(product_url)
        if not platform_id:
            continue

        affiliate_url = _affiliate_url(product_url)

        s = _score(
            p.get('commission_rate'),
            p.get('commission_extra_pct'),
            p.get('sold_num', 0),
            p.get('rating', 0.0),
            p.get('video_count'),
        )

        # ── Loja ─────────────────────────────────────────────
        # Upsert sempre que tiver shop_id — garante FK antes do produto
        store = p.get('store') or {}
        if shop_id:
            supabase.table('stores').upsert({
                'shop_id':         shop_id,
                'name':            store.get('name') or None,
                'years_on_shopee': store.get('years_on_shopee') or None,
                'response_rate':   store.get('response_rate') or None,
                'response_time':   store.get('response_time') or None,
                'followers':       store.get('followers') or None,
                'total_reviews':   store.get('total_reviews') or None,
                'total_products':  store.get('total_products') or None,
                'last_scraped_at': p.get('product_scraped_at') or None,
            }, on_conflict='shop_id').execute()

        # ── Produto ───────────────────────────────────────────
        result = supabase.table('products').upsert({
            'platform_id':           platform_id,
            'shop_id':               shop_id or None,
            'source':                'shopee_affiliate',
            'slug':                  p.get('id'),
            'title':                 p.get('title'),
            'product_url':           product_url,
            'affiliate_url':         affiliate_url,
            'price_coupon':          p.get('price_coupon') or None,
            'original_price':        p.get('price_regular') or None,
            'rating':                p.get('rating') or None,
            'reviews_num':           p.get('reviews_num') or None,
            'sold_num':              p.get('sold_num') or None,
            'sold_raw':              p.get('sold_raw') or None,
            'has_flash_sale':        p.get('has_flash_sale', False),
            'shipping':              p.get('shipping') or None,
            'commission_rate':       p.get('commission_rate') or None,
            'commission_extra_pct':  p.get('commission_extra_pct') or None,
            'commission_extra_value':p.get('commission_extra_value') or None,
            'badge':                 p.get('badge') or None,
            'video_count':           p.get('video_count'),
            'variants':              p.get('variants') or None,
            'coupon_badges':         p.get('coupon_badges') or None,
            'product_details':       p.get('product_details') or None,
            'score':                 s,
            'batch_date':            batch,
            'scraped_at':            p.get('product_scraped_at'),
        }, on_conflict='platform_id,batch_date,source').execute()

        product_id = result.data[0]['id']

        # ── Canais de comissão ────────────────────────────────
        channels = p.get('channels') or []
        if channels:
            supabase.table('product_channels').delete().eq('product_id', product_id).execute()
            supabase.table('product_channels').insert([{
                'product_id':  product_id,
                'channel':     c.get('channel'),
                'shopee_pct':  c.get('shopee_pct') or None,
                'shopee_value':c.get('shopee_value') or None,
                'estimated':   c.get('estimated') or None,
            } for c in channels]).execute()

        # ── Cupons de loja ────────────────────────────────────
        coupons = p.get('store_coupons') or []
        if coupons:
            supabase.table('store_coupons').delete().eq('product_id', product_id).execute()
            supabase.table('store_coupons').insert([{
                'product_id':  product_id,
                'discount':    c.get('discount'),
                'conditions':  c.get('conditions'),
                'valid_until': c.get('valid_until'),
            } for c in coupons]).execute()

        # ── Produtos relacionados ─────────────────────────────
        related_rows = []
        for rel_type, items in (
            ('same_seller',       p.get('same_seller_products') or []),
            ('recommended',       p.get('recommended_products') or []),
            ('main_store_choice', p.get('main_store_choices') or []),
        ):
            for r in items[:30]:
                _, rpid = _parse_ids(r.get('url', ''))
                related_rows.append({
                    'source_product_id': product_id,
                    'relation_type':     rel_type,
                    'platform_id':       rpid or None,
                    'title':             r.get('name'),
                    'price':             r.get('price') or None,
                    'rating':            r.get('rating') or None,
                    'sold_num':          r.get('sold_num') or None,
                    'sold_raw':          r.get('sold_raw') or None,
                    'discount':          r.get('discount') or None,
                    'product_url':       r.get('url') or None,
                })

        if related_rows:
            supabase.table('related_products').delete().eq('source_product_id', product_id).execute()
            supabase.table('related_products').insert(related_rows).execute()

        saved += 1
        commission_info = f"comissão={p.get('commission_rate') or '?'}%"
        title_safe = (p.get('title') or '').encode('ascii', 'replace').decode()[:55]
        print(f"  ok [{saved}] {title_safe} | {commission_info} | sold={p.get('sold_raw','?')}")

    print(f"\n[supabase] {saved} produtos salvos para batch {batch}")
    return saved


# ── CLI ───────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="Carrega affiliate JSON(s) para o Supabase"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file',   help='JSON único exportado pelo browser')
    group.add_argument('--folder', help='Pasta com vários JSONs (mescla fases automaticamente)')
    parser.add_argument('--date',  default=None, help='YYYY-MM-DD (padrão: hoje)')
    args = parser.parse_args()

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(Path(args.folder).glob('*.json'))
        if not files:
            print(f"Nenhum JSON encontrado em {args.folder}")
            return

    load_affiliate(files, args.date)


if __name__ == '__main__':
    _cli()
