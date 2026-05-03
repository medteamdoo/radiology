from odoo import fields, models


class RadiologyMobileDevice(models.Model):
    _name = "radiology.mobile.device"
    _description = "Radiology Mobile Device"
    _order = "last_seen desc, id desc"

    radiologist_id = fields.Many2one(
        "radiology.radiologist",
        required=True,
        ondelete="cascade",
        index=True,
    )
    fcm_token = fields.Char(required=True, index=True)
    platform = fields.Char()
    device_name = fields.Char()
    is_active = fields.Boolean(default=True, index=True)
    last_seen = fields.Datetime(default=fields.Datetime.now, index=True)

    _sql_constraints = [
        (
            "unique_fcm_token",
            "unique(fcm_token)",
            "This Firebase token is already registered.",
        ),
    ]
