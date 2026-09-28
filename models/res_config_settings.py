from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """The three things an admin sets: where the dashboard is, the shared
    secret that signs what we send it, and the markup ceiling."""

    _inherit = "res.config.settings"

    cybervilla_backend_url = fields.Char(
        string="Affiliate backend URL",
        config_parameter="cybervilla_affiliate.backend_url",
        help="Where paid-order notifications are POSTed, e.g. "
             "https://affiliates.cybervilla.io/odoo/webhook",
    )
    cybervilla_webhook_secret = fields.Char(
        string="Webhook signing secret",
        config_parameter="cybervilla_affiliate.webhook_secret",
        help="Shared with the backend. Every notification is signed with it "
             "(HMAC-SHA256) so the backend can tell a real one from a forgery.",
    )
    cybervilla_max_markup_percent = fields.Float(
        string="Markup ceiling (%)",
        config_parameter="cybervilla_affiliate.max_markup_percent",
        default=10.0,
        help="The most any affiliate link may add to a price. Links over this "
             "are refused, and incoming markups are clamped to it.",
    )
