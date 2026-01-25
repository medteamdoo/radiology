from odoo import models, fields

class RadiologistAvailability(models.Model):
    _name = "radiology.radiologist.availability"
    _description = "Radiologist Availability"
    _order = "weekday, start_time"

    radiologist_id = fields.Many2one(
        "radiology.radiologist",
        required=True,
        ondelete="cascade"
    )

    weekday = fields.Selection([
        ('0', 'Lundi'),
        ('1', 'Mardi'),
        ('2', 'Mercredi'),
        ('3', 'Jeudi'),
        ('4', 'Vendredi'),
        ('5', 'Samedi'),
        ('6', 'Dimanche'),
    ], required=True, string="Jour")

    start_time = fields.Float(
        string="Heure début",
        help="Ex: 8.5 = 08:30"
    )

    end_time = fields.Float(
        string="Heure fin",
        help="Ex: 18.0 = 18:00"
    )

    is_night = fields.Boolean(
        string="Disponibilité de nuit",
        help="Créneau de nuit (ex: 22h–6h)"
    )

    is_weekend = fields.Boolean(
        string="Weekend",
        compute="_compute_is_weekend",
        store=True
    )

    active = fields.Boolean(default=True)

    def _compute_is_weekend(self):
        for rec in self:
            rec.is_weekend = rec.weekday in ('5', '6')
