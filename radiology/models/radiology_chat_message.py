from odoo import models, fields


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
