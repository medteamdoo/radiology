from odoo import models, fields

class Mission(models.Model):
    _name = "radiology.mission"
    _description = "Mission"

    # Nom de la mission
    name = fields.Char(string="Name", required=True)

    # Hôpital lié
    hospital_id = fields.Many2one('radiology.hospital', string="Hospital", required=True)

    # Spécialité concernée
    speciality_ids = fields.Many2many('radiology.specialty','mission_specialty_rel',  # Nom table relation
        'mission_id', 'specialty_id', string="Speciality")
    brand_ids = fields.Many2many('radiology.brand','mission_brand_rel','mission_id','brand_id' ,string="Brand")

    # Description de la mission
    description = fields.Text(string="Description")

    tarif = fields.Float(string="Tarif")

    # Dates de début et fin
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")

    # Statut
    status = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('done', 'Done')
    ], string="Status", default='draft')
