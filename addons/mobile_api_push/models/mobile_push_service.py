import json

from odoo import models
from odoo.addons.queue_job.job import job

from ..services.apns_client import ApnsClient


class MobilePushService(models.AbstractModel):
    _name = "mobile.push.service"
    _description = "Mobile Push Service"

    def send_template(self, template_key, device_domain, context=None):
        context = context or {}
        template = (
            self.env["mobile.push.template"]
            .sudo()
            .search([("key", "=", template_key), ("enabled", "=", True)], limit=1)
        )
        if not template:
            return 0
        devices = self.env["mobile.device"].sudo().search(device_domain)
        count = 0
        for device in devices:
            if device.push_opt_out or not device.push_token:
                continue
            self.with_delay(channel="mobile.push.high")._send_push_job(
                device.id, template.id, context
            )
            count += 1
        return count

    @job
    def _send_push_job(self, device_id, template_id, context=None):
        context = context or {}
        device = self.env["mobile.device"].sudo().browse(device_id)
        template = self.env["mobile.push.template"].sudo().browse(template_id)
        payload = self._build_payload(template, context)
        client = ApnsClient(self.env)
        return client.send(device.push_token, payload)

    def _build_payload(self, template, context):
        try:
            title = template.title.format(**context)
            body = template.body.format(**context)
        except KeyError:
            title = template.title
            body = template.body
        deeplink = None
        if template.deeplink_payload:
            try:
                deeplink = json.loads(template.deeplink_payload)
            except json.JSONDecodeError:
                deeplink = None
        aps = {
            "alert": {"title": title, "body": body},
            "sound": "default",
        }
        payload = {"aps": aps}
        if deeplink:
            payload["deeplink"] = deeplink
        return payload
