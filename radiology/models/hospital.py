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
    image_1920 = fields.Image("Photo", max_width=1920, max_height=1920)
    missions_count = fields.Integer(compute="_compute_missions_count")

    @api.model
    def generate_api_token(self):
        self.api_token = secrets.token_urlsafe(32)
        return self.api_token

    def _compute_missions_count(self):
        Mission = self.env['radiology.mission']
        for h in self:
            h.missions_count = Mission.search_count([('hospital_id','=',h.id)])
