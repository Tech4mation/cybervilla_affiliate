from odoo import api, fields, models


class SaleOrder(models.Model):
    """Attribution and the affiliate's earning, carried on the order itself.

    The link and its markup are stamped onto the order the moment the cart
    first knows the code, and the markup percentage is frozen here rather than
    read back from the link later — so re-pricing a link tomorrow never rewrites
    what an affiliate earned on a sale today.
    """

    _inherit = "sale.order"

    affiliate_link_id = fields.Many2one(
        "cybervilla.affiliate.link", string="Affiliate link",
        ondelete="set null", index=True, copy=False,
    )
    affiliate_id = fields.Many2one(
        related="affiliate_link_id.affiliate_id", store=True, index=True, copy=False,
    )
    affiliate_code = fields.Char(
        related="affiliate_link_id.code", store=True, copy=False,
    )
    # Frozen at attribution time. See the class docstring.
    affiliate_markup_percent = fields.Float(string="Markup %", copy=False)
    affiliate_earning = fields.Monetary(
        string="Affiliate earning", compute="_compute_affiliate_earning",
        store=True, currency_field="currency_id",
        help="What the affiliate keeps: the part of the untaxed total that is "
             "their markup, above CyberVilla's own price.",
    )
    affiliate_notified = fields.Boolean(
        default=False, copy=False,
        help="Whether the paid-order webhook has been queued for the dashboard.",
    )

    @api.depends("amount_untaxed", "affiliate_markup_percent")
    def _compute_affiliate_earning(self):
        for order in self:
            markup = order.affiliate_markup_percent or 0.0
            if markup <= 0:
                order.affiliate_earning = 0.0
                continue
            # The untaxed total already includes the markup, so the affiliate's
            # share is markup / (100 + markup) of it. CyberVilla's own take is
            # the rest.
            order.affiliate_earning = order.amount_untaxed * markup / (100.0 + markup)

    # ------------------------------------------------------------------ #
    # Attribution: attach the link when the cart first carries the code
    # ------------------------------------------------------------------ #
    def _apply_affiliate_link(self, link):
        """Put this order on the link's pricelist and record the attribution.

        Only the first affiliate to touch an order keeps it — last-click wins is
        decided earlier, in the session, not here, so a later re-read of the
        cart cannot quietly reassign a sale.
        """
        self.ensure_one()
        if not link or self.affiliate_link_id:
            return
        vals = {
            "affiliate_link_id": link.id,
            "affiliate_markup_percent": link.markup_percent,
        }
        if link.pricelist_id and self.pricelist_id != link.pricelist_id:
            vals["pricelist_id"] = link.pricelist_id.id
        self.write(vals)
        # Re-price existing lines onto the new pricelist. New carts have none
        # yet; a cart that already held items gets brought onto the markup.
        if vals.get("pricelist_id") and self.order_line:
            self.action_update_prices()

    # ------------------------------------------------------------------ #
    # Notify the backend once the order is confirmed and paid
    # ------------------------------------------------------------------ #
    def _affiliate_payload(self):
        self.ensure_one()
        return {
            "event": "order.paid",
            "order_ref": self.name,
            "order_id": self.id,
            "affiliate_code": self.affiliate_code,
            "affiliate_backend_ref": self.affiliate_id.backend_ref,
            "link_backend_ref": self.affiliate_link_id.backend_ref,
            "markup_percent": self.affiliate_markup_percent,
            "currency": self.currency_id.name,
            "amount_total": self.amount_total,
            "amount_untaxed": self.amount_untaxed,
            "affiliate_earning": self.affiliate_earning,
            "customer_email": self.partner_id.email or "",
            "confirmed_at": fields.Datetime.to_string(self.date_order),
        }

    def _notify_affiliate_backend(self):
        Webhook = self.env["cybervilla.affiliate.webhook"]
        for order in self:
            if order.affiliate_link_id and not order.affiliate_notified:
                Webhook._enqueue("order.paid", order._affiliate_payload(), order)
                order.affiliate_notified = True

    def action_confirm(self):
        """A website order confirms once Paystack reports the money in.

        That is the moment an affiliate has genuinely earned, so it is where the
        dashboard is told. Manual confirmations of an attributed order count
        too — they are still a real, paid, attributed sale.
        """
        result = super().action_confirm()
        self._notify_affiliate_backend()
        return result

    def _action_cancel(self):
        """A sale that is cancelled un-earns the affiliate.

        Only orders the dashboard was already told about are worth telling
        again — an unpaid cart being abandoned was never an earning. The
        backend decides what reversing means; the store's job is to say it
        happened.
        """
        result = super()._action_cancel()
        Webhook = self.env["cybervilla.affiliate.webhook"]
        for order in self:
            if order.affiliate_link_id and order.affiliate_notified:
                payload = order._affiliate_payload()
                payload["event"] = "order.cancelled"
                Webhook._enqueue("order.cancelled", payload, order)
        return result
