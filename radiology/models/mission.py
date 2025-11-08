from odoo import models, fields

class Mission(models.Model):
    _name = "radiology.mission"
    _description = "Mission"

    # Nom de la mission
    name = fields.Char(string="Name", required=True)

    # Hôpital lié
    hospital_id = fields.Many2one('radiology.hospital', string="Hospital", required=True)

    # Spécialité concernée
    specialty = fields.Char(string="Specialty")

    # Description de la mission
    description = fields.Text(string="Description")

    # Dates de début et fin
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")

    # Statut
    status = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('done', 'Done')
    ], string="Status", default='draft')
