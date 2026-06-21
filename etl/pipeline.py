"""
Pipeline completo: ingest → transform → load

Uso:
    # Ingere CSV e roda todo o pipeline
    python -m etl.pipeline --file shopee_2026-06-18.csv --keyword "kit cozinha"

    # Só transform + load (bronze já existe)
    python -m etl.pipeline --skip-ingest --date 2026-06-18

    # Dry-run (não grava no SQLite)
    python -m etl.pipeline --file shopee.csv --dry-run
"""

import argparse
from datetime import datetime

from etl.ingest import ingest
from etl.transform import transform
from etl.load import load


def run(
    csv_file:     str  | None = None,
    keyword:      str         = "",
    batch_date:   str  | None = None,
    skip_ingest:  bool        = False,
    dry_run:      bool        = False,
):
    date = batch_date or datetime.now().strftime("%Y-%m-%d")

    if not skip_ingest:
        if not csv_file:
            raise ValueError("Informe --file com o CSV exportado pelo browser.")
        ingest(csv_file, keyword)

    transform(date)
    load(date, dry_run=dry_run)

    print(f"\n✅ Pipeline concluído para {date}")


def _cli():
    p = argparse.ArgumentParser(description="Pipeline ETL Shopee (bronze → silver → gold → db)")
    p.add_argument("--file",         help="CSV exportado pelo browser")
    p.add_argument("--keyword",      default="", help="Keyword de busca")
    p.add_argument("--date",         default=None, help="YYYY-MM-DD (padrão: hoje)")
    p.add_argument("--skip-ingest",  action="store_true", help="Pula a etapa de ingestão")
    p.add_argument("--dry-run",      action="store_true", help="Não grava no SQLite")
    args = p.parse_args()

    run(
        csv_file    = args.file,
        keyword     = args.keyword,
        batch_date  = args.date,
        skip_ingest = args.skip_ingest,
        dry_run     = args.dry_run,
    )


if __name__ == "__main__":
    _cli()
