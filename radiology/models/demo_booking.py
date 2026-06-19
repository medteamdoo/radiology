from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RadiologyDemoBooking(models.Model):
    _name = "radiology.demo.booking"
    _description = "Demo Booking"
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    slot_id = fields.Many2one(
        "radiology.demo.slot",
        required=True,
        ondelete="restrict",
        string="Demo Slot",
    )
    partner_name = fields.Char(required=True, string="Full Name")
    email = fields.Char(required=True)
    phone = fields.Char(required=True)
    additional_info = fields.Text(string="Additional Information")
    booked_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    state = fields.Selection(
        [
            ("booked", "Booked"),
            ("cancelled", "Cancelled"),
        ],
        default="booked",
        required=True,
    )

    _sql_constraints = [
        ("unique_slot_booking", "unique(slot_id)", "This demo slot is already booked."),
    ]

    @api.depends("partner_name", "slot_id")
    def _compute_name(self):
        for rec in self:
            slot_name = rec.slot_id.name or "slot"
            rec.name = "%s - %s" % (rec.partner_name or "Booking", slot_name)

    @api.constrains("slot_id", "state")
    def _check_slot_state(self):
        for rec in self.filtered(lambda booking: booking.state == "booked"):
            if rec.slot_id.state != "available":
                raise ValidationError("Only available demo slots can be booked.")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("slot_id").write({"state": "booked"})
        records._send_admin_notification_email()
        return records

    def write(self, vals):
        previous_states = {rec.id: rec.state for rec in self}
        result = super().write(vals)
        for rec in self:
            if vals.get("state") == "cancelled" and previous_states.get(rec.id) != "cancelled":
                rec.slot_id.write({"state": "available"})
            elif vals.get("state") == "booked":
                rec.slot_id.write({"state": "booked"})
        return result

    def unlink(self):
        slots = self.mapped("slot_id")
        result = super().unlink()
        slots.write({"state": "available"})
        return result

    def _get_admin_notification_email(self):
        self.ensure_one()
        return (
            self.env["ir.config_parameter"].sudo().get_param("radiology.demo_admin_email")
            or self.env.company.email
            or self.env.user.email
            or ""
        )

    def _send_admin_notification_email(self):
        template = self.env.ref("radiology.mail_template_demo_booking_admin", raise_if_not_found=False)
        if not template:
            return
        for rec in self:
            if not rec._get_admin_notification_email():
                continue
            template.send_mail(rec.id, force_send=True)
