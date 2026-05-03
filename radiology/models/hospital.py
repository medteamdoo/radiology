from odoo import models, fields, api
import secrets

class Hospital(models.Model):
    _name = "radiology.hospital"
    _description = "Hospital"
    _inherit = ["mail.thread", "mail.activity.mixin"]


    user_id = fields.Many2one('res.users', string="User")
    api_token = fields.Char(string="API Token", copy=False)

    name = fields.Char()
    city = fields.Char()
    email = fields.Char()
    phone = fields.Char()
    longitude = fields.Float()
    latitude = fields.Float()
    image_1920 = fields.Image("Photo", max_width=1920, max_height=1920)
    missions_count = fields.Integer(compute="_compute_missions_count")
    subscription_plan = fields.Selection(
        [
            ('freemium', 'Freemium'),
            ('premium', 'Premium'),
            ('pro', 'Pro'),
        ],
        string="Abonnement",
        default='freemium',
        tracking=True,
        required=True,
    )

    # ✅ Favoris radiologues
    favorite_radiologist_ids = fields.Many2many(
        'radiology.radiologist',
        'radiology_hospital_radiologist_fav_rel',  # table relation
        'hospital_id', 'radiologist_id',
        string="Radiologues favoris"
    )

    @api.model
    def generate_api_token(self):
        self.api_token = secrets.token_urlsafe(32)
        return self.api_token

    def _compute_missions_count(self):
        Mission = self.env['radiology.mission']
        for h in self:
            h.missions_count = Mission.search_count([('hospital_id','=',h.id)])


