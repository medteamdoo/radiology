import json
import logging
import re
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from odoo import api, fields, models


_logger = logging.getLogger(__name__)
EMAIL_REGEX = re.compile(
    r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])"
)
PHONE_REGEX = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{6,}\d)(?!\w)")


class RadiologyChatMessage(models.Model):
    _name = "radiology.chat.message"
    _description = "Chat Message"
    _order = "create_date asc"

    conversation_id = fields.Many2one(
        'radiology.chat.conversation',
        required=True,
        ondelete='cascade'
    )

    sender_type = fields.Selection([
        ('hospital', 'Hospital'),
        ('radiologist', 'Radiologist')
    ], required=True)

    sender_id = fields.Integer(required=True)
    message = fields.Text(required=True)
    is_read_by_hospital = fields.Boolean(default=False)
    is_read_by_radiologist = fields.Boolean(default=False)

    def _extract_contact_details(self, message):
        text = (message or "").strip()
        emails = sorted({match.group(1) for match in EMAIL_REGEX.finditer(text)})

        phones = []
        seen_digits = set()
        for raw_phone in PHONE_REGEX.findall(text):
            raw_phone = (raw_phone or "").strip()
            digits_only = re.sub(r"\D", "", raw_phone)
            if not 8 <= len(digits_only) <= 15:
                continue
            if digits_only in seen_digits:
                continue
            seen_digits.add(digits_only)
            phones.append(raw_phone)

        return emails, phones

    def _create_suspicious_message_records(self):
        suspicious_model = self.env["radiology.suspicious.message"].sudo()
        existing_ids = set(
            suspicious_model.search([("chat_message_id", "in", self.ids)]).mapped("chat_message_id").ids
        )
        vals_list = []

        for record in self:
            if record.id in existing_ids:
                continue

            emails, phones = record._extract_contact_details(record.message)
            if not emails and not phones:
                continue

            detection_type = "email_phone" if emails and phones else "email" if emails else "phone"
            vals = {
                "chat_message_id": record.id,
                "detection_type": detection_type,
                "detected_emails": ", ".join(emails) if emails else False,
                "detected_phones": ", ".join(phones) if phones else False,
            }

            if record.sender_type == "hospital":
                vals["sender_hospital_id"] = record.conversation_id.hospital_id.id
            elif record.sender_type == "radiologist":
                vals["sender_radiologist_id"] = record.conversation_id.radiologist_id.id

            vals_list.append(vals)

        if vals_list:
            suspicious_model.create(vals_list)

    def _send_push_notification(self, *, tokens, title, body, data=None):
        tokens = [token for token in (tokens or []) if token]
        if not tokens:
            _logger.info("Chat push skipped: no active FCM tokens")
            return False

        params = self.env["ir.config_parameter"].sudo()
        push_url = (params.get_param("radiology.firebase_push_url") or "").strip()
        push_secret = (params.get_param("radiology.firebase_push_secret") or "").strip()
        if not push_url:
            _logger.info("Chat push skipped: missing radiology.firebase_push_url")
            return False

        payload = {
            "secret": push_secret,
            "tokens": tokens,
            "title": title,
            "body": body,
            "data": data or {},
        }

        try:
            req = urllib_request.Request(
                push_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=10) as response:
                status = getattr(response, "status", 200)
                if 200 <= status < 300:
                    _logger.info(
                        "Chat push sent for conversation %s to %s device(s)",
                        data.get("conversation_id") if isinstance(data, dict) else "?",
                        len(tokens),
                    )
                    return True
                _logger.warning("Chat push returned status %s", status)
        except (HTTPError, URLError, TimeoutError) as exc:
            _logger.warning("Chat push failed: %s", str(exc))
        except Exception as exc:
            _logger.exception("Unexpected chat push error: %s", str(exc))
        return False

    def _notify_radiologist_for_hospital_message(self):
        Device = self.env["radiology.mobile.device"].sudo()
        for record in self.filtered(lambda item: item.sender_type == "hospital"):
            devices = Device.search([
                ("radiologist_id", "=", record.conversation_id.radiologist_id.id),
                ("is_active", "=", True),
            ])
            self._send_push_notification(
                tokens=devices.mapped("fcm_token"),
                title="Nouveau message",
                body=(
                    f"{record.conversation_id.hospital_id.name or 'Un hopital'} "
                    "vous a envoye un message."
                ),
                data={
                    "type": "chat_message",
                    "conversation_id": str(record.conversation_id.id),
                },
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            update_vals = {}
            if record.sender_type == "hospital":
                update_vals.update({
                    "is_read_by_hospital": True,
                    "is_read_by_radiologist": False,
                })
            else:
                update_vals.update({
                    "is_read_by_hospital": False,
                    "is_read_by_radiologist": True,
                })
            if update_vals:
                record.write(update_vals)
            record.conversation_id.sudo().write({
                "last_message": record.message,
                "last_message_date": record.create_date or fields.Datetime.now(),
            })
        records._create_suspicious_message_records()
        records._notify_radiologist_for_hospital_message()
        return records
