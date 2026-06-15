"""
Scraper para Shopee Brasil.

Estratégias de coleta (em ordem de confiabilidade):
  1. Flash Sale   — /api/v4/flash_sale/          (promoções relâmpago, descontos altos)
  2. Busca        — /api/v4/search/search_items   (busca por palavras-chave com desconto)
  3. Recomendação — /api/v4/recommend/            (produtos em destaque do dia)

Preços na API Shopee são armazenados com fator 100.000.
Ex: R$ 29,90 → 2.990.000 no JSON → dividir por 100_000 → 29.90
"""

import logging
import random
import time
from datetime import datetime
from typing import List, Optional

import requests

from .affiliate import build_shopee_affiliate_url
from .models import Product

logger = logging.getLogger(__name__)

_PRICE_FACTOR = 100_000  # fator de conversão Shopee → BRL

_USER_AGENTS = [
    # Android Chrome (maioria do público brasileiro)
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-A525F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; moto g(20)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
    # iOS Safari
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# Palavras-chave para busca de ofertas gerais
_SEARCH_KEYWORDS = ["oferta", "promocao", "desconto", "barato"]


class ShopeeScraper:
    BASE_URL = "https://shopee.com.br"

    def __init__(self, delay_min: float = 1.5, delay_max: float = 3.5):
        self._delay_min = delay_min
        self._delay_max = delay_max
        self.session = requests.Session()
        self._init_session()

    # ─── Inicialização ────────────────────────────────────────

    def _init_session(self):
        """Visita a homepage para obter cookies de sessão."""
        ua = random.choice(_USER_AGENTS)
        self.session.headers.update(
            {
                "User-Agent": ua,
                "Accept": "application/json",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": f"{self.BASE_URL}/",
                "x-api-source": "pc",
                "x-requested-with": "XMLHttpRequest",
                "x-shopee-language": "pt-BR",
                # token placeholder — atualizado pelos cookies após homepage
                "x-csrftoken": "a" * 32,
            }
        )

        try:
            resp = self.session.get(self.BASE_URL, timeout=15)
            resp.raise_for_status()

            # Shopee define SPC_SC_TK ou SPC_CDS como CSRF token
            csrf = (
                self.session.cookies.get("SPC_SC_TK")
                or self.session.cookies.get("SPC_CDS")
                or "a" * 32
            )
            self.session.headers["x-csrftoken"] = csrf
            logger.info("Sessão Shopee inicializada com sucesso")
        except requests.RequestException as exc:
            logger.warning("Não foi possível inicializar sessão: %s", exc)

    # ─── HTTP ────────────────────────────────────────────────

    def _get(self, url: str, params: dict = None, retries: int = 3) -> Optional[dict]:
        for attempt in range(retries):
            try:
                time.sleep(random.uniform(self._delay_min, self._delay_max))
                resp = self.session.get(url, params=params, timeout=20)

                if resp.status_code == 429:
                    backoff = 2 ** attempt * 5
                    logger.warning("Rate limit (429). Aguardando %ds...", backoff)
                    time.sleep(backoff)
                    continue

                if resp.status_code == 403:
                    logger.warning("Acesso negado (403). Reinicializando sessão...")
                    self._init_session()
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    # Shopee retorna {"code": 0} em respostas OK
                    if isinstance(data, dict) and data.get("code", 0) not in (0, None):
                        logger.warning("Shopee erro code=%s em %s", data.get("code"), url)
                        return None
                    return data

                resp.raise_for_status()

            except requests.RequestException as exc:
                logger.error("Erro HTTP (tentativa %d/%d): %s", attempt + 1, retries, exc)
                if attempt < retries - 1:
                    time.sleep(2**attempt)

        logger.error("Falha após %d tentativas: %s", retries, url)
        return None

    # ─── Estratégia 1: Flash Sale ─────────────────────────────

    def fetch_flash_sale(self) -> List[Product]:
        """Produtos em promoção relâmpago — geralmente os maiores descontos."""
        data = self._get(f"{self.BASE_URL}/api/v4/flash_sale/get_all_sessions")
        if not data:
            return []

        sessions = (
            data.get("data", {}).get("sessions")
            or data.get("sessions")
            or []
        )
        if not sessions:
            logger.info("Flash Sale: nenhuma sessão ativa encontrada")
            return []

        # Usa a primeira sessão ativa (menor start_time no futuro ou em curso)
        session_id = (
            sessions[0].get("promotionid")
            or sessions[0].get("sessionid")
            or sessions[0].get("promo_id")
        )
        if not session_id:
            logger.warning("Flash Sale: ID de sessão não encontrado")
            return []

        logger.info("Flash Sale: sessão %s", session_id)
        products: List[Product] = []

        for start_index in range(0, 150, 50):
            batch = self._get(
                f"{self.BASE_URL}/api/v4/flash_sale/get_items",
                params={
                    "sessionid":   session_id,
                    "start_index": start_index,
                    "limit":       50,
                },
            )
            if not batch:
                break

            raw_items = (
                batch.get("data", {}).get("items")
                or batch.get("items")
                or []
            )
            if not raw_items:
                break

            for raw in raw_items:
                p = self._parse_flash_item(raw)
                if p:
                    products.append(p)

        logger.info("Flash Sale: %d produtos coletados", len(products))
        return products

    # ─── Estratégia 2: Busca por palavra-chave ────────────────

    def fetch_search(self, keyword: str = "", limit: int = 60) -> List[Product]:
        """Busca geral com filtro de desconto habilitado."""
        params = {
            "by":                  "pop",
            "limit":               limit,
            "newest":              0,
            "order":               "desc",
            "page_type":           "search",
            "scenario":            "PAGE_OTHERS",
            "version":             2,
            "discount_bff_n_items": -1,  # retorna apenas itens com desconto
        }
        if keyword:
            params["keyword"] = keyword

        data = self._get(
            f"{self.BASE_URL}/api/v4/search/search_items", params=params
        )
        if not data:
            return []

        raw_items = data.get("items") or []
        products = []
        for raw in raw_items:
            p = self._parse_search_item(raw)
            if p:
                products.append(p)

        logger.info("Busca '%s': %d produtos", keyword or "(geral)", len(products))
        return products

    # ─── Estratégia 3: Recomendações diárias ─────────────────

    def fetch_daily_discover(self) -> List[Product]:
        """Produtos em destaque curados pela Shopee para o dia."""
        data = self._get(
            f"{self.BASE_URL}/api/v4/recommend/recommend_items",
            params={"bundle": "daily_discover_main", "limit": 60, "offset": 0},
        )
        if not data:
            return []

        products: List[Product] = []
        sections = data.get("data", {}).get("sections") or []

        for section in sections:
            section_items = section.get("data", {}).get("item") or []
            for raw in section_items:
                # daily_discover retorna o item diretamente (sem wrapper)
                p = self._parse_raw_item(raw)
                if p:
                    products.append(p)

        logger.info("Daily Discover: %d produtos", len(products))
        return products

    # ─── Orquestrador ─────────────────────────────────────────

    def fetch_all(self) -> List[Product]:
        """
        Executa todas as estratégias e retorna lista deduplicada,
        ordenada por desconto (maior primeiro).
        """
        all_products: List[Product] = []
        seen: set = set()

        strategies = [
            ("flash_sale",     self.fetch_flash_sale),
            ("daily_discover", self.fetch_daily_discover),
        ]
        # Adiciona buscas por palavras-chave
        for kw in _SEARCH_KEYWORDS:
            strategies.append((f"search:{kw}", lambda k=kw: self.fetch_search(keyword=k)))
        strategies.append(("search:geral", lambda: self.fetch_search(keyword="")))

        for name, fetcher in strategies:
            logger.info("Executando estratégia: %s", name)
            try:
                for p in fetcher():
                    if p.platform_id not in seen:
                        seen.add(p.platform_id)
                        all_products.append(p)
            except Exception as exc:
                logger.error("Erro na estratégia '%s': %s", name, exc)

        all_products.sort(key=lambda p: p.discount_pct, reverse=True)
        logger.info("Total de produtos únicos coletados: %d", len(all_products))
        return all_products

    # ─── Parsers ─────────────────────────────────────────────

    def _parse_flash_item(self, raw: dict) -> Optional[Product]:
        # Flash sale envolve o item em "item_brief"
        item = raw.get("item_brief") or raw
        return self._parse_raw_item(item)

    def _parse_search_item(self, raw: dict) -> Optional[Product]:
        # Search envolve o item em "item_basic"
        item = raw.get("item_basic") or raw
        return self._parse_raw_item(item)

    def _parse_raw_item(self, item: dict) -> Optional[Product]:
        """
        Converte o dicionário bruto da API Shopee em Product.

        Campos usados (com aliases por variação de endpoint):
          itemid / item_id
          shopid / shop_id
          name
          price / price_min
          price_before_discount / price_max / original_price
          raw_discount / discount_percentage
          image / images[0]
          stock / stock_count
          sold / historical_sold
          item_rating.rating_star
          shop_name / shop_location
        """
        try:
            item_id = str(item.get("itemid") or item.get("item_id") or "")
            shop_id = str(item.get("shopid") or item.get("shop_id") or "")
            name    = (item.get("name") or "").strip()

            if not item_id or not name:
                return None

            raw_price    = item.get("price") or item.get("price_min") or 0
            raw_original = (
                item.get("price_before_discount")
                or item.get("price_max")
                or item.get("original_price")
                or raw_price
            )

            price    = round(raw_price    / _PRICE_FACTOR, 2)
            original = round(raw_original / _PRICE_FACTOR, 2)

            if price <= 0 or original <= 0:
                return None

            # Calcula desconto — prefere o campo direto da API
            discount_pct = int(
                item.get("raw_discount")
                or item.get("discount_percentage")
                or 0
            )
            if discount_pct == 0 and original > price:
                discount_pct = int(round((1 - price / original) * 100))

            # URL da imagem (hash → CDN da Shopee Brasil)
            images     = item.get("images") or []
            image_hash = item.get("image") or (images[0] if images else None)
            image_url  = (
                f"https://cf.shopee.com.br/file/{image_hash}" if image_hash else ""
            )

            product_url = f"{self.BASE_URL}/product/{shop_id}/{item_id}"

            rating_info = item.get("item_rating") or {}
            rating      = float(rating_info.get("rating_star") or 0)

            sold      = int(item.get("sold") or item.get("historical_sold") or 0)
            stock     = int(item.get("stock") or item.get("stock_count") or 0)
            shop_name = str(item.get("shop_name") or item.get("shop_location") or "")

            product = Product(
                source        = "shopee",
                platform_id   = item_id,
                shop_id       = shop_id,
                name          = name,
                price         = price,
                original_price = original,
                discount_pct  = discount_pct,
                image_url     = image_url,
                product_url   = product_url,
                shop_name     = shop_name,
                rating        = rating,
                sold          = sold,
                stock         = stock,
                collected_at  = datetime.now(),
            )
            product.affiliate_url = build_shopee_affiliate_url(product)
            return product

        except Exception as exc:
            logger.debug("Falha ao parsear item: %s | raw=%s", exc, str(item)[:120])
            return None
