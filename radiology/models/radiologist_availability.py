from odoo import api, fields, models
from odoo.exceptions import ValidationError

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

    @api.constrains('start_time', 'end_time', 'is_night')
    def _check_time_range(self):
        for rec in self:
            if rec.start_time is None or rec.end_time is None:
                continue

            if rec.start_time < 0 or rec.start_time >= 24:
                raise ValidationError("L'heure de debut doit etre comprise entre 0 et 24.")
            if rec.end_time < 0 or rec.end_time > 24:
                raise ValidationError("L'heure de fin doit etre comprise entre 0 et 24.")
            if rec.start_time == rec.end_time:
                raise ValidationError("L'heure de debut et l'heure de fin ne peuvent pas etre identiques.")
            if not rec.is_night and rec.end_time < rec.start_time:
                raise ValidationError(
                    "Un creneau de jour doit se terminer apres son heure de debut."
                )

    @api.constrains('radiologist_id', 'weekday', 'start_time', 'end_time', 'is_night', 'active')
    def _check_overlap_for_active_slots(self):
        for rec in self.filtered(lambda slot: slot.active and slot.radiologist_id and slot.weekday is not None):
            siblings = rec.radiologist_id.availability_ids.filtered(
                lambda slot: (
                    slot.id != rec.id
                    and slot.active
                    and slot.weekday == rec.weekday
                )
            )
            for sibling in siblings:
                if self._ranges_overlap(
                    rec.start_time,
                    rec.end_time,
                    rec.is_night,
                    sibling.start_time,
                    sibling.end_time,
                    sibling.is_night,
                ):
                    raise ValidationError(
                        "Deux creneaux actifs se chevauchent pour ce radiologue sur le meme jour."
                    )

    def _compute_is_weekend(self):
        for rec in self:
            rec.is_weekend = rec.weekday in ('5', '6')

    @staticmethod
    def _expand_range(start_time, end_time, is_night):
        if start_time is None or end_time is None:
            return []
        end_value = end_time
        if is_night and end_time <= start_time:
            end_value += 24
        return [(start_time, end_value)]

    @classmethod
    def _ranges_overlap(cls, start_a, end_a, night_a, start_b, end_b, night_b):
        ranges_a = cls._expand_range(start_a, end_a, night_a)
        ranges_b = cls._expand_range(start_b, end_b, night_b)
        for range_a_start, range_a_end in ranges_a:
            for range_b_start, range_b_end in ranges_b:
                if range_a_start < range_b_end and range_b_start < range_a_end:
                    return True
        return False
