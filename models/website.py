import logging

from odoo import models
from odoo.http import request

from .ir_http import SESSION_KEY

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = "website"

    def sale_get_order(self, *args, **kwargs):
        """Whenever the shop fetches the visitor's cart, make sure the cart is
        on the affiliate's markup and tagged with their code.

        This is the one place every cart passes through, so attaching the link
        here catches the visitor no matter which page they added an item from.
        It runs after Odoo has the order, and only stamps an order that has no
        affiliate yet — so the pricelist and the attribution are set once and
        then left alone.
        """
        order = super().sale_get_order(*args, **kwargs)
        code = request.session.get(SESSION_KEY) if request else None
        if not (order and code and not order.affiliate_link_id):
            return order
        # A savepoint so that if attribution or re-pricing fails, only that is
        # undone — the visitor still gets their cart, just without the markup.
        try:
            with self.env.cr.savepoint():
                link = self.env["cybervilla.affiliate.link"].sudo()._resolve(code)
                if link:
                    order._apply_affiliate_link(link)
        except Exception:  # noqa: BLE001
            _logger.warning(
                "cybervilla_affiliate: could not attribute cart %s to '%s'",
                order.id, code, exc_info=True,
            )
        return order
