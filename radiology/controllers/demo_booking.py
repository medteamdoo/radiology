# -*- coding: utf-8 -*-
import re

from psycopg2 import IntegrityError

from odoo import fields, http
from odoo.exceptions import ValidationError
from odoo.http import request


EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


class DemoBookingController(http.Controller):

    @http.route("/reserve-demo", type="http", auth="public", website=True, methods=["GET"])
    def reserve_demo_form(self, **kw):
        values = dict(kw or {})
        selected_slot_id = self._safe_int(values.get("slot_id"))
        slots = request.env["radiology.demo.slot"].sudo().search([
            ("active", "=", True),
            ("state", "=", "available"),
            ("end_datetime", ">", fields.Datetime.now()),
        ], order="start_datetime asc")
        return request.render("radiology.reserve_demo_form", {
            "error": values.get("error"),
            "success": values.get("success"),
            "values": values,
            "selected_slot_id": selected_slot_id,
            "slots": [self._prepare_slot_display(slot) for slot in slots],
        })

    @http.route("/reserve-demo", type="http", auth="public", website=True, methods=["POST"], csrf=True)
    def reserve_demo_submit(self, **post):
        name = (post.get("name") or "").strip()
        email = (post.get("email") or "").strip().lower()
        phone = (post.get("phone") or "").strip()
        slot_id = self._safe_int(post.get("slot_id"))

        if not name:
            return self._redirect_with_message("Veuillez saisir votre nom.", post, is_error=True)
        if not email or not EMAIL_RE.match(email):
            return self._redirect_with_message("Veuillez saisir un email valide.", post, is_error=True)
        if not phone:
            return self._redirect_with_message("Veuillez saisir votre numero de telephone.", post, is_error=True)
        if not slot_id:
            return self._redirect_with_message("Veuillez choisir un creneau.", post, is_error=True)

        slot = request.env["radiology.demo.slot"].sudo().search([
            ("id", "=", slot_id),
            ("active", "=", True),
            ("state", "=", "available"),
            ("end_datetime", ">", fields.Datetime.now()),
        ], limit=1)
        if not slot:
            return self._redirect_with_message(
                "Ce creneau n'est plus disponible. Veuillez en choisir un autre.",
                post,
                is_error=True,
            )

        try:
            with request.env.cr.savepoint():
                request.env["radiology.demo.booking"].sudo().create({
                    "slot_id": slot.id,
                    "partner_name": name,
                    "email": email,
                    "phone": phone,
                })
        except (IntegrityError, ValidationError):
            return self._redirect_with_message(
                "Ce creneau vient d'etre reserve par un autre utilisateur. Veuillez en choisir un autre.",
                post,
                is_error=True,
            )

        values = {
            "success": "Votre demo est reservee. Ce creneau n'apparaitra plus sur la plateforme.",
        }
        return request.redirect_query("/reserve-demo", values)

    def _redirect_with_message(self, message, values, is_error=False):
        payload = dict(values or {})
        payload["error" if is_error else "success"] = message
        return request.redirect_query("/reserve-demo", payload)

    def _prepare_slot_display(self, slot):
        start_local = fields.Datetime.context_timestamp(request.env.user, slot.start_datetime)
        end_local = fields.Datetime.context_timestamp(request.env.user, slot.end_datetime)
        return {
            "id": slot.id,
            "date_label": start_local.strftime("%d/%m/%Y"),
            "time_label": "%s - %s" % (start_local.strftime("%H:%M"), end_local.strftime("%H:%M")),
            "full_label": "%s | %s - %s" % (
                start_local.strftime("%d/%m/%Y"),
                start_local.strftime("%H:%M"),
                end_local.strftime("%H:%M"),
            ),
        }

    def _safe_int(self, value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
