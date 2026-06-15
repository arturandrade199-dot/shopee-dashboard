#!/usr/bin/env python3
"""
Importa cookies da Shopee para o arquivo de sessão do scraper.

Aceita dois formatos:

  Formato A — Cookie-Editor (recomendado, inclui cookies HttpOnly):
    1. Instale: https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm
    2. Acesse shopee.com.br já logado
    3. Clique no ícone da extensão → Export → JSON
    4. Cole o JSON aqui quando solicitado

  Formato B — document.cookie (NÃO recomendado, falta cookies HttpOnly):
    1. Abra shopee.com.br → F12 → Console
    2. Digite: document.cookie
    3. Copie e cole aqui

Uso:
    python import_cookies.py
"""

import json
from pathlib import Path

SESSION_FILE = Path("data/shopee_session.json")

# Cookies essenciais da Shopee para autenticação de API
ESSENTIAL = {"SPC_SC", "SPC_SC_TK", "SPC_CDS", "SPC_F", "SPC_U", "csrftoken"}
HTTPONLY  = {"SPC_SC", "SPC_SC_TK", "SPC_CDS"}  # só visíveis via Cookie-Editor


def from_cookie_editor_json(raw: str) -> list:
    """Parseia JSON exportado pela extensão Cookie-Editor."""
    items = json.loads(raw)
    cookies = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name  = item.get("name", "").strip()
        value = item.get("value", "").strip()
        if not name:
            continue
        cookies.append({
            "name":     name,
            "value":    value,
            "domain":   item.get("domain", ".shopee.com.br"),
            "path":     item.get("path", "/"),
            "secure":   item.get("secure", True),
            "httpOnly": item.get("httpOnly", False),
            "sameSite": item.get("sameSite", "None"),
            "expires":  item.get("expirationDate", -1),
        })
    return cookies


def from_document_cookie(raw: str) -> list:
    """Parseia string do document.cookie (sem cookies HttpOnly)."""
    cookies = []
    for part in raw.split(";"):
        part = part.strip().strip('"').strip("'")
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies.append({
            "name":     name.strip(),
            "value":    value.strip(),
            "domain":   ".shopee.com.br",
            "path":     "/",
            "secure":   True,
            "httpOnly": False,
            "sameSite": "None",
            "expires":  -1,
        })
    return cookies


def detect_and_parse(raw: str) -> list:
    raw = raw.strip()
    if raw.startswith("["):
        return from_cookie_editor_json(raw)
    return from_document_cookie(raw)


def main():
    print("=" * 55)
    print("  IMPORTAR COOKIES DA SHOPEE")
    print("=" * 55)
    print()
    print("RECOMENDADO — Cookie-Editor (captura cookies HttpOnly):")
    print("  1. Instale a extensao Cookie-Editor no Chrome")
    print("  2. Acesse shopee.com.br (ja logado)")
    print("  3. Clique no icone -> Export -> JSON")
    print("  4. Cole abaixo e pressione ENTER duas vezes")
    print()
    print("Alternativa — document.cookie (sem cookies HttpOnly):")
    print("  1. F12 -> Console -> document.cookie -> copie e cole")
    print()
    print("Cole aqui (ENTER duas vezes para finalizar):")
    print()

    lines = []
    try:
        while True:
            line = input()
            if line == "" and lines:
                break
            lines.append(line)
    except EOFError:
        pass

    raw = "\n".join(lines).strip()
    if not raw:
        print("Nenhum dado fornecido. Encerrando.")
        return

    try:
        cookies = detect_and_parse(raw)
    except Exception as exc:
        print(f"Erro ao parsear: {exc}")
        return

    if not cookies:
        print("Nenhum cookie encontrado. Verifique o formato.")
        return

    names = {c["name"] for c in cookies}
    httponly_found = {c["name"] for c in cookies if c.get("httpOnly")}

    print(f"\nCookies importados : {len(cookies)}")
    print(f"HttpOnly           : {len(httponly_found)} ({sorted(httponly_found)[:5]})")

    missing_essential = ESSENTIAL - names
    missing_httponly  = HTTPONLY  - names

    if missing_httponly:
        print()
        print(f"AVISO: Cookies HttpOnly ausentes: {sorted(missing_httponly)}")
        print("A API da Shopee pode retornar 403 sem eles.")
        print("Use a extensao Cookie-Editor para exportar todos os cookies.")

    if not missing_essential - HTTPONLY:
        print("OK: Todos os cookies essenciais non-HttpOnly estao presentes.")

    # Monta storage_state no formato do Playwright
    storage_state = {"cookies": cookies, "origins": []}
    data = {"cookies": cookies, "storage": storage_state}

    SESSION_FILE.parent.mkdir(exist_ok=True)
    SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nSessao salva em: {SESSION_FILE}")
    print("Execute agora: python main.py --dry-run --limit 5")


if __name__ == "__main__":
    main()
