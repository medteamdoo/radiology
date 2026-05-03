from odoo import models, fields


class RadiologyChatConversation(models.Model):
    _name = "radiology.chat.conversation"
    _description = "Chat Conversation"
    _order = "last_message_date desc"

    hospital_id = fields.Many2one('radiology.hospital', required=True)
    radiologist_id = fields.Many2one('radiology.radiologist', required=True)

    last_message = fields.Text()
    last_message_date = fields.Datetime()

    is_active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "unique_hospital_radiologist_conversation",
            "unique(hospital_id, radiologist_id)",
            "A conversation already exists for this hospital and radiologist.",
        ),
    ]
