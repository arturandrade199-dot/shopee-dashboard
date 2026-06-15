from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Product:
    source: str           # 'shopee' | 'mercadolivre' | 'amazon'
    platform_id: str      # ID único na plataforma
    shop_id: str
    name: str
    price: float          # preço atual em R$
    original_price: float # preço antes do desconto em R$
    discount_pct: int     # 0–100
    image_url: str
    product_url: str
    affiliate_url: str = ""
    shop_name: str = ""
    rating: float = 0.0
    sold: int = 0
    stock: int = 0
    coupon_code: Optional[str] = None
    coupon_discount: Optional[float] = None
    collected_at: datetime = field(default_factory=datetime.now)

    @property
    def savings(self) -> float:
        return round(self.original_price - self.price, 2)

    @property
    def final_price(self) -> float:
        if self.coupon_discount:
            return round(self.price - self.coupon_discount, 2)
        return self.price

    @property
    def dedup_key(self) -> str:
        return f"{self.source}:{self.platform_id}"
