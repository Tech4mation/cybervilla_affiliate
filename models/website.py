import logging

from odoo import models
from odoo.http import request

from .ir_http import SESSION_KEY, forget_affiliate, held_pricelist

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = "website"

    # ------------------------------------------------------------------ #
    # Attribution: tag the cart the first time it meets the code
    # ------------------------------------------------------------------ #
    # Odoo 19 has no single "get the cart" method any more (16's
    # `sale_get_order`). A cart is either made fresh by `_create_cart` or
    # fetched for the visit by `_get_and_cache_current_cart`; between them
    # they see every cart, including one that existed before the visitor
    # clicked an affiliate link.

    def _create_cart(self):
        cart = super()._create_cart()
        self._attribute_cart(cart)
        return cart

    def _get_and_cache_current_cart(self):
        cart = super()._get_and_cache_current_cart()
        # Read-only requests (product pages, for instance) may look at the
        # cart but cannot write to it; the next ordinary request will.
        if cart and not cart.affiliate_link_id and not request.env.cr.readonly:
            self._attribute_cart(cart)
        return cart

    def _attribute_cart(self, cart):
        """Credit this cart to the visitor's affiliate, once, if they have one.

        Only a cart with no affiliate yet is touched, so a later visit through
        someone else's link cannot quietly take a sale that was already made.
        A savepoint keeps any failure to this step: the buyer still gets their
        cart, just without the markup.
        """
        code = request.session.get(SESSION_KEY) if request else None
        if not (cart and code) or cart.affiliate_link_id:
            return
        try:
            with self.env.cr.savepoint():
                link = self.env["cybervilla.affiliate.link"].sudo()._resolve(code)
                if link:
                    cart._apply_affiliate_link(link)
                else:
                    # Retired since they clicked. Stop charging the markup.
                    forget_affiliate()
        except Exception:  # noqa: BLE001
            _logger.warning(
                "cybervilla_affiliate: could not attribute cart %s to '%s'",
                cart.id, code, exc_info=True,
            )

    # ------------------------------------------------------------------ #
    # Keep the buyer on the affiliate's price list
    # ------------------------------------------------------------------ #
    def get_pricelist_available(self, show_visible=False):
        """On an affiliate visit, the affiliate's list is the only one on offer.

        This one method decides both whether the shop shows a price-list
        menu (only when it gets back more than one) and whether a request to
        switch lists is allowed (`is_pricelist_available`). Returning just
        the affiliate's list therefore hides the menu and refuses the switch,
        so a buyer cannot strip the markup by picking the public price.
        The theme's own header menu calls the same method.
        """
        pricelists = super().get_pricelist_available(show_visible=show_visible)
        held = held_pricelist(self)
        if held:
            return pricelists.browse(held.id)
        return pricelists
