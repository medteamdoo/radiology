from odoo import models, fields, api
import secrets

class Radiologist(models.Model):
    _name = "radiology.radiologist"
    _description = "Radiologist"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    user_id = fields.Many2one('res.users', string="User")
    api_token = fields.Char(string="API Token", copy=False)

    display_name = fields.Char()
    email = fields.Char()
    phone = fields.Char()
    image_1920 = fields.Image("Photo", max_width=1920, max_height=1920)
    specialties = fields.Char()
    bio = fields.Text()
    experience_years = fields.Integer()
    cv_attachment_ids = fields.Many2many('ir.attachment')

    rating_avg = fields.Float(
        string="Note moyenne",
        compute="_compute_rating_avg",
        store=True,
        readonly=True
    )
    rating_count = fields.Integer(
        string="Nombre de notes reçues",
        compute="_compute_rating_avg",
        store=True,
        readonly=True
    )

    rating_ids = fields.One2many(
        'radiology.rating',
        'radiologist_id',
        string="Notes"
    )

    @api.depends('rating_ids.score')
    def _compute_rating_avg(self):
        for rec in self:
            if rec.rating_ids:
                total = sum(r.score for r in rec.rating_ids)
                rec.rating_count = len(rec.rating_ids)
                rec.rating_avg = total / rec.rating_count
            else:
                rec.rating_avg = 0.0
                rec.rating_count = 0

    @api.model
    def generate_api_token(self):
        self.api_token = secrets.token_urlsafe(32)
        return self.api_token
