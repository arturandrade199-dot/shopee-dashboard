"""
Geração de links de afiliado Shopee.

Como funciona o programa Shopee Parceiros:
  - Affiliate ID : fixo, identifica sua conta. Obtido em parceiros.shopee.com.br.
  - Sub-ID       : variável, você define por canal/campanha. Aparece nos relatórios
                   para saber exatamente de onde veio cada venda.

Exemplos de Sub-ID úteis para este projeto:
  "grupo_sp_1"   → Grupo WhatsApp São Paulo 1
  "grupo_rj_2"   → Grupo WhatsApp Rio 2
  "bot_flash"    → mensagem de flash sale automática
  "painel_manual"→ oferta postada manualmente pelo painel

Fluxo de geração de link:
  1. MVP (atual): adiciona parâmetros af_siteid + sub_id à URL do produto.
     Funciona para rastreamento básico, mas o link não é "curto" (shope.ee/...).

  2. Produção (TODO): usar a API de deep link do Shopee Parceiros para gerar
     um link curto rastreável com comissão registrada corretamente:
     POST https://open-api.affiliate.shopee.com.br/graphql
     → retorna https://s.shopee.com.br/XXXXXXX
     Requer: access_token obtido via OAuth do programa Parceiros.
"""

import os
from .models import Product

# Fixo — ID da sua conta no programa Shopee Parceiros
# Obtido em: parceiros.shopee.com.br → Configurações → Minha Conta
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "")


def build_shopee_affiliate_url(product: Product, sub_id: str = "") -> str:
    """
    Monta URL de afiliado para um produto Shopee.

    Args:
        product: produto coletado pelo scraper
        sub_id:  identificador do canal/campanha (ex: "grupo_sp_1").
                 Se não informado, usa SHOPEE_SUB_ID do .env ou deixa em branco.

    Returns:
        URL com parâmetros de rastreamento, ou URL direta se sem afiliado.
    """
    base = product.product_url

    if not SHOPEE_AFFILIATE_ID:
        return base  # sem afiliado configurado → link direto (modo teste)

    effective_sub_id = sub_id or os.getenv("SHOPEE_SUB_ID", "bot_default")

    sep = "&" if "?" in base else "?"
    params = f"af_siteid={SHOPEE_AFFILIATE_ID}&sub_id={effective_sub_id}&smtt=0.0.9"
    return f"{base}{sep}{params}"
