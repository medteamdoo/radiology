# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class PortalMissionsController(http.Controller):

    def _get_recommended_radiologists(self, mission, limit=2):
        Radiologist = request.env["radiology.radiologist"].sudo()

        domain = []
        if mission.speciality_ids:
            domain.append(("specialty_ids", "in", mission.speciality_ids.ids))
        if mission.brand_ids:
            domain.append(("brand_ids", "in", mission.brand_ids.ids))

        radiologists = Radiologist.search(domain)

        scored = []
        for r in radiologists:
            score = 0

            # Matching spécialités (poids fort)
            score += len(set(r.specialty_ids.ids) & set(mission.speciality_ids.ids)) * 3

            # Matching marques
            score += len(set(r.brand_ids.ids) & set(mission.brand_ids.ids)) * 2

            # Expérience
            score += (r.experience_years or 0)

            # Note moyenne
            score += int((r.rating_avg or 0) * 2)

            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    @http.route("/my/missions", type="http", auth="user", website=True)
    def portal_all_missions(self, **kw):
        # 1) Vérifier que l'utilisateur connecté est bien un hôpital
        hospital = request.env["radiology.hospital"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1
        )
        if not hospital:
            return request.redirect("/my")

        Mission = request.env["radiology.mission"].sudo()
        Specialty = request.env["radiology.specialty"].sudo()
        Brand = request.env["radiology.brand"].sudo()

        # 2) Domain : missions publiées uniquement
        domain = [("status", "=", "published")]

        # 3) Filtres depuis GET
        specialty_id = kw.get("specialty_id")
        brand_id = kw.get("brand_id")
        date_from = kw.get("date_from")
        date_to = kw.get("date_to")

        if specialty_id:
            try:
                domain.append(("speciality_ids", "in", [int(specialty_id)]))
            except Exception:
                pass

        if brand_id:
            try:
                domain.append(("brand_ids", "in", [int(brand_id)]))
            except Exception:
                pass

        # Filtre dates (simple)
        if date_from:
            domain.append(("start_date", ">=", date_from))
        if date_to:
            domain.append(("end_date", "<=", date_to))

        missions = Mission.search(domain, order="start_date asc, create_date desc", limit=80)

        recommend = kw.get("recommend")
        mission_id = kw.get("mission_id")

        recommended_radiologists = []
        show_recommend_modal = False

        if recommend and mission_id:
            try:
                mission = Mission.browse(int(mission_id))
                if mission.exists():
                    recommended_radiologists = self._get_recommended_radiologists(mission)
                    show_recommend_modal = True
            except Exception:
                pass

        return request.render("radiology.portal_all_missions", {
            "missions": missions,
            "specialties": Specialty.search([]),
            "brands": Brand.search([]),
            "recommended_radiologists": recommended_radiologists,
            "show_recommend_modal": show_recommend_modal,
        })

    def _get_hospital_of_user(self):
        return request.env["radiology.hospital"].sudo().search(
            [("user_id", "=", request.env.user.id)], limit=1)

    @http.route("/my/missions/<int:mission_id>", type="http", auth="user", website=True)
    def portal_mission_details(self, mission_id, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        Mission = request.env["radiology.mission"].sudo()
        mission = Mission.browse(mission_id)
        if not mission.exists():
            return request.not_found()

        # (Optionnel) si tu veux limiter: seulement missions publiées
        # if mission.status != "published":
        #     return request.not_found()

        return request.render("radiology.portal_mission_details_modern", {
            "mission": mission,
            "hospital": mission.hospital_id,
        })