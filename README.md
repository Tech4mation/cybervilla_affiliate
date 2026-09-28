# CyberVilla Affiliate (`cybervilla_affiliate`)

An Odoo **16.0** module that lets the CyberVilla affiliate dashboard sell
through the CyberVilla webshop: it attributes a sale to an affiliate, prices
the cart at that affiliate's markup (with a hard ceiling), and tells the
dashboard when an attributed order is paid or cancelled.

---

## The model in one paragraph

An affiliate shares `https://cybervilla.io/r/<code>`. The code carries no price
and no product — the module looks those up from the code, so there is nothing
in the address a buyer can edit (this is the bug the old dashboard links had).
Clicking `/r/<code>` records the visit, puts the visitor's cart on a pricelist
that adds the affiliate's markup to every product, and sends them into the shop.
The markup **travels with the link**, so it applies to whatever they buy, not
only the product that was shared. Payment is taken by the shop's existing
Paystack provider — this module does **not** handle money. When the order
confirms (i.e. Paystack reported the money in), the dashboard is notified, once,
reliably. If the order is later cancelled, the dashboard is notified again so it
can reverse the earning.

**The affiliate's earning** is the markup portion of the untaxed total:
`amount_untaxed × markup / (100 + markup)`. CyberVilla keeps the rest, exactly
as if the markup had never been added.

## How pricing works (and why this way)

Each affiliate link owns exactly one **pricelist** with a single global rule:
a `formula` rule with `price_discount = -markup` (a negative discount is Odoo's
way of *adding* to a price). Once the cart is on that pricelist, Odoo's own
website, cart, tax and order code do all the pricing — there is no custom price
arithmetic to fight `website_sale`. The module never trusts a number from
outside: the markup is validated (`@api.constrains`) and clamped to the ceiling
when a link is created or updated.

**The ceiling is 10%** by default (Settings → Affiliates, or the config
parameter `cybervilla_affiliate.max_markup_percent`). Links above it are
refused; incoming markups are clamped to it.

## What it does NOT do

- **Take payment.** The website already does, via the live Paystack provider.
- **Touch Point of Sale.** Affiliate links drive online traffic; in-store POS
  attribution (a code typed at the till) is a separate, later piece.
- **Create invoices or journal entries.** Deliberately — the integration user
  has no accounting rights and this module needs none.

---

## Install

1. Copy `cybervilla_affiliate/` into the addons path and restart Odoo.
2. Enable **Advanced price rules** — Settings → Sales → Pricing →
   *"Discounts, Loyalty & Gift Card"* / pricelist advanced rules. **Required:**
   formula pricelists only apply on the website when this is on. Verify a
   formula rule actually changes the shown price before going further.
3. Install the module (Apps → *CyberVilla Affiliate*).
4. Settings → **Affiliates**: set the backend URL, the signing secret, and
   confirm the markup ceiling.

## Configuration

| Setting | Config parameter | Meaning |
|---|---|---|
| Backend URL | `cybervilla_affiliate.backend_url` | Where paid/cancelled notifications are POSTed. |
| Signing secret | `cybervilla_affiliate.webhook_secret` | Shared with the backend; signs every notification (HMAC-SHA256). |
| Markup ceiling | `cybervilla_affiliate.max_markup_percent` | Most any link may add. Default 10. |

---

## The contract with the affiliate backend

The dashboard is the system of record. It pushes affiliates and links **into**
Odoo over XML-RPC (using the existing integration user, `<your Odoo integration user>`,
which has Sales rights), and Odoo pushes paid/cancelled events **back**.

### 1. Backend → Odoo: register an affiliate, then a link

```python
import xmlrpc.client
URL, DB, USER, KEY = "https://www.cybervilla.io", "cybervilla", "<your Odoo integration user>", "<api key>"
uid = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common").authenticate(DB, USER, KEY, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# Upsert the affiliate (keyed on the dashboard's own id)
aff_id = models.execute_kw(DB, uid, KEY, "cybervilla.affiliate", "upsert_from_backend", [{
    "backend_ref": "AFF-10492",
    "name": "Tomiwa Adebayo",
    "email": "tomiwa@example.com",
}])

# Upsert a link. markup_percent is clamped to the ceiling server-side.
result = models.execute_kw(DB, uid, KEY, "cybervilla.affiliate.link", "upsert_from_backend", [{
    "backend_ref": "LNK-001",
    "code": "TOMIWA-IP15",
    "label": "iPhone 15 Pro Max — Instagram bio",
    "affiliate_id": aff_id,
    "markup_percent": 0.5,
}])
# result -> {"link_id":..,"affiliate_id":..,"pricelist_id":..,"markup_percent":0.5}
```

