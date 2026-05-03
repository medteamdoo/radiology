from odoo import models, fields


class Mission(models.Model):
    _name = "radiology.mission"
    _description = "Mission"

    name = fields.Char(required=True)
    hospital_id = fields.Many2one('radiology.hospital', required=True)

    speciality_ids = fields.Many2many(
        'radiology.specialty', 'mission_specialty_rel',
        'mission_id', 'specialty_id'
    )
    brand_ids = fields.Many2many(
        'radiology.brand', 'mission_brand_rel',
        'mission_id', 'brand_id'
    )

    description = fields.Text()
    avantage = fields.Text()

    tarif_type = fields.Selection(
        [('hour', 'Par heure'), ('day', 'Par jour')],
        default='day', required=True
    )
    tarif = fields.Float()

    start_date = fields.Date()
    end_date = fields.Date()

    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('published', 'Published'),
            ('assigned', 'Affectée'),
            ('done', 'Done')
        ],
        default='draft'
    )

    application_ids = fields.One2many(
        'radiology.application',
        'mission_id'
    )

    # ✅ NOUVEAU CHAMP
    assigned_radiologist_id = fields.Many2one(
        'radiology.radiologist',
        string="Radiologue affecté"
    )
