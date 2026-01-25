from odoo import models, fields

class RadiologySpecialty(models.Model):
    _name = "radiology.specialty"
    _description = "Spécialité Radiologique"

    name = fields.Char(required=True)
