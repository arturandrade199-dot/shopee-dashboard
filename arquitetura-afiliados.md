# 🛒 Arquitetura — Bot de Ofertas com Afiliados

> Negócio de divulgação de ofertas via grupos de WhatsApp com monetização por links de afiliado (Shopee, Mercado Livre, Amazon).

---

## 📌 Visão Geral do Negócio

```
Anúncio Pago (Meta Ads)
        ↓
Landing Page (captura UTMs + dados)
        ↓
Usuário entra no Grupo do WhatsApp
        ↓
Bot envia ofertas com link de afiliado
        ↓
Usuário compra → você ganha comissão
```

---

## 🗺️ Fases do Projeto

### Fase 1 — MVP (Agora)
- Scraper coleta ofertas das plataformas
- Painel simples exibe os melhores produtos
- Você posta **manualmente** nos grupos existentes
- Valida o que converte antes de automatizar

### Fase 2 — Semi-automático
- Bot monta e envia mensagens automaticamente
- Landing page com redirecionamento dinâmico para grupos
- Métricas básicas de conversão

### Fase 3 — Escala
- Múltiplos grupos gerenciados automaticamente
- IA filtra os melhores produtos para anunciar
- Tráfego pago otimizado por CPL

---

## 🔧 Componentes da Arquitetura

### 1. Camada de Coleta (Scraping)

| Plataforma | Método | Dificuldade |
|---|---|---|
| Mercado Livre | API REST gratuita | ⭐ Fácil |
| Shopee | Endpoint interno | ⭐⭐ Médio |
| Amazon | Scraping HTML | ⭐⭐ Médio |
| Cuponomia | Scraping HTML | ⭐⭐ Médio |
| Pelando | Scraping HTML | ⭐ Fácil |
| Promobit | Scraping HTML | ⭐ Fácil |

**Endpoints principais:**
```
ML:      https://api.mercadolibre.com/sites/MLB/search?discount=20
Shopee:  https://shopee.com.br/api/v4/flash_sale/get_all_sessions
Cupons:  https://www.cuponomia.com.br/{loja}
```

### 2. Filtro de Qualidade

Critérios para um produto ser anunciado:
- ✅ Desconto mínimo: **25% OFF**
- ✅ Preço entre: **R$ 30 e R$ 500**
- ✅ Produto com imagem disponível
- ✅ Não anunciado nas últimas 24h
- ✅ Cupom disponível (bônus — aumenta conversão)

### 3. Geração do Link de Afiliado

```
Link original do produto
        ↓
Substituído por link com seu ID de afiliado
        ↓
s.shopee.com.br/... ou amzn.to/... ou mercadolivre.com/...?afiliado=SEU_ID
```

**Plataformas de afiliado:**
- Shopee: `affiliate.shopee.com.br`
- Amazon: `afiliados.amazon.com.br`
- Mercado Livre: `afiliados.mercadolivre.com.br`

### 4. Template de Mensagem

```
PERDE NÃOOOO 😱🏃

🛍 *Nome do Produto*

De ~~R$ 398,00~~
💸 Por *R$ 298,00*
😱 *25% OFF*
🎟 + Cupom SHOP15 → R$ 253,30 final

⚠️ Pagamento no Pix tem + desconto

🛒 Compre aqui: [link afiliado]

⚠️ Promoção sujeita a alteração a qualquer momento.
```

### 5. Gestão de Grupos WhatsApp

**Banco de dados de grupos:**
```sql
grupos (
  id, nome, link_convite, whatsapp_jid,
  membros, limite (1000), ativo, criado_em
)
```

**Lógica de rotação:**
- Grupo atinge 95% da capacidade → cria próximo grupo
- Landing page sempre consulta banco para redirecionar
- Bot dispara mensagem para **todos os grupos ativos**

**Delay entre envios:** 3–8 segundos (evitar ban)

### 6. Landing Page

**O que capturar:**
- UTM Source / Medium / Campaign / Content
- Cidade e estado (via IP)
- Dispositivo (mobile/desktop)
- Horário de acesso
- Grupo que o usuário entrou

