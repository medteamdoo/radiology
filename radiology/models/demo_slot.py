from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RadiologyDemoSlot(models.Model):
    _name = "radiology.demo.slot"
    _description = "Demo Slot"
    _order = "start_datetime asc"

    name = fields.Char(
        string="Label",
        compute="_compute_name",
        store=True,
    )
    start_datetime = fields.Datetime(required=True, string="Start")
    end_datetime = fields.Datetime(required=True, string="End")
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [
            ("available", "Available"),
            ("booked", "Booked"),
            ("cancelled", "Cancelled"),
        ],
        default="available",
        required=True,
        string="Status",
    )
    booking_id = fields.One2many("radiology.demo.booking", "slot_id", string="Bookings")
    booking_count = fields.Integer(compute="_compute_booking_count", string="Bookings")

    @api.depends("start_datetime", "end_datetime")
    def _compute_name(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime:
                rec.name = "%s - %s" % (
                    fields.Datetime.to_string(rec.start_datetime),
                    fields.Datetime.to_string(rec.end_datetime),
                )
            else:
                rec.name = "New Slot"

    @api.depends("booking_id")
    def _compute_booking_count(self):
        for rec in self:
            rec.booking_count = len(rec.booking_id)

    @api.constrains("start_datetime", "end_datetime")
    def _check_datetimes(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime and rec.end_datetime <= rec.start_datetime:
                raise ValidationError("The end date must be after the start date.")

    @api.constrains("start_datetime", "end_datetime", "state", "active")
    def _check_overlap(self):
        for rec in self.filtered(lambda slot: slot.active and slot.state != "cancelled"):
            overlapping = self.search([
                ("id", "!=", rec.id),
                ("active", "=", True),
                ("state", "!=", "cancelled"),
                ("start_datetime", "<", rec.end_datetime),
                ("end_datetime", ">", rec.start_datetime),
            ], limit=1)
            if overlapping:
                raise ValidationError("This demo slot overlaps with another active slot.")

