/**
 * Shopee DOM Scraper — console do navegador
 *
 * Cole no console do DevTools em qualquer página de busca da Shopee.
 * O script acumula dados entre páginas via localStorage.
 *
 * Funções disponíveis após rodar:
 *   shopee_export()  → baixa CSV com tudo acumulado
 *   shopee_clear()   → apaga dados do localStorage
 *   shopee_preview() → mostra tabela no console
 */
(function () {
  const STORAGE_KEY = "shopee_scrape_data";
  const BASE_URL = "https://shopee.com.br";

  // --- Página atual ---
  const pageEl = document.querySelector(".shopee-page-controller__page--active");
  const page = pageEl ? pageEl.innerText.trim() : "1";

  // --- Cards de produto ---
  const cards = document.querySelectorAll('[data-sqe="item"]');
  if (!cards.length) {
    console.warn("⚠️ Nenhum card encontrado. Aguarde a página carregar e tente novamente.");
    return;
  }

  const rows = [];

  cards.forEach((card, index) => {
    // Link
    const linkEl = card.querySelector("a[href]");
    const url = linkEl ? BASE_URL + linkEl.getAttribute("href").split("?")[0] : "";

    // Imagem
    const imgEl = card.querySelector("img");
    const image = imgEl ? imgEl.src || imgEl.dataset.src || "" : "";

    // Texto bruto (para regex)
    const text = card.innerText.replace(/\n+/g, " ").trim();
    if (!text) return;

    // Título = primeira linha não-vazia do card
    const lines = card.innerText.split("\n").map(l => l.trim()).filter(Boolean);
    const title = lines[0] || text.slice(0, 120);

    // Preços — pega todos os "R$ X,XX" e usa o menor como atual
    const allPrices = [...text.matchAll(/R\$\s*(\d+(?:[.,]\d{1,2})?)/g)]
      .map(m => ({ raw: m[0].trim(), value: parseFloat(m[1].replace(",", ".")) }))
      .filter(p => !isNaN(p.value));

    const price = allPrices.length ? allPrices[0].raw : "";
    const originalPrice = allPrices.length > 1 ? allPrices[allPrices.length - 1].raw : "";

    // Desconto
    const discountMatch = text.match(/-?\d+\s*%/);
    const discount = discountMatch ? discountMatch[0].replace(/\s+/, "") : "";

    // Rating (ex: "4.8" ou "4,8")
    const ratingMatch = text.match(/\b([45]\.[0-9])\b/);
    const rating = ratingMatch ? ratingMatch[1] : "";

    // Vendidos — formatos: "1.234 vendidos", "2mil+ vendidos", "500+ vendidos"
    const soldMatch = text.match(/(\d+(?:[.,]\d+)?(?:\s?mil)?)\s*(?:\+\s*)?vendidos/i);
    const sold = soldMatch ? soldMatch[0].trim() : "";

    // Frete / badge
    const lower = text.toLowerCase();
    const badge = lower.includes("frete grátis") || lower.includes("frete gratis")
      ? "Frete Grátis"
      : lower.includes("indicado")
      ? "Indicado"
      : "";

    rows.push({
      page,
      position: index + 1,
      title,
      price,
      originalPrice,
      discount,
      sold,
      rating,
      badge,
      url,
      image,
    });
  });

  if (!rows.length) {
    console.warn("⚠️ Cards encontrados mas sem dados extraídos.");
    return;
  }

  // --- Acumula no localStorage ---
  const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  // Evita duplicatas pela URL
  const existingUrls = new Set(existing.map(r => r.url));
  const newRows = rows.filter(r => !existingUrls.has(r.url));
  const allData = [...existing, ...newRows];
  localStorage.setItem(STORAGE_KEY, JSON.stringify(allData));

  console.log(
    `✅ Página ${page}: ${newRows.length} novos produtos (${rows.length - newRows.length} duplicatas ignoradas). ` +
    `Total acumulado: ${allData.length}`
  );
  console.table(newRows.slice(0, 5));
  console.log("💡 Navegue para a próxima página e rode o script novamente.");
  console.log("📥 Para exportar: shopee_export()  |  🗑️ Para limpar: shopee_clear()  |  👁️ Preview: shopee_preview()");

  // --- Funções globais ---
  window.shopee_export = function () {
    const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (!data.length) { console.warn("Nada para exportar."); return; }

    const headers = Object.keys(data[0]);
    const csv = [
      headers.join(","),
      ...data.map(r =>
        headers.map(h => `"${String(r[h] ?? "").replace(/"/g, '""')}"`).join(",")
      ),
    ].join("\n");

    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `shopee_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);

    console.log(`📥 ${data.length} produtos exportados.`);
  };

  window.shopee_clear = function () {
    localStorage.removeItem(STORAGE_KEY);
    console.log("🗑️ Dados limpos do localStorage.");
  };

  window.shopee_preview = function () {
    const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    console.log(`Total: ${data.length} produtos`);
    console.table(data);
  };
})();
