import logging
import time

from odoo import models
from odoo.http import request

from odoo.addons.website_sale.models.website import (
    PRICELIST_SELECTED_SESSION_CACHE_KEY,
    PRICELIST_SESSION_CACHE_KEY,
)

_logger = logging.getLogger(__name__)

# Which affiliate code this visitor is shopping under.
SESSION_KEY = "cybervilla_aff_code"
# The pricelist that code put them on. Kept separately from Odoo's own keys,
# because Odoo drops and recomputes those (on sign-in, on an address change,
# and every hour on the shop page), and this is what lets us put them back
# without asking the database on every request.
SESSION_PRICELIST_KEY = "cybervilla_aff_pricelist"
# website_sale refreshes its cached pricelist once this is an hour old.
_PRICELIST_TIME_KEY = "website_sale_pricelist_time"


def remember_link(link):
    """Put this visitor on the link's markup for the rest of their visit.

    Writing Odoo's own session keys is what actually marks the prices up: the
    shop, the product pages and a new cart all read the visitor's pricelist
    from `website_sale_current_pl`, and checkout keeps a pricelist the
    visitor "selected" (`website_sale_selected_pl_id`) when it recomputes the
    order for a new address. Doing it this way means no hot path of the shop
    is overridden. A failure here must never break the page — the visitor
    simply shops at the normal price.
    """
    try:
        if not (request and link):
            return
        request.session[SESSION_KEY] = link.code
        if link.pricelist_id:
            request.session[SESSION_PRICELIST_KEY] = link.pricelist_id.id
            hold_pricelist()
    except Exception:  # noqa: BLE001
        _logger.warning("cybervilla_affiliate: could not apply pricelist", exc_info=True)


def hold_pricelist():
    """Make sure Odoo's pricelist keys still point at the affiliate's list.

    Cheap enough to run on every page: it only compares session values, and
    writes (which marks the session for saving) only when something drifted.
    """
    session = request.session
    pricelist_id = session.get(SESSION_PRICELIST_KEY)
    if not pricelist_id:
        return
    if session.get(PRICELIST_SESSION_CACHE_KEY) != pricelist_id:
        session[PRICELIST_SESSION_CACHE_KEY] = pricelist_id
    if session.get(PRICELIST_SELECTED_SESSION_CACHE_KEY) != pricelist_id:
        session[PRICELIST_SELECTED_SESSION_CACHE_KEY] = pricelist_id
    # Otherwise the shop page drops the cached pricelist after an hour and
    # renders that one page at public prices before we can put it back.
    stamp = session.get(_PRICELIST_TIME_KEY)
    if stamp is not None and stamp < time.time() - 30 * 60:
        session[_PRICELIST_TIME_KEY] = time.time()


def forget_affiliate():
    """Drop the affiliate from this visit, e.g. because the link was retired.

    Without this a buyer whose link was switched off would keep paying the
    markup with nobody credited for it.
    """
    session = request.session
    pricelist_id = session.pop(SESSION_PRICELIST_KEY, None)
    session.pop(SESSION_KEY, None)
    for key in (PRICELIST_SESSION_CACHE_KEY, PRICELIST_SELECTED_SESSION_CACHE_KEY):
        if pricelist_id and session.get(key) == pricelist_id:
            session.pop(key, None)


def held_pricelist(website):
    """The affiliate pricelist this visit is on, if it is still usable here."""
    if not request:
        return None
    pricelist_id = request.session.get(SESSION_PRICELIST_KEY)
    if not pricelist_id:
        return None
    pricelist = website.env["product.pricelist"].sudo().browse(pricelist_id).exists()
    if pricelist and pricelist._is_available_on_website(website):
        return pricelist
    return None


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _frontend_pre_dispatch(cls):
        """Notice ``?ref=<code>`` on any shop page, and keep the markup on.

        `_frontend_pre_dispatch` runs for website pages only, after Odoo has
        set up the visitor's pricelist lazily but before anything has read
        it, so a session written here is what the page is priced with.

        The dedicated ``/r/<code>`` link is the main way in, but an affiliate
        may also append ``?ref=`` to a normal shop URL, so the code is picked
        up wherever it appears. Last one wins, matching how the click is
        attributed. Any failure is swallowed: a bad ref must never take a
        page down.
        """
        super()._frontend_pre_dispatch()
        try:
            code = (request.httprequest.args.get("ref") or "").strip()
            if code and request.session.get(SESSION_KEY) != code:
                # Resolved once, when the ref first appears, not on every
                # later request in the visit.
                link = request.env["cybervilla.affiliate.link"].sudo()._resolve(code)
                if link:
                    remember_link(link)
            hold_pricelist()
        except Exception:  # noqa: BLE001
            _logger.debug("cybervilla_affiliate: ref capture skipped", exc_info=True)
