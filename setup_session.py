#!/usr/bin/env python3
"""
Login Shopee — executa UMA VEZ para salvar a sessão.

Abre um browser real (não headless) para você fazer o login normalmente.
Os cookies são salvos em data/shopee_session.json e reutilizados pelo scraper.

Uso:
    python setup_session.py
"""

import json
import os
import sys
from pathlib import Path

SESSION_FILE = Path("data/shopee_session.json")


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Erro: Playwright não instalado. Execute: pip install playwright && playwright install chromium")
        sys.exit(1)

    SESSION_FILE.parent.mkdir(exist_ok=True)

    print("=" * 55)
    print("  CONFIGURAÇÃO DA SESSÃO SHOPEE")
    print("=" * 55)
    print()
    print("Um browser vai abrir. Faça o login na sua conta Shopee.")
    print("Quando terminar de logar, volte aqui e pressione ENTER.")
    print()
    input("Pressione ENTER para abrir o browser...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,   # browser visível para o login manual
            args=["--start-maximized"],
        )
        ctx = browser.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        page.goto("https://shopee.com.br/buyer/login", wait_until="domcontentloaded", timeout=30000)

        print()
        print("Browser aberto em shopee.com.br/buyer/login")
        print("Faça o login e depois pressione ENTER aqui.")
        input("ENTER após o login: ")

        # Salva cookies e storage
        cookies = ctx.cookies()
        storage = ctx.storage_state()

        data = {
            "cookies": cookies,
            "storage": storage,
        }
        SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        print()
        print(f"Sessao salva em: {SESSION_FILE}")
        print(f"Cookies salvos: {len(cookies)}")

        # Confirma que está logado
        csrf = next((c["value"] for c in cookies if c["name"] in ("SPC_SC_TK", "SPC_CDS")), None)
        if csrf:
            print("Token CSRF detectado — sessao parece valida.")
        else:
            print("Aviso: token CSRF nao encontrado. Verifique se o login foi concluido.")

        browser.close()

    print()
    print("Configuracao concluida! Agora execute: python main.py")


if __name__ == "__main__":
    main()
