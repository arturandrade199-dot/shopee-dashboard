from .models import Product


def _brl(value: float) -> str:
    """Formata número como moeda brasileira: R$ 1.299,90"""
    s = f"{value:,.2f}"                          # "1,299.90" (US format)
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")  # "1.299,90"
    return f"R$ {s}"


def format_whatsapp_message(product: Product) -> str:
    lines = [
        "PERDE NÃOOOO 😱🏃",
        "",
        f"🛍 *{product.name}*",
        "",
        f"De ~~{_brl(product.original_price)}~~",
        f"💸 Por *{_brl(product.price)}*",
        f"😱 *{product.discount_pct}% OFF*",
    ]

    if product.coupon_code and product.coupon_discount:
        lines.append(
            f"🎟 + Cupom {product.coupon_code} → {_brl(product.final_price)} final"
        )

    if product.rating >= 4.5 and product.sold >= 100:
        lines.append(f"⭐ {product.rating:.1f} ({product.sold:,} vendidos)".replace(",", "."))

    lines += [
        "",
        "⚠️ Pagamento no Pix tem + desconto",
        "",
        f"🛒 Compre aqui: {product.affiliate_url or product.product_url}",
        "",
        "⚠️ Promoção sujeita a alteração a qualquer momento.",
    ]

    return "\n".join(lines)
