from odoo import api, fields, models


class CybervillaAffiliate(models.Model):
    """One person who sells CyberVilla stock for a markup.

    The affiliate dashboard is the system of record for who an affiliate is
    and their payout details; this table is Odoo's local copy of just enough
    to price a sale and attribute it. It is kept in step by the backend, which
    calls ``upsert_from_backend`` over XML-RPC — Odoo never invents an
    affiliate on its own.
    """

    _name = "cybervilla.affiliate"
    _description = "CyberVilla Affiliate"
    _order = "name"

    name = fields.Char(required=True)
    # The affiliate's id in the dashboard. This, not Odoo's id, is how the two
    # systems name the same person to each other.
    backend_ref = fields.Char(
        string="Dashboard ID", index=True, copy=False,
        help="The affiliate's id in the affiliate dashboard.",
    )
    email = fields.Char()
    # The customer record, if this affiliate has ever also bought from us.
    # Only used to spot self-referral; never required.
    partner_id = fields.Many2one("res.partner", string="Contact", ondelete="set null")
    active = fields.Boolean(default=True)

    link_ids = fields.One2many("cybervilla.affiliate.link", "affiliate_id", string="Links")
    link_count = fields.Integer(compute="_compute_counts")
    order_count = fields.Integer(compute="_compute_counts")

    _sql_constraints = [
        ("backend_ref_uniq", "unique(backend_ref)",
         "An affiliate with this dashboard id already exists."),
    ]

    def _compute_counts(self):
        for affiliate in self:
            affiliate.link_count = len(affiliate.link_ids)
            affiliate.order_count = self.env["sale.order"].search_count(
                [("affiliate_id", "=", affiliate.id)]
            )

    @api.model
    def upsert_from_backend(self, vals):
        """Create or update an affiliate from the dashboard, keyed on its id.

        Returns the Odoo id. Callable over XML-RPC by the integration user.
        """
        backend_ref = (vals or {}).get("backend_ref")
        if not backend_ref:
            raise ValueError("backend_ref is required to upsert an affiliate.")
        record = self.search([("backend_ref", "=", backend_ref)], limit=1)
        if record:
            record.write(vals)
            return record.id
        return self.create(vals).id
