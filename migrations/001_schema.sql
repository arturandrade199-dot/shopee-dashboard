-- ══════════════════════════════════════════════════════════════
--  marketing-afiliados — schema inicial Supabase / PostgreSQL
--  Rode no SQL Editor do Supabase: https://supabase.com/dashboard
-- ══════════════════════════════════════════════════════════════

-- ── Lojas ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stores (
  id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  shop_id           TEXT UNIQUE NOT NULL,
  name              TEXT,
  years_on_shopee   TEXT,
  response_rate     TEXT,
  response_time     TEXT,
  followers         TEXT,
  total_reviews     TEXT,
  total_products    INTEGER,
  last_scraped_at   TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ── Produtos ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
  id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  platform_id             TEXT NOT NULL,
  shop_id                 TEXT REFERENCES stores(shop_id),
  source                  TEXT NOT NULL,  -- 'shopee_affiliate' | 'shopee_search'

  -- Identidade
  slug                    TEXT,
  title                   TEXT,
  product_url             TEXT,
  affiliate_url           TEXT,
  image_url               TEXT,

  -- Preços
  price                   NUMERIC(10,2),
  price_coupon            NUMERIC(10,2),
  original_price          NUMERIC(10,2),

  -- Desempenho
  rating                  NUMERIC(3,1),
  reviews_num             INTEGER,
  sold_num                INTEGER,
  sold_raw                TEXT,

  -- Desconto / comissão
  discount_pct            INTEGER,          -- scraper de busca
  commission_rate         INTEGER,          -- portal afiliado
  commission_extra_pct    INTEGER,
  commission_extra_value  NUMERIC(10,2),

  -- Flags
  badge                   TEXT,
  has_flash_sale          BOOLEAN DEFAULT FALSE,
  shipping                TEXT,
  video_count             INTEGER,          -- manual via app Android

  -- JSONB (campos compostos)
  variants                JSONB,
  coupon_badges           JSONB,
  product_details         JSONB,

  -- Score calculado pelo ETL
  score                   NUMERIC(6,4),

  -- Auditoria
  batch_date              DATE NOT NULL,
  scraped_at              TIMESTAMPTZ,
  created_at              TIMESTAMPTZ DEFAULT NOW(),
  updated_at              TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE (platform_id, batch_date, source)
);

-- ── Canais de comissão (por produto, fase 2) ─────────────────
CREATE TABLE IF NOT EXISTS product_channels (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  product_id   UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  channel      TEXT NOT NULL,          -- Shopee Vídeo | Redes sociais | Shopee Lives
  shopee_pct   INTEGER,
  shopee_value NUMERIC(10,2),
  estimated    NUMERIC(10,2)
);

-- ── Cupons de loja encontrados na página do produto ───────────
CREATE TABLE IF NOT EXISTS store_coupons (
  id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  product_id  UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  discount    TEXT,
  conditions  TEXT,
  valid_until TEXT
);

-- ── Produtos relacionados (mesmo vendedor / indicados / loja) ─
CREATE TABLE IF NOT EXISTS related_products (
  id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  source_product_id   UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  relation_type       TEXT NOT NULL,  -- 'same_seller' | 'recommended' | 'main_store_choice'
  platform_id         TEXT,
  title               TEXT,
  price               NUMERIC(10,2),
  rating              NUMERIC(3,1),
  sold_num            INTEGER,
  sold_raw            TEXT,
  discount            INTEGER,
  product_url         TEXT
);

-- ── Bronze: JSONs brutos ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_scrapes (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  source       TEXT NOT NULL,
  batch_date   DATE NOT NULL,
  filename     TEXT,
  raw_data     JSONB,
  ingested_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (source, batch_date, filename)
);

-- ── Índices ───────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_products_batch      ON products (batch_date);
CREATE INDEX IF NOT EXISTS idx_products_shop       ON products (shop_id);
CREATE INDEX IF NOT EXISTS idx_products_score      ON products (score DESC);
CREATE INDEX IF NOT EXISTS idx_products_commission ON products (commission_rate DESC);
CREATE INDEX IF NOT EXISTS idx_related_source      ON related_products (source_product_id);
CREATE INDEX IF NOT EXISTS idx_channels_product    ON product_channels (product_id);

-- ── Trigger: updated_at automático ───────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

CREATE OR REPLACE TRIGGER trg_products_updated
  BEFORE UPDATE ON products
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ══════════════════════════════════════════════════════════════
--  VIEWS — camada Gold
-- ══════════════════════════════════════════════════════════════

-- Top produtos para análise de oportunidade de afiliado
CREATE OR REPLACE VIEW vw_top_products AS
SELECT
  p.id,
  p.platform_id,
  p.shop_id,
  p.slug,
  p.title,
  p.price_coupon                                          AS price,
  p.original_price,
  p.rating,
  p.sold_num,
  p.sold_raw,
  p.commission_rate,
  p.commission_extra_pct,
  (COALESCE(p.commission_rate, 0) +
   COALESCE(p.commission_extra_pct, 0))                  AS total_commission_pct,
  p.video_count,
  p.badge,
  p.has_flash_sale,
  p.score,
  p.product_url,
  p.affiliate_url,
  p.batch_date,
  p.scraped_at,
  s.name                                                  AS store_name,
  s.followers                                             AS store_followers,
  s.total_reviews                                         AS store_total_reviews,
  s.years_on_shopee
FROM products p
LEFT JOIN stores s ON p.shop_id = s.shop_id
WHERE p.source = 'shopee_affiliate'
  AND p.price_coupon  >= 5
  AND p.commission_rate >= 5
  AND (p.rating = 0 OR p.rating >= 3.5)
