"""
Bronze layer — ingestion

Recebe o CSV exportado manualmente pelo script JS do navegador
e armazena em data/lake/bronze/shopee/YYYY-MM-DD/ com timestamp,
sem nenhuma transformação (dado bruto preservado).

Uso:
    python -m etl.pipeline ingest --file shopee_2026-06-18.csv --keyword "kit cozinha"
    python -m etl.ingest    --file shopee_2026-06-18.csv
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path

BRONZE_ROOT = Path("data/lake/bronze/shopee")


def ingest(csv_path: str | Path, keyword: str = "") -> Path:
    """Copia o CSV bruto para a camada bronze e retorna o destino."""
    src = Path(csv_path)
    if not src.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {src}")

    batch_date = datetime.now().strftime("%Y-%m-%d")
    timestamp  = datetime.now().strftime("%H-%M-%S")
    dest_dir   = BRONZE_ROOT / batch_date
    dest_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"_{keyword.replace(' ', '_')}" if keyword else ""
    dest = dest_dir / f"raw_{timestamp}{suffix}.csv"

    shutil.copy2(src, dest)
    print(f"[bronze] {src.name} → {dest}  ({dest.stat().st_size} bytes)")
    return dest


def _cli():
    p = argparse.ArgumentParser(description="Ingest CSV bruto para a camada bronze")
    p.add_argument("--file",    required=True, help="Caminho do CSV exportado pelo browser")
    p.add_argument("--keyword", default="",    help="Keyword de busca usada na coleta")
    args = p.parse_args()
    ingest(args.file, args.keyword)


if __name__ == "__main__":
    _cli()
