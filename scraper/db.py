import os
import sqlite3
from datetime import datetime, timedelta
from typing import Set

from .models import Product

_DEFAULT_DB = os.getenv("DB_PATH", "data/produtos.db")


class Database:
    def __init__(self, path: str = _DEFAULT_DB):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id              TEXT PRIMARY KEY,
                source          TEXT NOT NULL,
                platform_id     TEXT NOT NULL,
                shop_id         TEXT,
                name            TEXT NOT NULL,
                price           REAL NOT NULL,
                original_price  REAL NOT NULL,
                discount_pct    INTEGER NOT NULL,
                affiliate_url   TEXT,
                image_url       TEXT,
                product_url     TEXT,
                shop_name       TEXT,
                rating          REAL,
                sold            INTEGER,
                coupon_code     TEXT,
                collected_at    TEXT NOT NULL,
                announced_at    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_announced
                ON products (announced_at);
        """)
        self.conn.commit()

    def get_announced_last_24h(self) -> Set[str]:
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        rows = self.conn.execute(
            "SELECT id FROM products WHERE announced_at > ?", (cutoff,)
        ).fetchall()
        return {row["id"] for row in rows}

    def save_product(self, product: Product):
        self.conn.execute(
            """
            INSERT OR REPLACE INTO products
                (id, source, platform_id, shop_id, name, price, original_price,
                 discount_pct, affiliate_url, image_url, product_url, shop_name,
                 rating, sold, coupon_code, collected_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product.dedup_key,
                product.source,
                product.platform_id,
                product.shop_id,
                product.name,
                product.price,
                product.original_price,
                product.discount_pct,
                product.affiliate_url,
                product.image_url,
                product.product_url,
                product.shop_name,
                product.rating,
                product.sold,
                product.coupon_code,
                product.collected_at.isoformat(),
            ),
        )
        self.conn.commit()

    def mark_announced(self, product: Product):
        self.conn.execute(
            "UPDATE products SET announced_at = ? WHERE id = ?",
            (datetime.now().isoformat(), product.dedup_key),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