ORDER BY p.score DESC NULLS LAST;

-- Produtos sem (ou com poucos) vídeos = oportunidade de entrada
CREATE OR REPLACE VIEW vw_video_opportunities AS
SELECT
  p.id,
  p.title,
  p.price_coupon                                          AS price,
  p.rating,
  p.sold_num,
  COALESCE(p.commission_rate, 0) +
  COALESCE(p.commission_extra_pct, 0)                     AS total_commission_pct,
  COALESCE(p.video_count, 0)                              AS video_count,
  p.score,
  p.product_url,
  p.affiliate_url,
  p.batch_date
FROM products p
WHERE p.source         = 'shopee_affiliate'
  AND p.commission_rate >= 5
  AND p.sold_num        >= 500
  AND p.rating          >= 4.0
  AND COALESCE(p.video_count, 0) <= 3
ORDER BY p.score DESC NULLS LAST;

-- ══════════════════════════════════════════════════════════════
--  VIEW GOLD — Oportunidades de vídeo de afiliado
--
--  Estratégia:
--    1. Produto principal (da lista de afiliados) valida que o
--       VENDEDOR é confiável e a CATEGORIA vende bem.
--    2. same_seller_products com vendas baixas = produto ainda
--       pouco explorado por afiliados → oportunidade de gravar
--       um vídeo e capturar a demanda que já existe no mercado.
--    3. recommended_products prova que o mercado da categoria
--       é grande (outras lojas já vendem muito).
--
--  Saída: uma linha por PRODUTO ALVO (same_seller com baixas vendas)
--  Filtros ajustáveis:
--    - alvo.sold_num < 2000   → produto sub-explorado
--    - alvo.rating   >= 4.0   → produto de qualidade
--    - mercado max   >= 5000  → categoria validada pelo mercado
-- ══════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW vw_oportunidades AS
WITH prova_mercado AS (
  -- Maior volume de vendas dos concorrentes recomendados pela Shopee.
  -- Prova que a categoria tem demanda real.
  SELECT
    source_product_id,
    MAX(sold_num)   AS maior_venda_mercado,
    COUNT(*)        AS total_concorrentes
  FROM related_products
  WHERE relation_type = 'recommended'
    AND sold_num      IS NOT NULL
  GROUP BY source_product_id
)
SELECT
  -- ── Produto alvo (oportunidade) ──────────────────────────
  alvo.title                                         AS produto_alvo,
  alvo.price                                         AS preco_alvo,
  alvo.rating                                        AS rating_alvo,
  alvo.sold_num                                      AS vendas_alvo,
  alvo.sold_raw                                      AS vendas_alvo_raw,
  alvo.product_url                                   AS url_alvo,

  -- ── Produto validador (seu afiliado, mesma loja) ─────────
  p.title                                            AS produto_validador,
  p.sold_num                                         AS vendas_validador,
  p.sold_raw                                         AS vendas_validador_raw,
  p.commission_rate                                  AS comissao_produto_validador_pct,
  COALESCE(
    pc_video.estimated,
    ROUND(COALESCE(p.price_coupon, p.original_price) * p.commission_rate / 100.0, 2)
  )                                                  AS comissao_video_estimada,

  -- ── Prova de mercado (maior concorrente recomendado) ─────
  COALESCE(m.maior_venda_mercado, p.sold_num)        AS maior_venda_mercado,
  COALESCE(m.total_concorrentes, 0)                  AS concorrentes_na_categoria,

  -- ── Ratio: quanto o mercado está acima do produto alvo ───
  ROUND(
    COALESCE(m.maior_venda_mercado, p.sold_num)::numeric
    / NULLIF(alvo.sold_num, 0)
  , 0)                                               AS ratio_mercado_vs_alvo,

  -- ── Loja (qualidade do vendedor) ─────────────────────────
  s.name                                             AS loja,
  s.shop_id,
  s.total_reviews                                    AS avaliacoes_loja,
  s.followers                                        AS seguidores_loja,

  p.batch_date

FROM related_products alvo
JOIN products p    ON alvo.source_product_id = p.id
LEFT JOIN stores s ON p.shop_id              = s.shop_id
LEFT JOIN prova_mercado m ON m.source_product_id = p.id
LEFT JOIN LATERAL (
  SELECT estimated
  FROM product_channels
  WHERE product_id = p.id
    AND channel ILIKE '%deo%'
  LIMIT 1
) pc_video ON true

WHERE alvo.relation_type  = 'same_seller'
  AND alvo.rating        >= 4.0             -- produto de qualidade
  AND alvo.sold_num      IS NOT NULL
  AND alvo.sold_num       < 2000            -- pouco explorado por afiliados
  AND p.sold_num         >= 5000            -- vendedor validado pelo produto principal
  AND COALESCE(m.maior_venda_mercado, 0) >= 5000   -- mercado comprovado

ORDER BY
  ratio_mercado_vs_alvo DESC NULLS LAST,    -- maior gap primeiro
  alvo.sold_num ASC;                        -- menor concorrência primeiro

-- Fornecedores alternativos: mesmo produto em outras lojas
CREATE OR REPLACE VIEW vw_alternative_sellers AS
SELECT
  r.title,
  r.platform_id,
  r.price,
  r.rating,
  r.sold_num,
  r.sold_raw,
  r.product_url,
  p.title                                                 AS original_product,
  p.commission_rate                                       AS original_commission,
  p.batch_date
FROM related_products r
JOIN products p ON r.source_product_id = p.id
WHERE r.relation_type = 'same_seller'
  AND r.sold_num IS NOT NULL
ORDER BY r.sold_num DESC;
