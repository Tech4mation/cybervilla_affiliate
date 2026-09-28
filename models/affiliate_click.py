from odoo import fields, models


class CybervillaAffiliateClick(models.Model):
    """One visit that arrived on an affiliate link.

    Kept so the dashboard can show a click count next to a sale count and work
    out how well a link converts. Deliberately thin: no personal data beyond a
    coarse record of the visit, because a click is not a customer.
    """

    _name = "cybervilla.affiliate.click"
    _description = "CyberVilla Affiliate Click"
    _order = "create_date desc"

    link_id = fields.Many2one(
        "cybervilla.affiliate.link", required=True, ondelete="cascade", index=True,
    )
    affiliate_id = fields.Many2one(
        related="link_id.affiliate_id", store=True, index=True,
    )
    # A coarse fingerprint, only to avoid counting the same refresh ten times.
    # Not an identity, and not tied to a person.
    visitor_hash = fields.Char(index=True)
    referrer = fields.Char()
    landing_url = fields.Char()
