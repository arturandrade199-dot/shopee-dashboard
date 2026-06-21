"""
Dashboard de Oportunidades — Shopee Afiliados
Execução local:  streamlit run app.py
Deploy:          Streamlit Community Cloud → main file: app.py
"""

import os
import urllib.parse

import pandas as pd
import plotly.express as px
import streamlit as st

# ── Configuração ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Shopee Afiliados",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stMetricValue"] { font-size: 1.6rem; }
</style>
""", unsafe_allow_html=True)


# ── Conexão Supabase ──────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    try:
        url = st.secrets.get("SUPABASE_URL", "") or os.getenv("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_SERVICE_KEY", "")
    except Exception:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        return None

    from supabase import create_client
    return create_client(url, key)


def require_connection():
    sb = get_supabase()
    if not sb:
        st.error("⚠️ Supabase não configurado.")
        st.code("""
# .streamlit/secrets.toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_SERVICE_KEY = "eyJ..."
        """, language="toml")
        st.stop()
    return sb


# ── Queries ───────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_batches() -> list[str]:
    sb = get_supabase()
    res = sb.table("products").select("batch_date").execute()
    dates = sorted({r["batch_date"] for r in (res.data or [])}, reverse=True)
    return ["Todas"] + dates


@st.cache_data(ttl=300)
def load_oportunidades(sold_max: int, ratio_min: int, batch: str) -> pd.DataFrame:
    sb = get_supabase()
    q = (
        sb.table("vw_oportunidades")
        .select("*")
        .eq("is_extracted", False)
        .lte("vendas_alvo", sold_max)
        .gte("ratio_mercado_vs_alvo", ratio_min)
    )
    if batch != "Todas":
        q = q.eq("batch_date", batch)
    res = q.order("ratio_mercado_vs_alvo", desc=True).limit(300).execute()
    return pd.DataFrame(res.data or [])


@st.cache_data(ttl=300)
def load_top_produtos(min_commission: int, min_rating: float, batch: str) -> pd.DataFrame:
    sb = get_supabase()
    q = (
        sb.table("vw_top_products")
        .select("*")
        .eq("is_extracted", False)
        .gte("commission_rate", min_commission)
        .gte("rating", min_rating)
    )
    if batch != "Todas":
        q = q.eq("batch_date", batch)
    res = q.order("score", desc=True).limit(100).execute()
    return pd.DataFrame(res.data or [])


@st.cache_data(ttl=300)
def load_extraidos(batch: str) -> pd.DataFrame:
    sb = get_supabase()
    q = (
        sb.table("vw_top_products")
        .select("*")
        .eq("is_extracted", True)
    )
    if batch != "Todas":
        q = q.eq("batch_date", batch)
    res = q.order("extracted_at", desc=True).limit(500).execute()
    return pd.DataFrame(res.data or [])


def _br(v: float) -> str:
    """Formata float como moeda brasileira: 1.234,56"""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _short_url(url: str) -> str:
    """Remove query string da URL Shopee (mantém o caminho, elimina extraParams)."""
    return url.split("?")[0] if url else ""


def build_wa_multi_oportunidades(rows: pd.DataFrame) -> str:
    n = len(rows)
    lines = [f"🛍️ *OPORTUNIDADES SELECIONADAS ({n})*", ""]
    for i, (_, r) in enumerate(rows.iterrows(), 1):
        title    = str(r.get("produto_alvo", ""))[:65]
        price    = float(r.get("preco_alvo", 0) or 0)
        comm_pct = int(r.get("comissao_produto_validador_pct", 0) or 0)
        comm_val = float(r.get("comissao_video_estimada", 0) or 0)
        url      = _short_url(str(r.get("url_alvo", "") or ""))
        lines.append(f"*{i}.* {title}")
        if price:
            lines.append(f"💰 {_br(price)} | 💸 {comm_pct}% (~{_br(comm_val)})")
        if url:
            lines.append(f"🔗 {url}")
        if i < n:
            lines.append("─────────────────")
    return "https://wa.me/?text=" + urllib.parse.quote("\n".join(lines))


def build_wa_multi_produtos(rows: pd.DataFrame) -> str:
    n = len(rows)
    lines = [f"🛍️ *PRODUTOS SELECIONADOS ({n})*", ""]
    for i, (_, r) in enumerate(rows.iterrows(), 1):
        title    = str(r.get("title", ""))[:65]
        price    = float(r.get("price", 0) or 0)
        orig     = float(r.get("original_price", 0) or 0)
        comm_pct = int(r.get("total_commission_pct", 0) or 0)
        url      = _short_url(str(r.get("affiliate_url", "") or ""))
        lines.append(f"*{i}.* {title}")
        if orig and orig > price:
            lines.append(f"🔥 DE {_br(orig)} | POR {_br(price)}")
        elif price:
            lines.append(f"💰 {_br(price)}")
        if comm_pct:
            lines.append(f"💸 Comissão: {comm_pct}%")
        if url:
            lines.append(f"🔗 {url}")
        if i < n:
            lines.append("─────────────────")
    return "https://wa.me/?text=" + urllib.parse.quote("\n".join(lines))


def make_whatsapp_url_oportunidade(row: dict) -> str:
    title    = str(row.get("produto_alvo", ""))
    price    = float(row.get("preco_alvo", 0) or 0)
    rating   = float(row.get("rating_alvo", 0) or 0)
    vendas   = int(row.get("vendas_alvo", 0) or 0)
    comm_pct = int(row.get("comissao_produto_validador_pct", 0) or 0)
    comm_val = float(row.get("comissao_video_estimada", 0) or 0)
    loja     = str(row.get("loja", "") or "")
    url      = _short_url(str(row.get("url_alvo", "") or ""))

    lines = [f"🛍️ *{title}*", ""]
    if loja:
        lines.append(f"🏪 Loja: {loja}")
    if price:
        lines.append(f"💰 {_br(price)}")
    if rating:
        lines.append(f"⭐ {rating:.1f} | 📦 {vendas:,} vendas")
    if comm_pct:
        lines.append(f"💸 Comissão: {comm_pct}% (~{_br(comm_val)})")
    if url:
        lines += ["", f"🔗 {url}"]

    return "https://wa.me/?text=" + urllib.parse.quote("\n".join(lines))


def make_whatsapp_url(row: dict) -> str:
    title = str(row.get("title", ""))
    price = float(row.get("price", 0) or 0)
    orig  = float(row.get("original_price", 0) or 0)
    comm  = int(row.get("total_commission_pct", 0) or 0)
    url   = _short_url(str(row.get("affiliate_url", "") or row.get("product_url", "") or ""))

    lines = [f"🛍️ *{title}*", ""]
    if orig and orig > price:
        lines.append(f"🔥 DE {_br(orig)} | POR {_br(price)}")
    elif price:
        lines.append(f"💰 {_br(price)}")
    if comm:
        lines.append(f"💸 Comissão: {comm}%")
    if url:
        lines += ["", f"🔗 {url}"]

    return "https://wa.me/?text=" + urllib.parse.quote("\n".join(lines))


def mark_batch_extracted(batch_date: str) -> int:
    sb = get_supabase()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    res = (
        sb.table("products")
        .update({"is_extracted": True, "extracted_at": now})
        .eq("batch_date", batch_date)
        .eq("is_extracted", False)
        .execute()
    )
    return len(res.data or [])


# ── App ───────────────────────────────────────────────────────────────

require_connection()

st.title("🛍️ Shopee Afiliados · Dashboard")

with st.sidebar:
    st.header("Filtros globais")
    try:
        batches   = load_batches()
        batch_sel = st.selectbox("Coleta (batch)", batches)
    except Exception:
        batch_sel = "Todas"
        st.warning("Rode a migration no Supabase primeiro.")

    st.divider()

    st.subheader("Gestão de extrações")
    st.caption(
        "Marque um batch inteiro como já extraído para removê-lo "
        "das abas de novas oportunidades."
    )
    if batch_sel != "Todas":
        if st.button(f"✅ Marcar '{batch_sel}' como extraído", use_container_width=True):
            try:
                n = mark_batch_extracted(batch_sel)
                st.success(f"{n} produto(s) marcado(s) como extraído.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
    else:
        st.info("Selecione um batch específico para marcar como extraído.")

    st.divider()
    st.caption("Filtros extras em cada aba.")
    if st.button("🔄 Limpar cache"):
        st.cache_data.clear()
        st.rerun()


tab1, tab2, tab3 = st.tabs([
    "🎯 Oportunidades de Vídeo",
    "🏆 Top Produtos Afiliados",
    "📦 Já Extraídos",
])


# ════════════════════════════════════════════════════════════════════
#  TAB 1 — Oportunidades
# ════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown(
        "Produtos do **mesmo vendedor** com **poucas vendas**, descobertos via produtos "
        "afiliados já validados. Ideal para gravar vídeo e se tornar afiliado."
    )
    st.divider()

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        sold_max = st.slider(
            "Vendas máximas do produto alvo",
            min_value=10, max_value=2000, value=500, step=50,
            help="Menor = menos concorrência de afiliados.",
        )
    with col_f2:
        ratio_min = st.slider(
            "Ratio mínimo (mercado ÷ alvo)",
            min_value=5, max_value=1000, value=50, step=5,
            help="Maior = demanda mais comprovada pelo mercado.",
        )

    try:
        df = load_oportunidades(sold_max, ratio_min, batch_sel)
    except Exception as e:
        st.error(f"Erro: {e}")
        st.info("Verifique se a migration 002 foi aplicada no Supabase.")
        df = pd.DataFrame()

    if df.empty:
        st.info("Nenhuma oportunidade nova com esses filtros. Aumente o limite de vendas, reduza o ratio ou extraia um novo batch.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Oportunidades", f"{len(df)}")
        m2.metric("Menor vendas", f"{int(df['vendas_alvo'].min()):,}")
        m3.metric("Maior ratio", f"{int(df['ratio_mercado_vs_alvo'].max()):,}×")
        m4.metric("Mercado máximo", f"{int(df['maior_venda_mercado'].max()):,}")

        st.divider()

        # ── Scatter — mapa de oportunidades ───────────────────────
        st.subheader("Mapa de oportunidades")
        st.caption(
            "Ideal: **esquerda** (poucas vendas = pouca concorrência) + "
            "**alto** (mercado grande = demanda provada) + **cor quente** (ratio alto)."
        )

        fig = px.scatter(
            df,
            x="vendas_alvo",
            y="maior_venda_mercado",
            color="ratio_mercado_vs_alvo",
            size="rating_alvo",
            size_max=18,
            color_continuous_scale="RdYlGn",
            hover_name="produto_alvo",
            hover_data={
                "vendas_alvo":           ":,",
                "maior_venda_mercado":   ":,",
                "ratio_mercado_vs_alvo": ":,",
                "rating_alvo":           ":.1f",
                "loja":                  True,
                "preco_alvo":            ":.2f",
            },
            labels={
                "vendas_alvo":           "Vendas do produto alvo",
                "maior_venda_mercado":   "Maior vendedor do mercado",
                "ratio_mercado_vs_alvo": "Ratio",
                "rating_alvo":           "Rating",
            },
        )
        fig.update_layout(
            height=450,
            coloraxis_colorbar=dict(title="Ratio"),
            xaxis_title="Vendas do produto alvo (menor = melhor ←)",
            yaxis_title="Mercado provado (maior = melhor ↑)",
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Tabela ────────────────────────────────────────────────
        st.subheader(f"{len(df)} oportunidades")

        df["whatsapp_url"] = df.apply(make_whatsapp_url_oportunidade, axis=1)

        col_map = {
            "produto_alvo":                   "Produto Alvo",
            "url_alvo":                       "🔗 Link",
            "whatsapp_url":                   "📲 WhatsApp",
            "vendas_alvo":                    "Vendas",
            "rating_alvo":                    "Rating",
            "preco_alvo":                     "Preço (R$)",
            "comissao_produto_validador_pct": "Comissão %",
            "comissao_video_estimada":        "Comissão R$",
            "ratio_mercado_vs_alvo":          "Ratio ×",
            "maior_venda_mercado":            "Maior no Mercado",
            "concorrentes_na_categoria":      "Concorrentes",
            "produto_validador":              "Validador (sua loja)",
            "url_validador":                  "🔗 Link Validador",
            "loja":                           "Loja",
            "avaliacoes_loja":                "Avaliações Loja",
        }
        avail = [c for c in col_map if c in df.columns]
        table = df[avail].rename(columns=col_map)

        ev1 = st.dataframe(
            table,
            column_config={
                "🔗 Link":              st.column_config.LinkColumn("🔗 Link", display_text="Abrir →"),
                "📲 WhatsApp":          st.column_config.LinkColumn("📲 WhatsApp", display_text="Enviar"),
                "🔗 Link Validador":    st.column_config.LinkColumn("🔗 Link Validador", display_text="Abrir →"),
                "Ratio ×":          st.column_config.NumberColumn(format="%dx"),
                "Preço (R$)":       st.column_config.NumberColumn(format="R$ %.2f"),
                "Comissão %":       st.column_config.NumberColumn(format="%d%%"),
                "Comissão R$":      st.column_config.NumberColumn(format="R$ %.2f"),
                "Vendas":           st.column_config.NumberColumn(format="%d"),
                "Maior no Mercado": st.column_config.NumberColumn(format="%d"),
                "Concorrentes":     st.column_config.NumberColumn(format="%d"),
                "Rating":           st.column_config.NumberColumn(format="%.1f ⭐"),
            },
            use_container_width=True,
            hide_index=True,
            height=420,
            on_select="rerun",
            selection_mode="multi-row",
        )

        sel1 = ev1.selection.rows
        c_wa1, c_csv1 = st.columns([2, 1])
        with c_wa1:
            if sel1:
                wa_url = build_wa_multi_oportunidades(df.iloc[sel1])
                st.link_button(
                    f"📲 Enviar {len(sel1)} produto(s) para WhatsApp",
                    wa_url, use_container_width=True,
                )
            else:
                st.caption("Selecione linhas na tabela para enviar vários de uma vez.")
        with c_csv1:
            csv = table.drop(columns=["📲 WhatsApp"], errors="ignore").to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Exportar CSV", csv,
                               f"oportunidades_{batch_sel}.csv", "text/csv")


# ════════════════════════════════════════════════════════════════════
#  TAB 2 — Top Produtos Afiliados
# ════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown(
        "Produtos do **portal de afiliados** ordenados por score. "
        "Score = 40% comissão + 30% vendas + 20% rating − penalidade vídeos."
    )
    st.divider()

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        min_comm = st.slider("Comissão mínima (%)", 0, 30, 10)
    with col_f2:
        min_rat  = st.slider("Rating mínimo", 0.0, 5.0, 4.0, step=0.1)
    with col_f3:
        top_n    = st.slider("Top N no gráfico", 5, 50, 15)

    try:
        df2 = load_top_produtos(min_comm, min_rat, batch_sel)
    except Exception as e:
        st.error(f"Erro: {e}")
        df2 = pd.DataFrame()

    if df2.empty:
        st.info("Nenhum produto novo com esses filtros. Extraia um novo batch para ver novas oportunidades.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Produtos", len(df2))
        if "total_commission_pct" in df2.columns and df2["total_commission_pct"].notna().any():
            m2.metric("Comissão média", f"{df2['total_commission_pct'].mean():.1f}%")
        if "score" in df2.columns and df2["score"].notna().any():
            m3.metric("Melhor score", f"{df2['score'].max():.4f}")

        st.divider()

        if "score" in df2.columns and "title" in df2.columns:
            top_df       = df2.head(top_n).copy()
            top_df["label"] = top_df["title"].str[:50]
            color_col    = "total_commission_pct" if "total_commission_pct" in top_df.columns else "score"

            fig2 = px.bar(
                top_df,
                x="score",
                y="label",
                orientation="h",
                color=color_col,
                color_continuous_scale="Blues",
                labels={"score": "Score", "label": "", "total_commission_pct": "Comissão %"},
                title=f"Top {top_n} por score",
            )
            fig2.update_layout(
                height=max(320, top_n * 28),
                yaxis={"autorange": "reversed"},
                coloraxis_colorbar=dict(title="Comissão %"),
            )
            st.plotly_chart(fig2, use_container_width=True)

        df2["whatsapp_url"] = df2.apply(make_whatsapp_url, axis=1)

        col_map2 = {
            "title":               "Produto",
            "affiliate_url":       "🔗 Link",
            "whatsapp_url":        "📲 WhatsApp",
            "score":               "Score",
            "total_commission_pct":"Comissão %",
            "rating":              "Rating",
            "sold_num":            "Vendidos",
            "sold_raw":            "Vendidos (txt)",
            "price":               "Preço (R$)",
            "store_name":          "Loja",
            "badge":               "Badge",
            "video_count":         "Vídeos",
        }
        avail2  = [c for c in col_map2 if c in df2.columns]
        table2  = df2[avail2].rename(columns=col_map2)

        ev2 = st.dataframe(
            table2,
            column_config={
                "🔗 Link":       st.column_config.LinkColumn("🔗 Link", display_text="Abrir →"),
                "📲 WhatsApp":   st.column_config.LinkColumn("📲 WhatsApp", display_text="Enviar"),
                "Score":         st.column_config.NumberColumn(format="%.4f"),
                "Comissão %":    st.column_config.NumberColumn(format="%d%%"),
                "Preço (R$)":    st.column_config.NumberColumn(format="R$ %.2f"),
                "Rating":        st.column_config.NumberColumn(format="%.1f ⭐"),
                "Vendidos":      st.column_config.NumberColumn(format="%d"),
                "Vídeos":        st.column_config.NumberColumn(format="%d 🎥"),
            },
            use_container_width=True,
            hide_index=True,
            height=460,
            on_select="rerun",
            selection_mode="multi-row",
        )

        sel2 = ev2.selection.rows
        c_wa2, c_csv2 = st.columns([2, 1])
        with c_wa2:
            if sel2:
                wa_url2 = build_wa_multi_produtos(df2.iloc[sel2])
                st.link_button(
                    f"📲 Enviar {len(sel2)} produto(s) para WhatsApp",
                    wa_url2, use_container_width=True,
                )
            else:
                st.caption("Selecione linhas na tabela para enviar vários de uma vez.")
        with c_csv2:
            csv2 = table2.drop(columns=["📲 WhatsApp"], errors="ignore").to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Exportar CSV", csv2,
                               f"top_produtos_{batch_sel}.csv", "text/csv")


# ════════════════════════════════════════════════════════════════════
#  TAB 3 — Já Extraídos (histórico)
# ════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown(
        "Produtos do portal de afiliados que **já foram utilizados**. "
        "Use o sidebar para marcar um batch inteiro como extraído."
    )
    st.divider()

    try:
        df3 = load_extraidos(batch_sel)
    except Exception as e:
        st.error(f"Erro: {e}")
        st.info("Verifique se a migration 002 foi aplicada no Supabase.")
        df3 = pd.DataFrame()

    if df3.empty:
        st.info("Nenhum produto marcado como extraído ainda.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total extraídos", len(df3))
        if "total_commission_pct" in df3.columns and df3["total_commission_pct"].notna().any():
            m2.metric("Comissão média", f"{df3['total_commission_pct'].mean():.1f}%")
        if "extracted_at" in df3.columns and df3["extracted_at"].notna().any():
            ultimo = pd.to_datetime(df3["extracted_at"]).max()
            m3.metric("Último extraído em", ultimo.strftime("%d/%m/%Y"))

        st.divider()

        df3["whatsapp_url"] = df3.apply(make_whatsapp_url, axis=1)

        col_map3 = {
            "title":               "Produto",
            "affiliate_url":       "🔗 Link",
            "whatsapp_url":        "📲 WhatsApp",
            "score":               "Score",
            "total_commission_pct":"Comissão %",
            "rating":              "Rating",
            "sold_num":            "Vendidos",
            "price":               "Preço (R$)",
            "store_name":          "Loja",
            "badge":               "Badge",
            "video_count":         "Vídeos",
            "batch_date":          "Batch",
            "extracted_at":        "Extraído em",
        }
        avail3  = [c for c in col_map3 if c in df3.columns]
        table3  = df3[avail3].rename(columns=col_map3)

        if "Extraído em" in table3.columns:
            table3["Extraído em"] = pd.to_datetime(table3["Extraído em"]).dt.strftime("%d/%m/%Y %H:%M")

        ev3 = st.dataframe(
            table3,
            column_config={
                "🔗 Link":       st.column_config.LinkColumn("🔗 Link", display_text="Abrir →"),
                "📲 WhatsApp":   st.column_config.LinkColumn("📲 WhatsApp", display_text="Enviar"),
                "Score":         st.column_config.NumberColumn(format="%.4f"),
                "Comissão %":    st.column_config.NumberColumn(format="%d%%"),
                "Preço (R$)":    st.column_config.NumberColumn(format="R$ %.2f"),
                "Rating":        st.column_config.NumberColumn(format="%.1f ⭐"),
                "Vendidos":      st.column_config.NumberColumn(format="%d"),
                "Vídeos":        st.column_config.NumberColumn(format="%d 🎥"),
            },
            use_container_width=True,
            hide_index=True,
            height=460,
            on_select="rerun",
            selection_mode="multi-row",
        )

        sel3 = ev3.selection.rows
        c_wa3, c_csv3 = st.columns([2, 1])
        with c_wa3:
            if sel3:
                wa_url3 = build_wa_multi_produtos(df3.iloc[sel3])
                st.link_button(
                    f"📲 Enviar {len(sel3)} produto(s) para WhatsApp",
                    wa_url3, use_container_width=True,
                )
            else:
                st.caption("Selecione linhas na tabela para enviar vários de uma vez.")
        with c_csv3:
            csv3 = table3.drop(columns=["📲 WhatsApp"], errors="ignore").to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Exportar CSV", csv3,
                               f"extraidos_{batch_sel}.csv", "text/csv")
