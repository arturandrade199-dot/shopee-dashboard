import os
from .models import Product

# Configure em .env após cadastro em parceiros.shopee.com.br
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "")


def build_shopee_affiliate_url(product: Product) -> str:
    """
    Retorna URL de afiliado para produto Shopee.

    Com ID de afiliado: adiciona parâmetro de rastreamento ao link do produto.
    Sem ID: retorna o link direto (para testes).

    TODO: quando disponível, usar a API de deep link do programa Shopee Parceiros
    (POST https://affiliate.shopee.com.br/api/v1/deeplink/generate) para gerar
    links curtos rastreáveis (shope.ee/XXXXX) com comissão registrada.
    """
    base = product.product_url
    if not SHOPEE_AFFILIATE_ID:
        return base

    sep = "&" if "?" in base else "?"
    return f"{base}{sep}af_siteid={SHOPEE_AFFILIATE_ID}&smtt=0.0.9"
