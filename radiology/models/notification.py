from odoo import fields, models


class RadiologyNotification(models.Model):
    _name = "radiology.notification"
    _description = "Radiology Notification"
    _order = "is_read asc, create_date desc, id desc"

    hospital_id = fields.Many2one(
        "radiology.hospital",
        string="Hospital",
        required=True,
        ondelete="cascade",
        index=True,
    )
    title = fields.Char(required=True)
    message = fields.Text(required=True)
    type = fields.Selection(
        [
            ("info", "Info"),
            ("success", "Success"),
            ("warning", "Warning"),
            ("danger", "Danger"),
        ],
        default="info",
        required=True,
    )
    is_read = fields.Boolean(string="Read", default=False, index=True)
    action_url = fields.Char(string="Action URL")

    def action_mark_as_read(self):
        self.write({"is_read": True})
