import hashlib
import hmac
import json
import logging

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# How many times a delivery is retried before it is left as failed for someone
# to look at. The cron backs off between tries by only picking rows whose next
# attempt is due.
_MAX_ATTEMPTS = 8


class CybervillaAffiliateWebhook(models.Model):
    """One thing we owe the affiliate backend, and whether we have told it yet.

    A paid affiliate order has to reach the dashboard exactly once, even if the
    dashboard is down at the moment the money lands. So the fact is written
    here first, inside the same transaction as the order, and a cron delivers
    it afterwards and keeps trying. Nothing about taking the order waits on the
    dashboard being reachable.
    """

    _name = "cybervilla.affiliate.webhook"
    _description = "CyberVilla Affiliate Webhook Delivery"
    _order = "create_date"

    sale_order_id = fields.Many2one("sale.order", ondelete="cascade", index=True)
    event = fields.Char(required=True, default="order.paid")
    payload = fields.Text(required=True)
    state = fields.Selection(
        [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")],
        default="pending", required=True, index=True,
    )
    attempts = fields.Integer(default=0)
    next_attempt = fields.Datetime(default=fields.Datetime.now, index=True)
    last_error = fields.Char()

    @api.model
    def _enqueue(self, event, payload, sale_order=None):
        # sudo: the queue row is bookkeeping, not something the person
        # confirming the order needs rights over. Without this, a salesperson
        # confirming an attributed order gets an AccessError and the
        # confirmation itself fails.
        return self.sudo().create({
            "event": event,
            "payload": json.dumps(payload, default=str),
            "sale_order_id": sale_order.id if sale_order else False,
        })

    # ------------------------------------------------------------------ #
    # Delivery
    # ------------------------------------------------------------------ #
    @api.model
    def _cron_dispatch(self, batch=50):
        """Deliver what is due. Called by the scheduled action."""
        params = self.env["ir.config_parameter"].sudo()
        url = params.get_param("cybervilla_affiliate.backend_url")
        secret = params.get_param("cybervilla_affiliate.webhook_secret") or ""
        if not url:
            _logger.info("cybervilla_affiliate: no backend_url set, nothing to deliver")
            return

        now = fields.Datetime.now()
        due = self.search(
            ["&", ("state", "in", ("pending", "failed")), ("next_attempt", "<=", now)],
            limit=batch,
        )
        for row in due:
            row._deliver(url, secret)

    def _deliver(self, url, secret):
        self.ensure_one()
        body = self.payload.encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Cybervilla-Event": self.event,
            "X-Cybervilla-Signature": signature,
        }
        self.attempts += 1
        try:
            resp = requests.post(url, data=body, headers=headers, timeout=15)
            resp.raise_for_status()
            self.write({"state": "sent", "last_error": False})
        except Exception as exc:  # noqa: BLE001 — any failure is a retry, not a crash
            message = str(exc)[:500]
            failed_for_good = self.attempts >= _MAX_ATTEMPTS
            # Back off: wait attempts² minutes before the next try, capped at a day.
            delay_minutes = min(self.attempts ** 2, 60 * 24)
            self.write({
                "state": "failed" if failed_for_good else "pending",
                "last_error": message,
                "next_attempt": fields.Datetime.add(
                    fields.Datetime.now(), minutes=delay_minutes
                ),
            })
            _logger.warning(
                "cybervilla_affiliate: delivery %s failed (attempt %s): %s",
                self.id, self.attempts, message,
            )