**Métricas calculadas:**
```
Taxa de conversão = Cliques no botão / Visitantes × 100
CPL = Gasto no Meta Ads / Leads gerados
```

**Integrações recomendadas:**
- Meta Pixel (conversões dos anúncios)
- Google Analytics 4 (comportamento)
- Google Tag Manager (gerenciar eventos)

---

## 🏗️ Stack Tecnológica

| Componente | Tecnologia | Custo |
|---|---|---|
| Scraping | Python + Requests + BeautifulSoup | Grátis |
| Agendamento | APScheduler (a cada 2h) | Grátis |
| Banco de dados | SQLite → PostgreSQL (na escala) | Grátis |
| Backend/API | Python + Flask | Grátis |
| Painel MVP | React (HTML simples no início) | Grátis |
| Landing Page | HTML + Carrd | R$ 0–30/mês |
| Bot WhatsApp | Evolution API (self-hosted) | Grátis |
| Hospedagem | VPS Hostinger | ~R$ 25/mês |
| Chip WhatsApp | SIM card físico (Vivo/Claro) | ~R$ 20 único |
| Tráfego pago | Meta Ads | Variável |

**Custo fixo de infraestrutura: ~R$ 25/mês**

---

## 📊 Funil Completo

```
[Meta Ads] → Impressões
      ↓
[Landing Page] → Visitantes
      ↓
[Clique no botão] → Leads
      ↓
[Entrada no grupo] → Membros
      ↓
[Clique na oferta] → Potenciais compradores
      ↓
[Compra realizada] → Comissão (2–10%)
```

---

## 🚀 Ordem de Construção

### Semana 1 — Scraper MVP
- [ ] Scraping do Mercado Livre (API gratuita)
- [ ] Scraping da Shopee (endpoint interno)
- [ ] Filtro de qualidade dos produtos
- [ ] Geração do link de afiliado

### Semana 2 — Painel MVP
- [ ] Painel React simples com lista de ofertas
- [ ] Botão "Copiar Mensagem" formatada pro WhatsApp
- [ ] Scraping de cupons (Cuponomia + Pelando)
- [ ] Cruzamento produto + cupom disponível

### Semana 3 — WhatsApp
- [ ] Instalar Evolution API na VPS
- [ ] Configurar chip + login via QR Code
- [ ] Bot enviando mensagem para grupos manualmente via painel

### Semana 4 — Landing Page
- [ ] Página de conversão com botão de entrada no grupo
- [ ] Meta Pixel + Google Analytics 4
- [ ] Captura de UTMs
- [ ] Redirecionamento dinâmico por grupo

### Após validação — Automação
- [ ] Agendamento automático do scraper (APScheduler)
- [ ] Bot disparando para todos os grupos automaticamente
- [ ] Rotação automática de grupos ao atingir limite
- [ ] Painel de métricas (CPL, conversão, grupos, comissões)

---

## ⚠️ Riscos e Mitigações

| Risco | Mitigação |
|---|---|
| Ban do WhatsApp | Delay entre mensagens, chip com histórico, limite de grupos por hora |
| Scraping bloqueado | Rotação de User-Agent, delay aleatório, usar API oficial quando disponível |
| Promoção expirada | Checar validade antes de enviar, marcar timestamp da coleta |
| Grupo cheio sem substituto | Pré-criar grupos com antecedência e cadastrar no banco |

---

## 💰 Projeção de Receita (estimativa)

| Grupos | Membros | Ofertas/dia | CTR | Vendas/dia | Ticket médio | Comissão | Receita/mês |
|---|---|---|---|---|---|---|---|
| 2 | 2.000 | 4 | 3% | 2,4 | R$ 150 | 5% | ~R$ 540 |
| 5 | 5.000 | 4 | 3% | 6 | R$ 150 | 5% | ~R$ 1.350 |
| 20 | 20.000 | 4 | 3% | 24 | R$ 150 | 5% | ~R$ 5.400 |

> Valores estimados. Variam conforme nicho, qualidade dos produtos e engajamento do grupo.

---

*Documento gerado em Junho/2026 — atualizar conforme o projeto evolui.*
