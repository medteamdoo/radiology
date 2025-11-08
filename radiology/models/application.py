from odoo import models, fields

class Application(models.Model):
    _name = "radiology.application"
    _description = "Radiologist Application to Mission"

    radiologist_id = fields.Many2one('radiology.radiologist', required=True)
    mission_id = fields.Many2one('radiology.mission', required=True)
    status = fields.Selection([('pending','Pending'),('accepted','Accepted'),('rejected','Rejected')], default='pending')
