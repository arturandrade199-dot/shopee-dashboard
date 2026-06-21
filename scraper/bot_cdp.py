"""
Bot Shopee — CDP (Chrome DevTools Protocol)
============================================
Conecta ao Chrome REAL já aberto pelo usuário (sem WebDriver detectável).
Automatiza as 3 fases do scraper JS e salva os JSONs em data/jsons/.

Pré-requisitos:
  1. Inicie o Chrome via start_chrome.bat
  2. Faça login em affiliate.shopee.com.br e shopee.com.br
  3. Execute: python -m scraper.bot_cdp

Depois rode o ETL:
  python -m etl.load_supabase --folder data/jsons
"""

import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP_URL           = "http://localhost:9222"
AFFILIATE_LIST    = "https://affiliate.shopee.com.br/offer/product_offer"
STORAGE_KEY       = "shopee_affiliate_data"
OUTPUT_DIR        = Path("data/jsons")
SCRIPT_PATH       = Path("scraper/js/scraper_afiliados_shopee.js")

# Pausa entre páginas (segundos) — evita rate limit
DELAY_ENTRE_PAGINAS = 2.5


def _scroll(page, rounds: int = 6, intervalo: int = 1200) -> None:
    """Rola até o fim para forçar o lazy loading das seções."""
    for _ in range(rounds):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(intervalo)


def _inject(page, script: str) -> None:
    try:
        page.evaluate(script)
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"    [aviso] erro ao injetar script: {e}")


def _ler_storage(page) -> dict:
    try:
        return page.evaluate(
            f"JSON.parse(localStorage.getItem('{STORAGE_KEY}') || '{{}}')"
        )
    except Exception:
        return {}


def _salvar_json(data: dict, label: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = OUTPUT_DIR / f"shopee_affiliate_{ts}_{label}.json"
    path.write_text(
        json.dumps(list(data.values()), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def run() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    with sync_playwright() as p:
        print("Conectando ao Chrome na porta 9222...")
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"\nErro de conexão: {e}")
            print("Certifique-se de ter iniciado o Chrome via start_chrome.bat")
            return

        ctx  = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("Conectado.\n")

        # ══════════════════════════════════════════════════════
        #  Fase 1 — Lista de afiliados
        # ══════════════════════════════════════════════════════
        print("Fase 1 — capturando lista de produtos afiliados...")
        page.goto(AFFILIATE_LIST, wait_until="networkidle", timeout=30_000)
        _scroll(page, rounds=3, intervalo=800)
        _inject(page, script)

        dados_afiliado = _ler_storage(page)
        produtos       = list(dados_afiliado.values())
        print(f"  {len(produtos)} produto(s) encontrado(s) na lista.\n")

        if not produtos:
            print("Nenhum produto encontrado. Verifique o login e a página.")
            browser.close()
            return

        # ══════════════════════════════════════════════════════
        #  Fase 2 — Detalhe de comissão de cada produto
        # ══════════════════════════════════════════════════════
        print("Fase 2 — coletando comissões por canal...")
        for i, prod in enumerate(produtos, 1):
            nome  = (prod.get("name") or prod.get("title") or "?")[:55]
            href  = prod.get("detail_href", "")
            print(f"  [{i}/{len(produtos)}] {nome}")

            if not href:
                print("    sem link de detalhe, pulando.")
                continue

            page.goto(href, wait_until="networkidle", timeout=30_000)
            _inject(page, script)
            time.sleep(DELAY_ENTRE_PAGINAS)

        # Salva fases 1+2 (domínio affiliate)
        dados_afiliado = _ler_storage(page)
        arq_f12 = _salvar_json(dados_afiliado, "fases1-2")
        print(f"\n  Fases 1+2 salvas → {arq_f12.name}")

        # ══════════════════════════════════════════════════════
        #  Fase 3 — Página do produto no shopee.com.br
        # ══════════════════════════════════════════════════════
        print("\nFase 3 — coletando dados completos dos produtos...")
        total = len(dados_afiliado)
        for i, prod in enumerate(dados_afiliado.values(), 1):
            nome        = (prod.get("name") or prod.get("title") or "?")[:55]
            product_url = prod.get("product_url", "")
            print(f"  [{i}/{total}] {nome}")

            if not product_url:
                print("    sem product_url (fase de detalhe não coletada), pulando.")
                continue

            page.goto(product_url, wait_until="networkidle", timeout=30_000)
            _scroll(page, rounds=6, intervalo=1200)  # lazy loading das seções
            _inject(page, script)
            time.sleep(DELAY_ENTRE_PAGINAS)

        # Salva fase 3 (domínio shopee.com.br — localStorage separado)
        dados_shopee = _ler_storage(page)
        arq_f3 = _salvar_json(dados_shopee, "fase3")
        print(f"\n  Fase 3 salva → {arq_f3.name}")

        # ══════════════════════════════════════════════════════
        #  Resumo
        # ══════════════════════════════════════════════════════
        print("\n" + "═" * 55)
        print(f"Concluído!")
        print(f"  Fases 1+2 : {arq_f12}")
        print(f"  Fase 3    : {arq_f3}")
        print(f"\nPróximo passo — carregar no Supabase:")
        print(f"  python -m etl.load_supabase --folder data/jsons")
        print("═" * 55)

        browser.close()


if __name__ == "__main__":
    run()