Both `upsert_from_backend` methods are idempotent (keyed on `backend_ref`), so
the backend can re-send safely.

### 2. Odoo → backend: paid / cancelled notifications

POSTed to the backend URL. Headers:

- `X-Cybervilla-Event`: `order.paid` or `order.cancelled`
- `X-Cybervilla-Signature`: `hmac_sha256(secret, raw_body).hexdigest()`

Verify the signature exactly as the existing Paystack webhook does. Body:

```json
{
  "event": "order.paid",
  "order_ref": "S00123",
  "order_id": 123,
  "affiliate_code": "TOMIWA-IP15",
  "affiliate_backend_ref": "AFF-10492",
  "link_backend_ref": "LNK-001",
  "markup_percent": 0.5,
  "currency": "NGN",
  "amount_total": 1859250.0,
  "amount_untaxed": 1859250.0,
  "affiliate_earning": 9250.0,
  "customer_email": "buyer@example.com",
  "confirmed_at": "2026-09-23 14:40:00"
}
```

Delivery is queued in `cybervilla.affiliate.webhook` inside the order's own
transaction, then sent by a cron every 3 minutes with retry and back-off (up to
8 attempts). A failed dashboard never blocks a sale. The backend endpoint
**must be idempotent** on `order_ref` + `event`, because a delivery may be
retried after a timeout that actually succeeded.

---

## Verify on staging (in priority order)

1. **Pricelist applies and sticks.** With advanced rules on, click `/r/<code>`,
   add to cart, and confirm the price is `base × (1 + markup%)`. Then log in,
   change quantities, and re-check — the affiliate pricelist must survive cart
   updates and login. If Odoo resets `pricelist_id` from the partner, the fix is
   in `sale.order._apply_affiliate_link` / `website.sale_get_order`; this is the
   most version-sensitive part.
2. **`ir_http._dispatch` signature.** `models/ir_http.py` captures `?ref=` on any
   page. Confirm the `_dispatch(cls, endpoint)` signature matches this exact
   16.0 point release — a wrong signature there affects every request. If you
   only want `/r/<code>` capture, you can delete `models/ir_http.py` and its
   import; `/r/<code>` does not depend on it.
3. **Vendor-owned products.** This store distinguishes vendor vs own stock
   (`cybervilla_product_ownership`). Decide whose margin an affiliate's markup
   comes from before letting affiliates mark up vendor products. The module adds
   the markup **on top** of the shown price (the buyer pays it), so it does not
   touch CyberVilla's or the vendor's margin — but confirm that is the intended
   commercial rule.
4. **Earning vs tax.** Earning is computed on `amount_untaxed`. Confirm that
   matches how you want to pay affiliates if the store prices tax-inclusive.
5. **Refunds.** Cancellation is covered. If you also refund via credit note
   without cancelling the sale order, add that signal (out of scope here).

## Security / the integration user

`<your Odoo integration user>` (Sales Administrator) can call both `upsert_from_backend`
methods via the Sales access granted in `security/ir.model.access.csv`. The
public `/r/<code>` controller runs `sudo()` for the lookup and click, so buyers
need no rights. The **Affiliate Manager** group gates the back-office menus.

## Files

```
cybervilla_affiliate/
├── __manifest__.py
├── controllers/main.py            # /r/<code> — click, price, redirect
├── models/
│   ├── affiliate.py               # cybervilla.affiliate (+ upsert)
│   ├── affiliate_link.py          # link + its pricelist (+ upsert, cap)
│   ├── affiliate_click.py         # thin click record
│   ├── affiliate_webhook.py       # signed, queued, retried delivery
│   ├── sale_order.py              # attribution, earning, paid/cancel hooks
│   ├── ir_http.py                 # ?ref= capture (see staging note 2)
│   ├── website.py                 # attach link to the cart
│   └── res_config_settings.py     # the three settings
├── data/                          # cron + default ceiling
├── security/                      # manager group + access rules
└── views/                         # back-office views, settings, menus
```
