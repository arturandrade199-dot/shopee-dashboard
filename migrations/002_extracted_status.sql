-- ══════════════════════════════════════════════════════════════
--  002 — Status de extração por produto
--
--  Rode no SQL Editor do Supabase:
--    1. Cole e execute este arquivo inteiro de uma vez.
--
--  O que faz:
--    1. Adiciona is_extracted + extracted_at em products.
--    2. Marca TODOS os produtos atuais como já extraídos
--       (o usuário já trabalhou com eles).
--    3. Recria vw_top_products e vw_oportunidades expondo
--       is_extracted para filtro no dashboard.
-- ══════════════════════════════════════════════════════════════

-- ── 1. Novas colunas ─────────────────────────────────────────
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS is_extracted  BOOLEAN    DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS extracted_at  TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_products_extracted ON products (is_extracted);

-- ── 2. Marca todos os registros atuais como extraídos ────────
UPDATE products
SET
  is_extracted = TRUE,
  extracted_at = NOW()
WHERE is_extracted = FALSE;

-- ══════════════════════════════════════════════════════════════
--  3. Recria vw_top_products expondo is_extracted
--     DROP necessário: CREATE OR REPLACE não permite inserir
--     colunas no meio da lista existente (erro 42P16).
-- ══════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS vw_top_products CASCADE;
CREATE VIEW vw_top_products AS
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
  p.is_extracted,
  p.extracted_at,
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


-- ══════════════════════════════════════════════════════════════
--  4. Recria vw_oportunidades expondo is_extracted do validador
-- ══════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS vw_oportunidades CASCADE;
CREATE VIEW vw_oportunidades AS
WITH prova_mercado AS (
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
  p.is_extracted,
  p.extracted_at,

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
  AND alvo.rating        >= 4.0
  AND alvo.sold_num      IS NOT NULL
  AND alvo.sold_num       < 2000
  AND p.sold_num         >= 5000
  AND COALESCE(m.maior_venda_mercado, 0) >= 5000

ORDER BY
  ratio_mercado_vs_alvo DESC NULLS LAST,
  alvo.sold_num ASC;
