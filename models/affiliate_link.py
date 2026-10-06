from odoo import api, fields, models
from odoo.exceptions import ValidationError


def _max_markup(env):
    """The ceiling on any markup, as a percentage. Configurable, defaults to 10."""
    value = env["ir.config_parameter"].sudo().get_param(
        "cybervilla_affiliate.max_markup_percent", "10"
    )
    try:
        return float(value)
    except (TypeError, ValueError):
        return 10.0


class CybervillaAffiliateLink(models.Model):
    """A shareable code that prices the shop at one affiliate's markup.

    Every link owns exactly one pricelist, holding a single global rule that
    adds the link's markup to every product's price. The pricelist is the
    whole mechanism: once a visitor's cart is on it, Odoo's own website, cart
    and order code do the pricing, and there is no custom price maths to fight
    with website_sale.

    The markup travels with the link, not the product — a visitor who arrives
    on an iPhone link and buys a charger still buys it at the link's markup.
    That is why the rule is global rather than tied to one product, and it
    matches what the dashboard tells affiliates.
    """

    _name = "cybervilla.affiliate.link"
    _description = "CyberVilla Affiliate Link"
    _order = "code"

    code = fields.Char(required=True, index=True, copy=False,
                       help="What goes in the address: cybervilla.io/r/<code>.")
    label = fields.Char(help="The affiliate's own name for this link.")
    affiliate_id = fields.Many2one(
        "cybervilla.affiliate", required=True, ondelete="cascade", index=True,
    )
    backend_ref = fields.Char(string="Dashboard link ID", index=True, copy=False)

    # Held as a percentage because a link's markup is capped as a percentage,
    # and because the same number prices a storewide link and a product link.
    markup_percent = fields.Float(
        string="Markup %", required=True, default=0.0,
        help="Added to every product's price for a buyer on this link. "
             "Cannot exceed the store's markup ceiling.",
    )
    # Product links exist to point the landing page at one product; the markup
    # still applies storewide. Optional.
    product_tmpl_id = fields.Many2one(
        "product.template", string="Featured product", ondelete="set null",
    )

    pricelist_id = fields.Many2one(
        "product.pricelist", string="Pricelist", ondelete="restrict", copy=False,
        help="Created and maintained by this module. Do not edit by hand.",
    )
    active = fields.Boolean(default=True)

    click_ids = fields.One2many("cybervilla.affiliate.click", "link_id", string="Clicks")
    click_count = fields.Integer(compute="_compute_click_count")

    _sql_constraints = [
        ("code_uniq", "unique(code)", "This affiliate code is already in use."),
        ("backend_ref_uniq", "unique(backend_ref)",
         "A link with this dashboard id already exists."),
    ]

    def _compute_click_count(self):
        for link in self:
            link.click_count = len(link.click_ids)

    @api.constrains("markup_percent")
    def _check_markup_ceiling(self):
        ceiling = _max_markup(self.env)
        for link in self:
            if link.markup_percent < 0:
                raise ValidationError("A markup cannot be negative.")
            if link.markup_percent > ceiling:
                raise ValidationError(
                    "A markup of %.2f%% is over the %.0f%% ceiling."
                    % (link.markup_percent, ceiling)
                )

    # ------------------------------------------------------------------ #
    # The pricelist behind each link
    # ------------------------------------------------------------------ #
    def _pricelist_values(self):
        self.ensure_one()
        currency = self.env.company.currency_id
        # A formula rule with a *negative* discount is Odoo's way of adding to
        # a price rather than taking off it: new = list * (1 - discount/100),
        # so discount = -markup gives list * (1 + markup/100).
        item = {
            "applied_on": "3_global",
            "compute_price": "formula",
            "base": "list_price",
            "price_discount": -self.markup_percent,
            "price_surcharge": 0.0,
        }
        return {
            "name": "Affiliate %s (%s)" % (self.code, self.affiliate_id.name or ""),
            "currency_id": currency.id,
            "item_ids": [(5, 0, 0), (0, 0, item)],
        }

    def _sync_pricelist(self):
        """Make each link's pricelist match its markup. Safe to call repeatedly."""
        Pricelist = self.env["product.pricelist"].sudo()
        for link in self:
            values = link._pricelist_values()
            if link.pricelist_id:
                link.pricelist_id.write(values)
            else:
                link.pricelist_id = Pricelist.create(values)

    @api.model_create_multi
    def create(self, vals_list):
        links = super().create(vals_list)
        links._sync_pricelist()
        return links

    def write(self, vals):
        result = super().write(vals)
        if {"markup_percent", "code", "affiliate_id"} & set(vals):
            self._sync_pricelist()
        return result

    # ------------------------------------------------------------------ #
    # How the backend keeps this table in step
    # ------------------------------------------------------------------ #
    @api.model
    def upsert_from_backend(self, vals):
        """Create or update a link from the dashboard, keyed on its dashboard id.

        The markup is clamped to the ceiling here as well as validated, so the
        store is safe even if the caller forgot to check. Returns a small dict
        the backend can store: the Odoo ids and the markup actually applied.
        Callable over XML-RPC by the integration user.
        """
        vals = dict(vals or {})
        backend_ref = vals.get("backend_ref")
        if not backend_ref:
            raise ValueError("backend_ref is required to upsert a link.")

        ceiling = _max_markup(self.env)
        if "markup_percent" in vals:
            vals["markup_percent"] = max(0.0, min(float(vals["markup_percent"]), ceiling))

        link = self.search([("backend_ref", "=", backend_ref)], limit=1)
        if link:
            link.write(vals)
        else:
            link = self.create(vals)
        return {
            "link_id": link.id,
            "affiliate_id": link.affiliate_id.id,
            "pricelist_id": link.pricelist_id.id,
            "markup_percent": link.markup_percent,
        }

    @api.model
    def _resolve(self, code):
        """The live link for a code, or an empty recordset."""
        if not code:
            return self.browse()
        return self.search([("code", "=", code), ("active", "=", True)], limit=1)
