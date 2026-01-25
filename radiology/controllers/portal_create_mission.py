# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class PortalMissionCreateController(http.Controller):

    def _get_hospital_of_user(self):
        return request.env["radiology.hospital"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1
        )

    @http.route("/my/missions/new", type="http", auth="user", website=True, methods=["GET"])
    def mission_new_form(self, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        Specialty = request.env["radiology.specialty"].sudo()
        Brand = request.env["radiology.brand"].sudo()

        return request.render("radiology.portal_mission_new", {
            "error": kw.get("error"),
            "values": kw,  # pour re-remplir en cas d'erreur
            "specialties": Specialty.search([]),
            "brands": Brand.search([]),
        })

    @http.route("/my/missions/new", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def mission_new_submit(self, **post):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        # Champs
        name = (post.get("name") or "").strip()
        description = (post.get("description") or "").strip()
        tarif = post.get("tarif") or ""
        start_date = post.get("start_date") or False
        end_date = post.get("end_date") or False
        publish_now = (post.get("publish_now") == "on")

        specialty_ids = post.get("specialty_ids") or []
        brand_ids = post.get("brand_ids") or []

        # multi-select: parfois string si un seul, liste si plusieurs
        if isinstance(specialty_ids, str):
            specialty_ids = [specialty_ids]
        if isinstance(brand_ids, str):
            brand_ids = [brand_ids]

        # Validations
        if not name:
            return self._error_new("Veuillez saisir le nom de la mission.", post)

        # tarif float
        tarif_val = 0.0
        if tarif:
            try:
                tarif_val = float(str(tarif).replace(",", "."))
            except Exception:
                return self._error_new("Tarif invalide. Exemple : 35 ou 35.5", post)

        if start_date and end_date and start_date > end_date:
            return self._error_new("La date de début doit être avant la date de fin.", post)

        # Convert ids
        try:
            specialty_ids_int = [int(x) for x in specialty_ids if x]
            brand_ids_int = [int(x) for x in brand_ids if x]
        except Exception:
            return self._error_new("Sélection invalide (spécialité / marque).", post)

        Mission = request.env["radiology.mission"].sudo()

        mission = Mission.create({
            "name": name,
            "hospital_id": hospital.id,
            "description": description,
            "tarif": tarif_val,
            "start_date": start_date or False,
            "end_date": end_date or False,
            "speciality_ids": [(6, 0, specialty_ids_int)],
            "brand_ids": [(6, 0, brand_ids_int)],
            "status": "published" if publish_now else "draft",
        })

        # Rediriger vers "Mes missions" (on le fera après) ou vers toutes les missions
        return request.redirect(
            "/my/missions?created=1&recommend=1&mission_id=%s" % mission.id
        )
    def _error_new(self, message, values):
        values = dict(values or {})
        values["error"] = message
        return request.redirect_query("/my/missions/new", values)
