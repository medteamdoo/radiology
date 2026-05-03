# controllers/portal_favorites.py
# -*- coding: utf-8 -*-
from datetime import date

from odoo import http
from odoo.http import request

class PortalFavoritesController(http.Controller):

    def _get_hospital_of_user(self):
        return request.env["radiology.hospital"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1
        )

    @http.route("/my/favorites", type="http", auth="user", website=True, sitemap=False)
    def portal_favorite_radiologists(self, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        fav_ids = hospital.favorite_radiologist_ids.ids

        Radiologist = request.env["radiology.radiologist"].sudo()
        Specialty = request.env["radiology.specialty"].sudo()
        Brand = request.env["radiology.brand"].sudo()

        domain = [("id", "in", fav_ids)] if fav_ids else [("id", "=", 0)]

        specialty_id = kw.get("specialty_id")
        brand_id = kw.get("brand_id")

        if specialty_id:
            try:
                domain.append(("specialty_ids", "in", [int(specialty_id)]))
            except Exception:
                pass

        if brand_id:
            try:
                domain.append(("brand_ids", "in", [int(brand_id)]))
            except Exception:
                pass

        radiologists = Radiologist.search(
            domain,
            order="rating_avg desc, experience_years desc, display_name asc",
            limit=80
        )

        return request.render("radiology.portal_favorite_radiologists", {
            "radiologists": radiologists,
            "specialties": Specialty.search([]),
            "brands": Brand.search([]),
            "fav_ids": set(fav_ids),
            "page_name": "favorites",
        })

    @http.route("/my/missionss", type="http", auth="user", website=True, sitemap=False)
    def my_missions(self, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        Mission = request.env["radiology.mission"].sudo()
        Specialty = request.env["radiology.specialty"].sudo()
        Brand = request.env["radiology.brand"].sudo()

        # filters
        specialty_id = (kw.get("specialty_id") or "").strip()
        brand_id = (kw.get("brand_id") or "").strip()
        date_from = (kw.get("date_from") or "").strip()
        date_to = (kw.get("date_to") or "").strip()
        base_domain = [("hospital_id", "=", hospital.id)]

        if specialty_id:
            try:
                base_domain.append(("speciality_ids", "in", [int(specialty_id)]))
            except Exception:
                pass

        if brand_id:
            try:
                base_domain.append(("brand_ids", "in", [int(brand_id)]))
            except Exception:
                pass

        # dates (Mission.start_date/end_date are Date)
        # overlap logic: (start_date <= date_to) AND (end_date >= date_from)
        if date_from:
            base_domain.append(("end_date", ">=", date_from))
        if date_to:
            base_domain.append(("start_date", "<=", date_to))

        order = "create_date desc, id desc"

        missions_draft = Mission.search(base_domain + [("status", "=", "draft")], order=order)
        missions_published = Mission.search(base_domain + [("status", "=", "published")], order=order)
        mission_assigned = Mission.search(base_domain + [("status", "=", "assigned")], order=order)
        missions_done = Mission.search(base_domain + [("status", "=", "done")], order=order)

        return request.render("radiology.portal_my_missions_grouped", {
            "specialties": Specialty.search([]),
            "brands": Brand.search([]),

            "missions_draft": missions_draft,
            "missions_published": missions_published,
            "missions_assigned": mission_assigned,
            "missions_done": missions_done,

            "selected_specialty": specialty_id,
            "selected_brand": brand_id,
            "date_from": date_from,
            "date_to": date_to,

            "page_name": "my_missions",
        })

    @http.route("/my/missions/<int:mission_id>/delete", type="http", auth="user", website=True, methods=["POST"],
                csrf=True)
    def delete_mission(self, mission_id, **post):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        Mission = request.env["radiology.mission"].sudo()
        mission = Mission.browse(mission_id)

        if not mission.exists() or mission.hospital_id.id != hospital.id:
            return request.not_found()

        # optionnel: empêcher delete si published/done
        # if mission.status != "draft":
        #     return request.redirect("/my/missions?error=not_allowed")

        mission.unlink()
        return request.redirect("/my/missions")

    @http.route("/my/dashboard", type="http", auth="user", website=True, sitemap=False)
    def portal_hospital_dashboard(self, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        Mission = request.env["radiology.mission"].sudo()
        Radiologist = request.env["radiology.radiologist"].sudo()

        today = date.today()

        # KPI counts
        domain_hospital = [("hospital_id", "=", hospital.id)]

        total_missions = Mission.search_count(domain_hospital)
        draft_count = Mission.search_count(domain_hospital + [("status", "=", "draft")])
        published_count = Mission.search_count(domain_hospital + [("status", "=", "published")])
        assigned_count = Mission.search_count(domain_hospital + [("status", "=", "assigned")])
        done_count = Mission.search_count(domain_hospital + [("status", "=", "done")])

        # (optionnel) missions actives
        active_count = published_count + assigned_count

        fav_ids = hospital.favorite_radiologist_ids.ids
        favorites_count = len(fav_ids)

        # Recent missions (tous statuts)
        recent_missions = Mission.search(
            domain_hospital,
            order="create_date desc, id desc",
            limit=8
        )

        # Upcoming missions (start_date >= today) + statuts utiles
        # -> published + assigned (et tu peux ajouter "draft" si tu veux)
        upcoming_missions = Mission.search(
            domain_hospital + [
                ("start_date", "!=", False),
                ("start_date", ">=", today),
                ("status", "in", ["published", "assigned"]),
            ],
            order="start_date asc, id desc",
            limit=6
        )

        # Favorites preview
        favorite_radiologists = Radiologist.browse(fav_ids) if fav_ids else Radiologist.browse([])
        favorite_radiologists = favorite_radiologists[:6]

        # Profile completeness (simple)
        filled = 0
        total_fields = 5
        if hospital.name: filled += 1
        if hospital.city: filled += 1
        if hospital.email: filled += 1
        if hospital.phone: filled += 1
        if hospital.image_1920: filled += 1
        profile_percent = int((filled / total_fields) * 100) if total_fields else 0

        values = {
            "hospital": hospital,
            "today": today,

            "total_missions": total_missions,
            "draft_count": draft_count,
            "published_count": published_count,
            "assigned_count": assigned_count,
            "done_count": done_count,
            "active_count": active_count,  # optionnel

            "favorites_count": favorites_count,

            "recent_missions": recent_missions,
            "upcoming_missions": upcoming_missions,
            "favorite_radiologists": favorite_radiologists,

            "profile_percent": profile_percent,
            "page_name": "dashboard",
        }
        return request.render("radiology.portal_hospital_dashboard", values)