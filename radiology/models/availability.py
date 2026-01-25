from odoo import models, fields, api

class RadiologyAvailabilityDay(models.Model):
    _name = "radiology.availability.day"
    _description = "Radiologist Daily Availability"
    _order = "date"

    radiologist_id = fields.Many2one(
        'radiology.radiologist',
        required=True,
        ondelete="cascade"
    )

    date = fields.Date(required=True)

    # 🌞 Jour
    available_day = fields.Boolean(string="Available (Day)")

    # 🌙 Nuit
    available_night = fields.Boolean(string="Available (Night)")

    # 📆 Week-end (calculé)
    is_weekend = fields.Boolean(
        compute="_compute_is_weekend",
        store=True
    )

    @api.depends('date')
    def _compute_is_weekend(self):
        for rec in self:
            if rec.date:
                rec.is_weekend = rec.date.weekday() in (5, 6)
            else:
                rec.is_weekend = False

    _sql_constraints = [
        (
            'unique_radiologist_date',
            'unique(radiologist_id, date)',
            'Availability already exists for this date.'
        )
    ]
