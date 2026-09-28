{
    "name": "CyberVilla Affiliate",
    "version": "16.0.1.0.0",
    "summary": "Affiliate attribution and capped markup pricing on the CyberVilla webshop",
    "description": """
CyberVilla Affiliate
====================

Lets the CyberVilla affiliate dashboard sell through this store.

What it does
------------
* Turns an affiliate link ``/r/<code>`` into a shop visit that is priced at
  the affiliate's markup and tagged with their code, so the sale can be
  attributed and paid out.
* Enforces a hard ceiling on that markup (10% by default) inside Odoo, so a
  bad number typed into the dashboard can never reach a buyer.
* Tells the affiliate backend, once and reliably, whenever an attributed order
  is confirmed and paid — signed, queued, and retried.

What it deliberately does NOT do
--------------------------------
* It does not take payment. The website already does that through the live
  Paystack provider; this module only sets the price and records who sold it.
* It does not touch the Point of Sale. Affiliate links drive online traffic;
  in-store POS attribution is a separate, later piece.
* It does not create invoices or accounting entries.
""",
    "author": "Tech4mation / CyberVilla",
    "website": "https://www.cybervilla.io",
    "category": "Website/eCommerce",
    "license": "LGPL-3",
    # website_sale pulls in sale, account, payment, website and stock.
    "depends": ["website_sale", "sale_management"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/affiliate_security.xml",
        "security/ir.model.access.csv",
        "data/config_parameters.xml",
        "data/ir_cron.xml",
        "views/affiliate_views.xml",
        "views/affiliate_link_views.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
}
