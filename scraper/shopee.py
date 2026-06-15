"""
Scraper para Shopee Brasil.

A Shopee requer autenticação em todos os endpoints /api/v4/ desde 2025.
Solução: Playwright com sessão autenticada. Os cookies ficam salvos em
data/shopee_session.json (gerado por setup_session.py ou import_cookies.py).

Chamadas de API são feitas via fetch() dentro do contexto do browser,
o que inclui os cookies de sessão automaticamente (same-origin).

Fluxo:
  1. execute: python import_cookies.py   (uma vez, ou quando os cookies expirarem)
  2. execute: python main.py

Preços na API Shopee: armazenados × 100.000.
Ex: R$ 29,90 → 2.990.000 → / 100_000 → 29,90
"""

import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .affiliate import build_shopee_affiliate_url
from .models import Product

logger = logging.getLogger(__name__)

_PRICE_FACTOR    = 100_000
_SESSION_FILE    = Path("data/shopee_session.json")
_BASE_URL        = "https://shopee.com.br"
_SEARCH_KEYWORDS = ["oferta", "promocao", "desconto"]


class ShopeeScraper:

    def __init__(self, delay_min: float = 1.5, delay_max: float = 3.0):
        self._delay_min  = delay_min
        self._delay_max  = delay_max
        self._playwright = None
        self._browser    = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ─── Ciclo de vida ────────────────────────────────────────

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._ctx  = self._load_context()
        self._page = self._ctx.new_page()
        self._page.set_extra_http_headers({
            "Accept-Language":    "pt-BR,pt;q=0.9",
            "x-shopee-language":  "pt-BR",
            "x-requested-with":   "XMLHttpRequest",
            "x-api-source":       "pc",
        })
        # Navega para a homepage para estabelecer o domínio e ativar os cookies
        logger.info("Inicializando sessao em %s ...", _BASE_URL)
        self._page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=20000)
        return self

    def __exit__(self, *_):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _load_context(self) -> BrowserContext:
        if _SESSION_FILE.exists():
            try:
                data    = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
                storage = data.get("storage") or {}
                ctx = self._browser.new_context(
                    storage_state=storage,
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    user_agent=(
                        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Mobile Safari/537.36"
                    ),
                )
                logger.info("Sessao carregada (%d cookies)", len(storage.get("cookies", [])))
                return ctx
            except Exception as exc:
                logger.warning("Falha ao carregar sessao: %s", exc)

        logger.warning("Sessao nao encontrada. Execute python import_cookies.py")
        return self._browser.new_context(locale="pt-BR", timezone_id="America/Sao_Paulo")

    # ─── Chamada de API via fetch() no browser ────────────────

    def _api_get(self, path: str, params: dict = None) -> Optional[dict]:
        """
        Executa fetch() dentro do contexto autenticado do browser.
        Os cookies de sessão são incluídos automaticamente (same-origin).
        """
        qs = ""
        if params:
            qs = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{_BASE_URL}{path}{qs}"

        time.sleep(random.uniform(self._delay_min, self._delay_max))

        js = f"""
        async () => {{
            try {{
                const csrfMatch = document.cookie.match(/csrftoken=([^;]+)/);
                const csrf = csrfMatch ? csrfMatch[1] : '';
                const resp = await fetch({json.dumps(full_url)}, {{
                    method: 'GET',
                    credentials: 'include',
                    headers: {{
                        'Accept': 'application/json',
                        'x-requested-with': 'XMLHttpRequest',
                        'x-shopee-language': 'pt-BR',
                        'x-csrftoken': csrf,
                        'x-api-source': 'pc',
                    }}
                }});
                if (!resp.ok) return {{ _http_status: resp.status }};
                return await resp.json();
            }} catch(e) {{
                return {{ _error: e.toString() }};
            }}
        }}
        """

        try:
            data = self._page.evaluate(js)
        except Exception as exc:
            logger.error("Erro no fetch JS: %s", exc)
            return None

        if not isinstance(data, dict):
            return None

        if "_error" in data:
            logger.error("Erro JS em %s: %s", path, data["_error"])
            return None

        if "_http_status" in data:
            logger.warning("HTTP %s em %s", data["_http_status"], path)
            return None

        if data.get("error", 0) not in (0, None, ""):
            logger.warning("API erro code=%s em %s", data.get("error"), path)
            return None

        return data

    # ─── Estratégia 1: Flash Sale ─────────────────────────────

    def fetch_flash_sale(self) -> List[Product]:
        data = self._api_get("/api/v4/flash_sale/get_all_sessions",
                             params={"tracker_info_version": 1})
        if not data:
            return []

        sessions = data.get("data", {}).get("sessions") or []
        if not sessions:
            logger.info("Flash Sale: nenhuma sessao ativa no momento")
            return []

        session_id = sessions[0].get("promotionid") or sessions[0].get("sessionid")
        if not session_id:
            return []

        logger.info("Flash Sale: sessao %s", session_id)
        products: List[Product] = []

        for start in range(0, 150, 50):
            batch = self._api_get(
                "/api/v4/flash_sale/get_items",
                params={"promotionid": session_id, "start_index": start, "limit": 50},
            )
            if not batch:
                break
            raw_items = batch.get("data", {}).get("items") or batch.get("items") or []
            if not raw_items:
                break
            for raw in raw_items:
                p = self._parse_flash_item(raw)
                if p:
                    products.append(p)

        logger.info("Flash Sale: %d produtos", len(products))
        return products

    # ─── Estratégia 2: Busca por palavra-chave ────────────────

    def fetch_search(self, keyword: str = "", limit: int = 60) -> List[Product]:
        params = {
            "by":                   "pop",
            "limit":                limit,
            "newest":               0,
            "order":                "desc",
            "page_type":            "search",
            "scenario":             "PAGE_OTHERS",
            "version":              2,
            "discount_bff_n_items": -1,
        }
        if keyword:
            params["keyword"] = keyword

        data = self._api_get("/api/v4/search/search_items", params=params)
        if not data:
            return []

        products = []
        for raw in data.get("items") or []:
            p = self._parse_search_item(raw)
            if p:
                products.append(p)

        logger.info("Busca '%s': %d produtos", keyword or "(geral)", len(products))
        return products

    # ─── Estratégia 3: Recomendações diárias ─────────────────

    def fetch_daily_discover(self) -> List[Product]:
        data = self._api_get(
            "/api/v4/recommend/recommend_items",
            params={"bundle": "daily_discover_main", "limit": 60, "offset": 0},
        )
        if not data:
            return []

        products: List[Product] = []
        for section in data.get("data", {}).get("sections") or []:
            for raw in section.get("data", {}).get("item") or []:
                p = self._parse_raw_item(raw)
                if p:
                    products.append(p)

        logger.info("Daily Discover: %d produtos", len(products))
        return products

    # ─── Orquestrador ─────────────────────────────────────────

    def fetch_all(self) -> List[Product]:
        all_products: List[Product] = []
        seen: set = set()

        strategies = [
            ("flash_sale",     self.fetch_flash_sale),
            ("daily_discover", self.fetch_daily_discover),
        ]
        for kw in _SEARCH_KEYWORDS:
            strategies.append((f"search:{kw}", lambda k=kw: self.fetch_search(keyword=k)))

        for name, fetcher in strategies:
            logger.info("Estrategia: %s", name)
            try:
                for p in fetcher():
                    if p.platform_id not in seen:
                        seen.add(p.platform_id)
                        all_products.append(p)
            except Exception as exc:
                logger.error("Erro em '%s': %s", name, exc)

        all_products.sort(key=lambda p: p.discount_pct, reverse=True)
        logger.info("Total de produtos unicos: %d", len(all_products))
        return all_products

    # ─── Parsers ─────────────────────────────────────────────

    def _parse_flash_item(self, raw: dict) -> Optional[Product]:
        return self._parse_raw_item(raw.get("item_brief") or raw)

    def _parse_search_item(self, raw: dict) -> Optional[Product]:
        return self._parse_raw_item(raw.get("item_basic") or raw)

    def _parse_raw_item(self, item: dict) -> Optional[Product]:
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
                or raw_price
            )

            price    = round(raw_price    / _PRICE_FACTOR, 2)
            original = round(raw_original / _PRICE_FACTOR, 2)

            if price <= 0 or original <= 0:
                return None

            discount_pct = int(item.get("raw_discount") or item.get("discount_percentage") or 0)
            if discount_pct == 0 and original > price:
                discount_pct = int(round((1 - price / original) * 100))

            images     = item.get("images") or []
            image_hash = item.get("image") or (images[0] if images else None)
            image_url  = f"https://cf.shopee.com.br/file/{image_hash}" if image_hash else ""

            product_url = f"{_BASE_URL}/product/{shop_id}/{item_id}"

            rating_info = item.get("item_rating") or {}
            rating      = float(rating_info.get("rating_star") or 0)
            sold        = int(item.get("sold") or item.get("historical_sold") or 0)
            stock       = int(item.get("stock") or item.get("stock_count") or 0)
            shop_name   = str(item.get("shop_name") or item.get("shop_location") or "")

            product = Product(
                source         = "shopee",
                platform_id    = item_id,
                shop_id        = shop_id,
                name           = name,
                price          = price,
                original_price = original,
                discount_pct   = discount_pct,
                image_url      = image_url,
                product_url    = product_url,
                shop_name      = shop_name,
                rating         = rating,
                sold           = sold,
                stock          = stock,
                collected_at   = datetime.now(),
            )
            product.affiliate_url = build_shopee_affiliate_url(product)
            return product

        except Exception as exc:
            logger.debug("Falha ao parsear item: %s", exc)
            return None
