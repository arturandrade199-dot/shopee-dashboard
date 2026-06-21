"""
Silver layer — transformation

Lê todos os CSVs brutos da camada bronze (ou de uma data específica),
parseia e normaliza os campos, deduplica por URL e salva em
data/lake/silver/shopee/YYYY-MM-DD/products.csv

Transformações aplicadas:
  price / originalPrice → float (R$ 29,90 → 29.90)
  discount              → int   (-30% → 30)
  sold                  → int   ("1.234 vendidos" / "2mil+" → inteiro)
  rating                → float
  platform_id / shop_id → extraídos da URL Shopee
  ingested_at           → timestamp ISO da ingestão
"""

import csv
import re
from datetime import datetime
from pathlib import Path

BRONZE_ROOT = Path("data/lake/bronze/shopee")
SILVER_ROOT = Path("data/lake/silver/shopee")

SILVER_COLUMNS = [
    "batch_date", "page", "position", "title",
    "price", "original_price", "discount",
    "sold", "rating", "badge",
    "url", "image",
    "platform_id", "shop_id",
    "ingested_at",
]


# ---------- parsers individuais ----------

def _parse_price(raw: str) -> float:
    """'R$ 29,90' → 29.9"""
    m = re.search(r"[\d.,]+", raw.replace(".", "").replace(",", "."))
    try:
        return round(float(m.group()), 2) if m else 0.0
    except ValueError:
        return 0.0


def _parse_discount(raw: str) -> int:
    """-30% → 30"""
    m = re.search(r"-?(\d+)\s*%", raw)
    return int(m.group(1)) if m else 0


def _parse_sold(raw: str) -> int:
    """
    '1.234 vendidos'  → 1234
    '2mil+ vendidos'  → 2000
    '500+ vendidos'   → 500
    '3,5mil vendidos' → 3500
    """
    if not raw:
        return 0
    raw = raw.lower()
    mil = re.search(r"([\d]+(?:[,.][\d]+)?)\s*mil", raw)
    if mil:
        return int(float(mil.group(1).replace(",", ".")) * 1000)
    num = re.search(r"[\d]+", raw.replace(".", "").replace(",", ""))
    return int(num.group()) if num else 0


def _parse_ids(url: str) -> tuple[str, str]:
    """
    'https://shopee.com.br/produto-i.123456789.987654321'
    → platform_id='987654321', shop_id='123456789'
    """
    m = re.search(r"-i\.(\d+)\.(\d+)", url)
    if m:
        return m.group(2), m.group(1)   # platform_id, shop_id
    return "", ""


# ---------- lógica principal ----------

def _read_bronze_rows(batch_date: str) -> list[dict]:
    bronze_dir = BRONZE_ROOT / batch_date
    if not bronze_dir.exists():
        raise FileNotFoundError(f"Bronze não encontrado: {bronze_dir}")

    rows = []
    for csv_file in sorted(bronze_dir.glob("*.csv")):
        with open(csv_file, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["_source_file"] = csv_file.name
                rows.append(row)
    return rows


def transform(batch_date: str | None = None) -> Path:
    """
    Transforma bronze → silver para a data informada
    (padrão: hoje).  Retorna o caminho do arquivo silver gerado.
    """
    if batch_date is None:
        batch_date = datetime.now().strftime("%Y-%m-%d")

    raw_rows = _read_bronze_rows(batch_date)
    if not raw_rows:
        print(f"[silver] Nenhum dado bronze encontrado para {batch_date}.")
        return Path()

    ingested_at = datetime.now().isoformat(timespec="seconds")
    seen_urls: set[str] = set()
    clean_rows: list[dict] = []

    for r in raw_rows:
        url = r.get("url", "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        price    = _parse_price(r.get("price", ""))
        orig     = _parse_price(r.get("originalPrice", ""))
        discount = _parse_discount(r.get("discount", ""))

        # recalcula desconto se não veio do JS mas há preços
        if not discount and orig > price > 0:
            discount = round((1 - price / orig) * 100)

        platform_id, shop_id = _parse_ids(url)

        clean_rows.append({
            "batch_date":     batch_date,
            "page":           r.get("page", ""),
            "position":       r.get("position", ""),
            "title":          r.get("title", "").strip(),
            "price":          price,
            "original_price": orig,
            "discount":       discount,
            "sold":           _parse_sold(r.get("sold", "")),
            "rating":         float(r.get("rating", 0) or 0),
            "badge":          r.get("badge", "").strip(),
            "url":            url,
            "image":          r.get("image", "").strip(),
            "platform_id":    platform_id,
            "shop_id":        shop_id,
            "ingested_at":    ingested_at,
        })

    dest_dir = SILVER_ROOT / batch_date
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "products.csv"

    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SILVER_COLUMNS)
        writer.writeheader()
        writer.writerows(clean_rows)

    print(f"[silver] {len(clean_rows)} produtos limpos → {dest}")
    return dest


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None, help="YYYY-MM-DD (padrão: hoje)")
    args = p.parse_args()
    transform(args.date)
