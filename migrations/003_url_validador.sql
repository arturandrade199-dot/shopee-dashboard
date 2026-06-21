-- ══════════════════════════════════════════════════════════════
--  003 — Adiciona url_validador em vw_oportunidades
--
--  Rode no SQL Editor do Supabase.
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
  p.affiliate_url                                    AS url_validador,
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
