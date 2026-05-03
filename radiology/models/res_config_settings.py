from odoo import fields, models


class RadiologyResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    radiology_firebase_push_url = fields.Char(
        string="Firebase Push URL",
        config_parameter="radiology.firebase_push_url",
    )
    radiology_firebase_push_secret = fields.Char(
        string="Firebase Push Secret",
        config_parameter="radiology.firebase_push_secret",
    )
