from odoo import models, fields, api

class RadiologyRadiologistReview(models.Model):
    _name = "radiology.radiologist.review"
    _description = "Radiologist Review"
    _order = "date desc"

    radiologist_id = fields.Many2one(
        'radiology.radiologist',
        string="Radiologist",
        required=True,
        ondelete='cascade'
    )

    hospital_id = fields.Many2one(
        'radiology.hospital',
        string="Hôpital",
        required=True,
    )

    punctuality = fields.Selection(
        [('1','1'),('2','2'),('3','3'),('4','4'),('5','5')],
        string="Ponctualité",
        required=True
    )
    human_relation = fields.Selection(
        [('1','1'),('2','2'),('3','3'),('4','4'),('5','5')],
        string="Relation humaine",
        required=True
    )
    competence = fields.Selection(
        [('1','1'),('2','2'),('3','3'),('4','4'),('5','5')],
        string="Compétence",
        required=True
    )

    score_avg = fields.Float(
        string="Note moyenne",
        compute="_compute_score_avg",
        store=True,
        readonly=True
    )

    comment = fields.Text("Commentaire")
    date = fields.Datetime("Date", default=fields.Datetime.now)

    @api.depends('punctuality', 'human_relation', 'competence')
    def _compute_score_avg(self):
        for rec in self:
            if rec.punctuality and rec.human_relation and rec.competence:
                rec.score_avg = (float(rec.punctuality) + float(rec.human_relation) + float(rec.competence)) / 3.0
            else:
                rec.score_avg = 0.0
