/**
 * Shopee Affiliate Scraper — console do navegador
 *
 * Detecta automaticamente a página e extrai os dados corretos.
 * Acumula tudo no localStorage vinculando as 3 etapas por produto.
 *
 * ─── FLUXO ──────────────────────────────────────────────────────
 *
 *  PÁGINA 1  affiliate.shopee.com.br/offer/product_offer
 *    → Cola o script → extrai todos os cards da página
 *    → Clique em um produto
 *
 *  PÁGINA 2  Detalhes da Oferta do Produto (affiliate portal)
 *    → Cola o script → extrai comissões por canal
 *    → Clique em "Ver produto" (link azul)
 *
 *  PÁGINA 3  shopee.com.br/produto-i.xxx.yyy
 *    → Cola o script → extrai tudo: info, combos, loja, cupons, similares
 *    → Pressione BACK → próximo produto → repita
 *
 * ─── FUNÇÕES DISPONÍVEIS ────────────────────────────────────────
 *   shopee_export()              → baixa JSON com todos os produtos
 *   shopee_status()              → resumo do que foi coletado por fase
 *   shopee_scroll()              → rola a página até o fim (carrega lazy sections)
 *   shopee_set_videos(id, n)     → registra nº de vídeos (verificar no app Android)
 *   shopee_set_videos()          → lista produtos e IDs disponíveis
 *   shopee_clear()               → apaga localStorage e começa do zero
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'shopee_affiliate_data';
  const CURRENT_KEY = 'shopee_affiliate_current';

  // ── Persistência ─────────────────────────────────────────────

  const db = {
    all:        ()  => JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'),
    save:       (d) => localStorage.setItem(STORAGE_KEY, JSON.stringify(d)),
    current:    ()  => JSON.parse(localStorage.getItem(CURRENT_KEY) || 'null'),
    setCurrent: (p) => p
      ? localStorage.setItem(CURRENT_KEY, JSON.stringify(p))
      : localStorage.removeItem(CURRENT_KEY),
  };

  // ── Parsers ───────────────────────────────────────────────────

  function parsePrice(text) {
    const m = (text || '').match(/R\$\s*([\d.,]+)/);
    if (!m) return 0;
    return parseFloat(m[1].replace(/\./g, '').replace(',', '.')) || 0;
  }

  function parseSold(text) {
    if (!text) return 0;
    const t = text.toLowerCase();
    const mil = t.match(/([\d,]+)\s*mil/);
    if (mil) return Math.round(parseFloat(mil[1].replace(',', '.')) * 1000);
    const n = t.match(/\d+/);
    return n ? parseInt(n[0]) : 0;
  }

  function parsePct(text) {
    const m = (text || '').match(/(\d+)\s*%/);
    return m ? parseInt(m[1]) : 0;
  }

  function text(el) {
    return el?.innerText?.trim() || '';
  }

  function slug(str) {
    return (str || '').toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60);
  }

  // Encontra seção pelo título (texto exato ou parcial)
  function findSection(titleText) {
    return [...document.querySelectorAll('*')].find(el =>
      el.children.length > 0 &&
      el.innerText?.toLowerCase().includes(titleText.toLowerCase()) &&
      el.innerText.length < 8000
    ) || null;
  }

  // ── Detecção de página ────────────────────────────────────────

  const { hostname, pathname, href } = window.location;
  const isAffiliate   = hostname.includes('affiliate');
  const isShopeeMain  = hostname === 'shopee.com.br';

  // Página 2: detalhe do afiliado — mesma URL base mas com item na path
  // ou detectado pelo conteúdo (tabela de comissão presente)
  const hasCommissionTable = !!document.querySelector('table') &&
    document.body.innerText.includes('Comissão Estimada');

  const PAGE =
    isAffiliate && !hasCommissionTable ? 'affiliate-list' :
    isAffiliate && hasCommissionTable  ? 'affiliate-detail' :
    isShopeeMain                       ? 'product-page' :
    'unknown';

  console.log(`📍 Página: ${PAGE} | ${href.slice(0, 80)}`);

  // ════════════════════════════════════════════════════════════════
  //  PÁGINA 1 — Lista de ofertas do afiliado
  // ════════════════════════════════════════════════════════════════

  function scrapeAffiliateList() {
    // Tenta vários seletores para os cards (o Shopee usa CSS modules com hashes)
    const candidates = [
      '[class*="product-item"]',
      '[class*="item-card"]',
      '[class*="offer-item"]',
      '[class*="ProductCard"]',
    ];

    let cards = [];
    for (const sel of candidates) {
      cards = [...document.querySelectorAll(sel)];
      if (cards.length) break;
    }

    // Fallback: qualquer elemento que contenha "Taxa de comissão"
    if (!cards.length) {
      cards = [...document.querySelectorAll('*')].filter(el =>
        el.children.length > 2 &&
        el.children.length < 20 &&
        el.innerText?.includes('Taxa de comissão') &&
        el.innerText.length < 600
      );
    }

    if (!cards.length) {
      console.warn('⚠️ Nenhum card encontrado. Aguarde carregar e tente de novo.');
      return;
    }

    const data     = db.all();
    const products = [];

    cards.forEach((card, i) => {
      const t = card.innerText;
      if (!t.includes('Taxa de comissão') && !t.includes('comissão')) return;

      // Nome: primeira linha longa (> 15 chars) ou link mais proeminente
      const lines  = t.split('\n').map(l => l.trim()).filter(Boolean);
      const linkEl = card.querySelector('a[href]');
      const name   = lines.find(l => l.length > 15 && !l.match(/^R\$/)) || '';
      if (!name) return;

      const id = slug(name);

      // "Indicado" costuma ser um <img>, não texto — checa alt e src também
      const hasIndicado = /indicado/i.test(t) ||
        [...card.querySelectorAll('img')].some(img =>
          /indicado/i.test(img.alt || img.src || '')
        );
      const badge =
        /comissão extra/i.test(t) ? 'Comissão Extra' :
        hasIndicado               ? 'Indicado' : '';

      const price           = parsePrice(t);
      const sold_raw        = t.match(/([\d.,]+\s*mil\+?)\s*venda/i)?.[0]?.trim() || '';
      const commission_rate = parsePct(t.match(/Taxa de comissão[^\n]*/i)?.[0]);
      const detail_href     = linkEl?.href || '';

      const product = {
        id, name, badge, price, sold_raw,
        commission_rate, detail_href,
        _phase: 'list',
        list_scraped_at: new Date().toISOString(),
      };

      if (!data[id]) data[id] = product;
      products.push(product);
    });

    db.save(data);

    console.log(`✅ Lista: ${products.length} produtos extraídos`);
    console.table(products.map(p => ({
      nome:      p.name.slice(0, 45),
      badge:     p.badge,
      preço:     `R$${p.price}`,
      vendas:    p.sold_raw,
      comissão:  `${p.commission_rate}%`,
    })));
    console.log('💡 Clique em um produto → vá à página de detalhe → cole o script novamente.');
  }

  // ════════════════════════════════════════════════════════════════
  //  PÁGINA 2 — Detalhe da oferta (portal do afiliado)
  // ════════════════════════════════════════════════════════════════

  function scrapeAffiliateDetail() {
    // Nome do produto
    const nameEl = document.querySelector('h1, h2, [class*="product-name"], [class*="pdp-title"]');
    const name   = text(nameEl);
    const id     = slug(name);

    const pageText = document.body.innerText;

    // Rating
    const ratingMatch = pageText.match(/(\d\.\d)\s*(?:★|⭐|\d+mil)/);
    const rating = ratingMatch ? parseFloat(ratingMatch[1]) : 0;

    // Vendas
    const sold_raw = pageText.match(/([\d.,]+\s*mil\+?)\s*venda/i)?.[1]?.trim() || '';

    // Preço
    const price = parsePrice(pageText);

    // Comissão Extra (bloco único acima da tabela)
    const extraBlock = pageText.match(/(\d+)%\s*\(R\$([\d.,]+)\)/);
    const commission_extra_pct   = extraBlock ? parseInt(extraBlock[1]) : 0;
    const commission_extra_value = extraBlock ? parseFloat(extraBlock[2].replace(',', '.')) : 0;

    // Tabela de canais: Shopee Vídeo / Redes sociais / Shopee Lives
    const channels = [];
    const rows     = document.querySelectorAll('table tr');

    rows.forEach(row => {
      const cells = row.querySelectorAll('td');
      if (cells.length < 3) return;

      const channelName = text(cells[0]);
      if (!channelName || /tipo de canal/i.test(channelName)) return;

      // Célula 1 = Comissão Extra (compartilhada)
      // Célula 2 = Comissão da Shopee  "3% (R$0,60)"
      // Célula 3 = Comissão Estimada   "R$2,61"
      const shopee_pct   = parsePct(text(cells[2]));
      const shopee_value = parsePrice(text(cells[2]));
      const estimated    = parsePrice(text(cells[3] || cells[2]));

      channels.push({ channel: channelName, shopee_pct, shopee_value, estimated });
    });

    // Link "Ver produto"
    const verProdLink = [...document.querySelectorAll('a')].find(a =>
      /ver produto/i.test(a.innerText) || (a.href?.includes('shopee.com.br') && !a.href.includes('affiliate'))
    );
    const product_url = verProdLink?.href || '';

    // Salva e marca como atual
    const data     = db.all();
    const existing = data[id] || { id, name };

    const updated = {
      ...existing,
      id, name,
      rating:                 rating || existing.rating || 0,
      sold_raw:               sold_raw || existing.sold_raw || '',
      price:                  price || existing.price || 0,
      commission_extra_pct,
      commission_extra_value,
      channels,
      product_url,
      _phase:                 'detail',
      detail_scraped_at:      new Date().toISOString(),
    };

    data[id] = updated;
    db.save(data);
    db.setCurrent(updated);

    console.log(`✅ Detalhe: ${name.slice(0, 60)}`);
    console.log(`   Rating: ${rating} | Vendas: ${sold_raw} | Comissão Extra: ${commission_extra_pct}%`);
    console.table(channels);
    if (product_url) {
      console.log(`🔗 Ver produto: ${product_url}`);
    } else {
      console.warn('⚠️ Link "Ver produto" não encontrado — copie a URL manualmente.');
    }
    console.log('💡 Clique em "Ver produto" → cole o script na página do produto.');
  }

  // ════════════════════════════════════════════════════════════════
  //  PÁGINA 3 — Página do produto (shopee.com.br)
  // ════════════════════════════════════════════════════════════════

  function scrapeProductPage() {
    const current  = db.current();
    const pageText = document.body.innerText;

    // ── Título ──
    const titleEl = document.querySelector('h1');
    const title   = text(titleEl) || document.title;

    // ── Rating ──
    // Estrelas são SVG — não aparecem no innerText.
    // O número "4.9" aparece imediatamente antes de "X mil Avaliações".
    const ratingMatch = pageText.match(/(\d\.\d)\s+[\d,]+(?:\s*mil\s+)?[Aa]valia/);
    const rating      = ratingMatch ? parseFloat(ratingMatch[1]) : 0;

    // ── Avaliações ──
    const reviewsMatch = pageText.match(/([\d,]+(?:\s*mil)?)\s+[Aa]valia/i);
    const reviews_raw  = reviewsMatch?.[1]?.trim() || '';
    const reviews_num  = parseSold(reviews_raw);

    // ── Vendidos ──
    // Formato: "10mil+ Vendidos"
    const soldMatch = pageText.match(/([\d.,]+(?:\s*mil)?\+?)\s+[Vv]endidos/i);
    const sold_raw  = soldMatch?.[1]?.trim() || '';
    const sold_num  = parseSold(sold_raw);

    // ── Flash sale ──
    const has_flash_sale = /ofertas?\s+relâmpago/i.test(pageText);

    // ── Preços ──
    // "R$19,99 com cupom" / "ou R$20,09"
    // Classes de preço têm hash no Shopee — usamos texto direto.
    const priceCouponM  = pageText.match(/R\$\s*([\d.,]+)\s+com\s+cupom/i);
    const priceRegularM = pageText.match(/ou\s+R\$\s*([\d.,]+)/i);
    let price_coupon    = priceCouponM
      ? parseFloat(priceCouponM[1].replace(/\./g,'').replace(',','.'))
      : 0;
    let price_regular   = priceRegularM
      ? parseFloat(priceRegularM[1].replace(/\./g,'').replace(',','.'))
      : 0;
    // Fallback: primeiros dois valores R$ da página
    if (!price_coupon) {
      const all = [...pageText.matchAll(/R\$\s*([\d.,]+)/g)]
        .map(m => parseFloat(m[1].replace(/\./g,'').replace(',','.')) )
        .filter(v => v > 0);
      price_coupon  = all[0] || 0;
      price_regular = all[1] || price_coupon;
    }

    // ── Frete ──
    const shipM    = pageText.match(/[Ff]rete\s+[Gg]rátis[^\n]*|[Ff]rete:[^\n]{0,60}/);
    const shipping = shipM?.[0]?.trim() || '';

    // ── Variantes ──
    // Classes são hashed no Shopee — filtra botões curtos que não são ações
    const variants = [...new Set(
      [...document.querySelectorAll('button')]
        .filter(btn => {
          const t = btn.innerText.trim();
          if (!t || t.length > 20) return false;
          if (/\n/.test(t)) return false;           // "Compre Com Cupom\nR$19,99"
          if (/^\d+$/.test(t)) return false;        // "1","2","3" (qtd/paginação)
          if (/^\d+[.,]\d+$/.test(t)) return false; // "4.9" (rating)
          if (t === '...') return false;
          if (/adicionar|comprar|carrinho|obter|ativar|chat|favorit|compartilhar|denunciar|conversar|ver tudo/i.test(t)) return false;
          if (/^[-+]$/.test(t)) return false;
          return true;
        })
        .map(btn => btn.innerText.trim())
    )];

    // ── Badges de cupom no topo ("55% OFF", "60% Cashback") ──
    const couponBadges = [...new Set(
      (pageText.match(/\d+%\s*(?:OFF|Cashback)[^\n]*/gi) || [])
        .map(s => s.replace(/\n/g, ' ').trim())
    )].slice(0, 5);

    // ── Combos ──────────────────────────────────────────────────
    const combos = [];
    // Encontra o header "Combos" (pode ter filhos como "Veja Mais")
    const comboHeader = [...document.querySelectorAll('*')]
      .filter(el => /^combos/i.test(el.innerText?.trim()) && el.innerText.length < 30)
      .sort((a, b) => a.innerText.length - b.innerText.length)[0];

    if (comboHeader) {
      // Sobe até encontrar o container do combo — para quando achar "Adicionar Ao Carrinho"
      // (botão único no bloco de combo, não aparece antes dele na página)
      let wrap = comboHeader;
      for (let i = 0; i < 12; i++) {
        wrap = wrap.parentElement;
        if (!wrap) break;
        if (/adicionar ao carrinho/i.test(wrap.innerText)) break;
      }
      if (wrap) {
        [...wrap.querySelectorAll('*')]
          .filter(el => {
            const imgs = el.querySelectorAll('img').length;
            return imgs >= 1 && imgs <= 3 &&
              /R\$/.test(el.innerText) &&
              el.innerText.length > 15 &&
              el.innerText.length < 500;
          })
          .slice(0, 8)  // max 8 itens num combo
          .forEach(item => {
            const n = (text(item.querySelector('a')) || '').split('\n')[0].trim() ||
              item.innerText.split('\n').find(l => l.length > 5 && !/R\$/.test(l)) || '';
            if (!n) return;
            const prices = [...item.innerText.matchAll(/R\$\s*([\d.,]+)/g)]
              .map(m => parseFloat(m[1].replace(',','.')));
            combos.push({
              name:          n.slice(0, 100),
              price_coupon:  prices[0] || 0,
              price_regular: prices[1] || 0,
            });
          });
      }
    }

    // ── Informações da loja ──────────────────────────────────────
    const storeWrap = [...document.querySelectorAll('*')].find(el =>
      /último login/i.test(el.innerText) &&
      el.innerText.length > 50 &&
      el.innerText.length < 1500
    );
    const st = text(storeWrap);
    const store = {
      name:            st.split('\n')
        .find(l => l.trim().length > 2 && !/login|avalia|resposta|anos|produto|seguidor/i.test(l))
        ?.trim() || '',
      last_login:      st.match(/último login\s+([^\n]+)/i)?.[1]?.trim() || '',
      years_on_shopee: st.match(/(\d+\s*anos?)/i)?.[0] || '',
      response_rate:   st.match(/taxa de resposta[^\n]*/i)?.[0]?.match(/(\d+%)/)?.[1]
                       || st.match(/(\d+)%/)?.[0] || '',
      response_time: (() => {
        const m = st.match(/responde([^\n]+)\n?\s*([^\n]{1,25})?/i);
        if (!m) return '';
        const base = ('responde' + m[1]).trim();
        const next = m[2]?.trim();
        return next && !/login|seguidor|avalia|produto|taxa|shopee|desde/i.test(next)
          ? base + ' ' + next : base;
      })(),
      followers:       st.match(/([\d,]+(?:\s*mil)?)\s*[Ss]eguidores/i)?.[1]?.trim() ||
                       st.match(/[Ss]eguidores\s*\n?\s*([\d,]+(?:\s*mil)?)/i)?.[1]?.trim() || '',
      total_reviews:   st.match(/[Aa]valia[çc][õo]es?\s+([\d.,]+(?:\s*mil)?)/i)?.[1]?.trim()
                       || st.match(/([\d.,]+(?:\s*mil)?)\s*[Aa]valia/i)?.[1]?.trim() || '',
      total_products:  parseInt(
        st.match(/[Pp]rodutos\s*(\d+)/i)?.[1] || st.match(/(\d+)\s*[Pp]rodutos/i)?.[1] || 0
      ),
    };

    // ── Detalhes do produto (specs) ──────────────────────────────
    const product_details = {};
    const detailHeader = [...document.querySelectorAll('*')].find(el =>
      /detalhes\s+do\s+produto/i.test(el.innerText?.trim()) &&
      el.innerText.length < 50
    );
    if (detailHeader) {
      let detailSection = detailHeader;
      for (let i = 0; i < 5; i++) {
        detailSection = detailSection.parentElement;
        if (!detailSection) break;
        if (detailSection.innerText.length > 200) break;
      }
      if (detailSection) {
        // Tenta <table>
        detailSection.querySelectorAll('tr').forEach(row => {
          const cells = row.querySelectorAll('td');
          if (cells.length >= 2) {
            const k = text(cells[0]), v = text(cells[1]);
            if (k && v && k !== v) product_details[k] = v;
          }
        });
        // Fallback: pares de filhos
        if (!Object.keys(product_details).length) {
          [...detailSection.querySelectorAll('*')]
            .filter(el => el.children.length === 2 && el.innerText.length < 200)
            .forEach(row => {
              const k = text(row.children[0]), v = text(row.children[1]);
              if (k && v && k !== v) product_details[k] = v;
            });
        }
      }
    }

    // ── Cupons de loja ───────────────────────────────────────────
    // Abordagem por texto: cada cupom tem desconto + condição + "Válido até"
    const store_coupons = [];
    // Regex captura blocos: "55% OFF\nNas compras...\nVálido até: 12/08/2026"
    const couponBlocks = pageText.match(
      /(\d+%[^\n]*(?:OFF|cashback|Cashback)[^\n]*)[\s\S]{0,200}?[Vv]álido até[:\s]*([\d/]+)/gi
    ) || [];
    couponBlocks.forEach(block => {
      const discount    = block.match(/(\d+%[^\n]*(?:OFF|cashback|Cashback)[^\n]*)/i)?.[1]?.trim() || '';
      const conditions  = block.match(/[Nn]as compras[^\n]*/i)?.[0]?.trim() || '';
      const valid_until = block.match(/[Vv]álido até[:\s]*([\d/]+)/i)?.[1] || '';
      if (discount) store_coupons.push({ discount, conditions, valid_until });
    });

    // ── Grid de produtos (mesmo vendedor / indicados / escolhas) ─
    function scrapeGrid(sectionTitle) {
      // Entre todos os elementos que começam com o título, pega o de menor innerText
      // (o mais específico — evita pegar containers com todo o conteúdo da seção)
      const header = [...document.querySelectorAll('*')]
        .filter(el =>
          el.innerText?.toLowerCase().trim().startsWith(sectionTitle.toLowerCase()) &&
          el.innerText.length < sectionTitle.length + 80
        )
        .sort((a, b) => a.innerText.length - b.innerText.length)[0];
      if (!header) return [];

      let section = header;
      for (let i = 0; i < 10; i++) {
        section = section.parentElement;
        if (!section) return [];
        if (section.querySelectorAll('img').length >= 2) break;
      }

      // Pega items: 1-4 imagens (produto + estrela + badges), tem preço, texto razoável
      // Shopee usa img para ícone de estrela de rating, então img.length pode ser 2 ou 3
      const rawItems = [...section.querySelectorAll('*')]
        .filter(el => {
          const imgs = el.querySelectorAll('img').length;
          return imgs >= 1 && imgs <= 4 &&
            /R\$/.test(el.innerText) &&
            el.innerText.length < 600;
        });

      // Deduplica por URL (mantém o primeiro/menor de cada produto)
      const seen = new Set();
      const items = rawItems.filter(el => {
        const url = el.querySelector('a[href]')?.href || '';
        if (!url || seen.has(url)) return false;
        seen.add(url);
        return true;
      });

      return items.map(item => {
        // Texto base do item; expande para o pai se faltar rating ou vendidos
        let t = item.innerText;
        if (!/\b\d\.\d\b/.test(t) || !/vendid/i.test(t)) {
          const pt = item.parentElement?.innerText || '';
          if (pt.length < 1200) t = pt;
        }

        // Nome: pula linhas de badge de desconto ("-33%") que aparecem antes do título
        const anchorText = text(item.querySelector('a[href]'));
        const anchorLines = anchorText.split('\n').map(l => l.trim()).filter(Boolean);
        const name = anchorLines.find(l => l.length > 5 && !/^-\d+%$/.test(l) && !/^R\$/.test(l)) ||
          t.split('\n').find(l => l.length > 5 && !/R\$/.test(l) && !/^-\d+%$/.test(l)) || '';

        const prices = [...t.matchAll(/R\$\s*([\d.,]+)/g)]
          .map(m => parseFloat(m[1].replace(/\./g, '').replace(',', '.')));

        // Rating — DOM direto: <img alt="rating-star"> + <span> irmão
        const starImg = item.querySelector('img[alt="rating-star"]') ||
                        item.querySelector('img[alt*="vehicle"]');
        const ratingSpan = starImg?.nextElementSibling ||
                           starImg?.parentElement?.querySelector('span');
        const ratingFromDOM = parseFloat(ratingSpan?.innerText?.trim() || '0') || 0;
        const rating = ratingFromDOM || parseFloat(t.match(/\b(\d\.\d)\b/)?.[1] || 0);

        // Sold — DOM direto: folha com "Vendido(s)"
        const soldLeaf = [...item.querySelectorAll('div,span')].find(el =>
          !el.querySelector('div,span') &&
          /^\s*[\d.,]+(?:\s*mil)?\+?\s*[Vv]endid/i.test(el.innerText.trim()) &&
          el.innerText.length < 30
        );
        const sold_raw = (soldLeaf?.innerText || t)
          .match(/([\d.,]+(?:\s*mil)?\+?)\s*[Vv]endid/i)?.[1]?.trim() || '';

        const discount = parseInt(t.match(/-(\d+)%/)?.[1] || 0);
        const hasInd   = /indicado/i.test(t) ||
          [...item.querySelectorAll('img')]
            .some(img => /indicado/i.test(img.alt || img.src || ''));

        return {
          name:     name.slice(0, 120),
          price:    prices[0] || 0,
          rating,
          sold_raw,
          sold_num: parseSold(sold_raw),
          discount,
          badge:    hasInd ? 'Indicado' : '',
          url:      item.querySelector('a[href]')?.href || '',
        };
      }).filter(p => p.name.length > 3);
    }

    const main_store_choices   = scrapeGrid('principais escolhas da loja');
    const same_seller_products = scrapeGrid('produtos do mesmo vendedor');
    const recommended_products = scrapeGrid('você também pode gostar');

    // Avisa se seções do fundo da página não foram encontradas (lazy loading)
    if (!same_seller_products.length || !recommended_products.length) {
      console.warn('⚠️ Seções "Mesmo Vendedor" / "Você Também Pode Gostar" vazias.');
      console.warn('   Role a página ATÉ O FIM, aguarde carregar e execute o script novamente.');
      console.warn('   Atalho: shopee_scroll() rola automaticamente e avisa quando terminar.');
    }

    // ── Monta e salva ────────────────────────────────────────────
    const id       = current?.id || slug(title);
    const allData  = db.all();
    const existing = allData[id] || current || {};

    const productData = {
      ...existing,
      id, title,
      rating:             rating || existing.rating || 0,
      reviews_raw, reviews_num,
      sold_raw, sold_num,
      price_coupon, price_regular,
      has_flash_sale, shipping, variants,
      coupon_badges: couponBadges,
      combos, store, product_details,
      store_coupons,
      main_store_choices,
      same_seller_products,
      recommended_products,
      product_url:        href,
      _phase:             'complete',
      product_scraped_at: new Date().toISOString(),
    };

    allData[id] = productData;
    db.save(allData);
    db.setCurrent(null);

    console.log(`✅ Produto completo: ${title.slice(0, 65)}`);
    console.log(`   Rating ${rating} | Vendidos: ${sold_raw} | Preço: R$${price_coupon} (cupom) / R$${price_regular}`);
    console.log(`   Combos: ${combos.length} | Cupons da loja: ${store_coupons.length}`);
    console.log(`   Mesmo vendedor: ${same_seller_products.length} | Indicados: ${recommended_products.length}`);
    console.log('💡 Pressione BACK → próximo produto → repita. Para exportar: shopee_export()');
  }

  // ── Funções globais ──────────────────────────────────────────

  window.shopee_export = function () {
    const products = Object.values(db.all());
    if (!products.length) { console.warn('Nada para exportar.'); return; }

    const json = JSON.stringify(products, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const a    = document.createElement('a');
    a.href     = URL.createObjectURL(blob);
    const _ts = new Date().toISOString().slice(0, 19).replace('T', '_').replace(/:/g, '-');
    a.download = `shopee_affiliate_${_ts}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
    console.log(`📥 ${products.length} produtos exportados.`);
  };

  window.shopee_status = function () {
    const products = Object.values(db.all());
    const byPhase  = products.reduce((acc, p) => {
      acc[p._phase] = (acc[p._phase] || 0) + 1;
      return acc;
    }, {});
    console.log(`Total: ${products.length} produtos`);
    console.table(byPhase);
    console.table(products.map(p => ({
      nome:      (p.title || p.name || '').slice(0, 40),
      fase:       p._phase,
      comissão:  p.commission_rate ? p.commission_rate + '%'
        : p.commission_extra_pct ? '+' + p.commission_extra_pct + '% extra' : '—',
      vendidos:  p.sold_raw || '—',
      preço:     p.price_coupon ? 'R$' + p.price_coupon : p.price ? 'R$' + p.price : '—',
    })));
  };

  window.shopee_clear = function () {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(CURRENT_KEY);
    console.log('🗑️ Dados limpos.');
  };

  /**
   * Rola a página até o fim em etapas para forçar o carregamento lazy das seções.
   * Após concluir, avisa para colar o script novamente.
   */
  window.shopee_scroll = function () {
    const total   = document.body.scrollHeight;
    const step    = Math.ceil(total / 10);
    let   current = 0;
    console.log('⏬ Rolando a página para carregar seções lazy...');
    const timer = setInterval(() => {
      current += step;
      window.scrollTo(0, current);
      if (current >= total) {
        clearInterval(timer);
        window.scrollTo(0, 0);
        console.log('✅ Rolagem completa. Cole o script novamente para extrair os dados.');
      }
    }, 400);
  };

  /**
   * Registra manualmente a quantidade de vídeos de afiliado de um produto.
   * Verificar no app Shopee Vídeo (Android) e chamar aqui antes de exportar.
   *
   * Uso:
   *   shopee_set_videos('percarbonato-de-sodio-calisul', 2)
   *   shopee_set_videos()   → lista todos os produtos com IDs para referência
   */
  window.shopee_set_videos = function (productId, videoCount) {
    const data = db.all();

    if (!productId) {
      console.log('Produtos coletados (use o id para registrar os vídeos):');
      console.table(Object.values(data).map(p => ({
        id:         p.id,
        nome:       (p.title || p.name || '').slice(0, 50),
        vídeos:     p.video_count ?? '—',
        fase:       p._phase,
      })));
      return;
    }

    if (!data[productId]) {
      console.warn(`Produto "${productId}" não encontrado. Use shopee_set_videos() sem argumentos para ver os IDs.`);
      return;
    }

    data[productId].video_count      = parseInt(videoCount) || 0;
    data[productId].video_checked_at = new Date().toISOString();
    db.save(data);
    console.log(`✅ ${data[productId].title || data[productId].name} → ${videoCount} vídeo(s) registrado(s).`);
  };

  // ── Roteamento ───────────────────────────────────────────────

  if      (PAGE === 'affiliate-list')   scrapeAffiliateList();
  else if (PAGE === 'affiliate-detail') scrapeAffiliateDetail();
  else if (PAGE === 'product-page')     scrapeProductPage();
  else {
    console.warn('⚠️ Página não reconhecida. Acesse uma das páginas suportadas:');
    console.log('  1. affiliate.shopee.com.br/offer/product_offer');
    console.log('  2. Detalhes da oferta no portal do afiliado');
    console.log('  3. shopee.com.br/produto-i.xxx.yyy');
  }

})();
