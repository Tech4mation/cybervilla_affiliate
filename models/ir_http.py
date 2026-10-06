import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

# The session key that remembers which affiliate a visitor is shopping under.
SESSION_KEY = "cybervilla_aff_code"

# Odoo's own "this visitor is on a specific pricelist" key. Writing the
# affiliate's pricelist here is what actually marks the prices up: the shop
# listing, the product pages and the cart all read the pricelist through
# `website.get_current_pricelist()`, which honours this session value. Setting
# it once per visit costs nothing afterwards, whereas overriding that method
# would run a lookup on every single request.
WEBSITE_PRICELIST_KEY = "website_sale_current_pl"


def _apply_affiliate_pricelist(link):
    """Put this visitor's session on the link's pricelist.

    Odoo keeps the value only if the pricelist is usable on this website, which
    the module's own pricelists are (created against the website, with no
    company or country restriction). A failure here must never break the page
    the visitor asked for — they simply shop at the normal price.
    """
    try:
        if request and link and link.pricelist_id:
            request.session[WEBSITE_PRICELIST_KEY] = link.pricelist_id.id
    except Exception:  # noqa: BLE001
        _logger.warning("cybervilla_affiliate: could not apply pricelist", exc_info=True)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _dispatch(cls, endpoint):
        """Notice ``?ref=<code>`` on any page and remember it for this visitor.

        The dedicated ``/r/<code>`` link is the main way in, but an affiliate
        may also append ``?ref=`` to a normal shop URL, so the code is picked up
        wherever it appears. Last one wins, matching how the click is attributed.
        This only reads a query parameter and writes the session; it never
        changes what the page does, and any failure is swallowed so a bad ref
        can never take a page down.
        """
        try:
            if request and request.httprequest.args.get("ref"):
                code = request.httprequest.args.get("ref").strip()
                if code and request.session.get(SESSION_KEY) != code:
                    request.session[SESSION_KEY] = code
                    # Resolve once, when the ref first appears, rather than on
                    # every later request in the visit.
                    link = request.env["cybervilla.affiliate.link"].sudo()._resolve(code)
                    _apply_affiliate_pricelist(link)
        except Exception:  # noqa: BLE001
            _logger.debug("cybervilla_affiliate: ref capture skipped", exc_info=True)
        return super()._dispatch(endpoint)
