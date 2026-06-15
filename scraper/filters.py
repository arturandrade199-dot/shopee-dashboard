from typing import Set
from .models import Product

# Critérios da arquitetura do projeto
MIN_DISCOUNT_PCT = 25
MIN_PRICE_BRL    = 30.0
MAX_PRICE_BRL    = 500.0
MIN_RATING       = 3.5   # evita produtos com avaliações ruins
MIN_SOLD         = 10    # evita produtos sem histórico de venda


def quality_filter(product: Product, seen_ids: Set[str] = None) -> bool:
    """Retorna True se o produto passa em todos os critérios de qualidade."""
    seen_ids = seen_ids or set()

    if product.discount_pct < MIN_DISCOUNT_PCT:
        return False
    if not (MIN_PRICE_BRL <= product.price <= MAX_PRICE_BRL):
        return False
    if not product.image_url:
        return False
    if product.original_price <= product.price:
        return False
    if product.rating > 0 and product.rating < MIN_RATING:
        return False
    if product.sold > 0 and product.sold < MIN_SOLD:
        return False
    if product.dedup_key in seen_ids:
        return False

    return True
