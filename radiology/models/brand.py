from odoo import models, fields

class RadiologyBrand(models.Model):
    _name = "radiology.brand"
    _description = "Marque Equipement Radiologique"

    name = fields.Char(required=True)
