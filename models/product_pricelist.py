from odoo import fields, models


class ProductPricelist(models.Model):
    """Keep affiliate price lists out of everyone else's way.

    An affiliate list has to be usable on the website — that is how a buyer
    who came through a link gets the markup — but it must never be *chosen*
    for anyone else. Odoo picks a default list for a shopper or a customer by
    searching for "the first usable price list", and on this store the public
    list is not attached to the website, so without this the affiliate lists
    would win that search and every visitor would pay a markup nobody is
    credited for. That happened on the Odoo 19 sandbox before this existed.

    So affiliate lists are left out of both searches Odoo uses to offer or
    default a list, while staying valid when a visit already holds one
    (`_is_available_on_website` is deliberately not changed).
    """

    _inherit = "product.pricelist"

    is_cybervilla_affiliate = fields.Boolean(
        string="Affiliate price list", copy=False, index=True, readonly=True,
        help="Created by the affiliate module for one affiliate link. Never "
             "offered to shoppers or used as anyone's default.",
    )

    def _get_partner_pricelist_multi_search_domain_hook(self, company_id):
        # The fallback "first available list" for a customer, in the shop and
        # in the back office alike.
        domain = super()._get_partner_pricelist_multi_search_domain_hook(company_id)
        return domain + [("is_cybervilla_affiliate", "=", False)]

    def _get_website_pricelists_domain(self, website):
        # The lists a website offers (`website.pricelist_ids`), which is what
        # the shop chooses a visitor's list from when nothing else applies.
        domain = super()._get_website_pricelists_domain(website)
        return domain + [("is_cybervilla_affiliate", "=", False)]
