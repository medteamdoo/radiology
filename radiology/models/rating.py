from odoo import models, fields, api, exceptions, _

class RadiologyRating(models.Model):
    _name = "radiology.rating"
    _description = "Radiologist Rating"

    radiologist_id = fields.Many2one(
        'radiology.radiologist',
        string="Radiologist",
        required=True,
        ondelete='cascade'
    )
    reviewer_id = fields.Many2one(
        'res.users',
        string="Évalué par",
        required=True,
        default=lambda self: self.env.user,
    )
    hospital_id = fields.Many2one(
        'radiology.hospital',
        string="Hôpital",
        required=True,
    )

    score = fields.Selection(
        [('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')],
        string="Note sur 5",
        required=True
    )

    comment = fields.Text("Commentaire")
    date = fields.Datetime("Date", default=fields.Datetime.now)

    @api.model
    def create(self, vals):
        """Vérifie que seul un hôpital peut donner une note."""
        user = self.env.user
        hospital = self.env['radiology.hospital'].search([('user_id', '=', user.id)], limit=1)

        if not hospital:
            raise exceptions.AccessError(_("Seuls les hôpitaux peuvent donner une note à un radiologue."))

        vals['hospital_id'] = hospital.id
        vals['reviewer_id'] = user.id

        return super().create(vals)
