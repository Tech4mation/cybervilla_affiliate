import hashlib
from datetime import datetime, time

from odoo import fields, http
from odoo.addons.http_routing.models.ir_http import slug
from odoo.http import request

from ..models.ir_http import SESSION_KEY, _apply_affiliate_pricelist


class CybervillaAffiliateController(http.Controller):
    """The link a buyer actually clicks.

    An affiliate shares ``cybervilla.io/r/<code>`` and nothing else. The code
    carries no price and no product id — those are looked up here, from the
    code, so there is nothing in the address for a buyer to edit. The visit is
    recorded, the visitor is put on the affiliate's markup, and they are sent
    on to the shop.
    """

    def _visitor_hash(self):
        """A coarse, non-identifying fingerprint, only to avoid counting one
        person refreshing as many clicks. Never stored in a way that names
        anyone."""
        parts = [
            request.httprequest.remote_addr or "",
            request.httprequest.user_agent.string if request.httprequest.user_agent else "",
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

    def _record_click(self, link):
        Click = request.env["cybervilla.affiliate.click"].sudo()
        visitor = self._visitor_hash()
        # One click per visitor per link per day is plenty for a conversion
        # rate; a refresh loop should not inflate it.
        start_of_day = fields.Datetime.to_string(
            datetime.combine(fields.Date.context_today(Click), time.min)
        )
        already = Click.search_count([
            ("link_id", "=", link.id),
            ("visitor_hash", "=", visitor),
            ("create_date", ">=", start_of_day),
        ])
        if not already:
            Click.create({
                "link_id": link.id,
                "visitor_hash": visitor,
                "referrer": request.httprequest.referrer or "",
                "landing_url": request.httprequest.url,
            })

    @http.route(["/r/<string:code>"], type="http", auth="public",
                website=True, sitemap=False, csrf=False)
    def affiliate_redirect(self, code, **kwargs):
        link = request.env["cybervilla.affiliate.link"].sudo()._resolve(code)
        if not link:
            # An unknown or retired code is not an error page — send them to the
            # shop as an ordinary visitor, earning nobody anything.
            return request.redirect("/shop")

        request.session[SESSION_KEY] = link.code
        _apply_affiliate_pricelist(link)
        try:
            self._record_click(link)
        except Exception:  # noqa: BLE001 — a click we failed to log is not worth a broken link
            request.env.cr.rollback()

        # A link that names a product lands on it; otherwise the shop front.
        if link.product_tmpl_id:
            return request.redirect("/shop/%s" % slug(link.product_tmpl_id))
        return request.redirect("/shop")
