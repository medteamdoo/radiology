from odoo import api, fields, models


class RadiologySuspiciousMessage(models.Model):
    _name = "radiology.suspicious.message"
    _description = "Suspicious Chat Message"
    _order = "create_date desc, id desc"

    chat_message_id = fields.Many2one(
        "radiology.chat.message",
        string="Message source",
        required=True,
        ondelete="cascade",
        readonly=True,
    )
    conversation_id = fields.Many2one(
        "radiology.chat.conversation",
        related="chat_message_id.conversation_id",
        string="Conversation",
        store=True,
        readonly=True,
    )
    hospital_id = fields.Many2one(
        "radiology.hospital",
        related="conversation_id.hospital_id",
        string="Hopital",
        store=True,
        readonly=True,
    )
    radiologist_id = fields.Many2one(
        "radiology.radiologist",
        related="conversation_id.radiologist_id",
        string="Radiologue",
        store=True,
        readonly=True,
    )
    sender_type = fields.Selection(
        related="chat_message_id.sender_type",
        string="Type expediteur",
        store=True,
        readonly=True,
    )
    sender_hospital_id = fields.Many2one(
        "radiology.hospital",
        string="Envoye par hopital",
        readonly=True,
    )
    sender_radiologist_id = fields.Many2one(
        "radiology.radiologist",
        string="Envoye par radiologue",
        readonly=True,
    )
    sender_name = fields.Char(
        string="Expediteur",
        compute="_compute_sender_name",
        store=True,
    )
    message = fields.Text(
        related="chat_message_id.message",
        string="Message",
        store=True,
        readonly=True,
    )
    detection_type = fields.Selection(
        [
            ("email", "Email"),
            ("phone", "Telephone"),
            ("email_phone", "Email + Telephone"),
        ],
        string="Type de detection",
        required=True,
        readonly=True,
    )
    detected_emails = fields.Text(
        string="Emails detectes",
        readonly=True,
    )
    detected_phones = fields.Text(
        string="Telephones detectes",
        readonly=True,
    )

    _sql_constraints = [
        (
            "radiology_suspicious_message_unique_chat_message",
            "unique(chat_message_id)",
            "A suspicious message already exists for this chat message.",
        ),
    ]

    @api.depends("sender_type", "sender_hospital_id.name", "sender_radiologist_id.display_name")
    def _compute_sender_name(self):
        for record in self:
            if record.sender_type == "hospital":
                record.sender_name = record.sender_hospital_id.name or ""
            elif record.sender_type == "radiologist":
                record.sender_name = record.sender_radiologist_id.display_name or ""
            else:
                record.sender_name = ""
