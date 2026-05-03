# -*- coding: utf-8 -*-
import json
import logging
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class PortalMissionsController(http.Controller):

    def _send_push_notification(self, *, tokens, title, body, data=None):
        tokens = [token for token in (tokens or []) if token]
        if not tokens:
            _logger.info("Mission assignment push skipped: no active FCM tokens")
            return False

        params = request.env["ir.config_parameter"].sudo()
        push_url = (params.get_param("radiology.firebase_push_url") or "").strip()
        push_secret = (params.get_param("radiology.firebase_push_secret") or "").strip()
        if not push_url:
            _logger.info("Mission assignment push skipped: missing radiology.firebase_push_url")
            return False

        payload = {
            "secret": push_secret,
            "tokens": tokens,
            "title": title,
            "body": body,
            "data": data or {},
        }

        try:
            req = urllib_request.Request(
                push_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=10) as response:
                status = getattr(response, "status", 200)
                if 200 <= status < 300:
                    _logger.info(
                        "Mission assignment push sent to %s device(s) for mission %s",
                        len(tokens),
                        data.get("mission_id") if isinstance(data, dict) else "?",
                    )
                    return True
                _logger.warning("Mission assignment push returned status %s", status)
        except (HTTPError, URLError, TimeoutError) as exc:
            _logger.warning("Mission assignment push failed: %s", str(exc))
        except Exception as exc:
            _logger.exception("Unexpected mission assignment push error: %s", str(exc))
        return False

    def _notify_radiologist_assignment(self, mission, application):
        radiologist = application.radiologist_id
        if not radiologist:
            return False

        devices = request.env["radiology.mobile.device"].sudo().search([
            ("radiologist_id", "=", radiologist.id),
            ("is_active", "=", True),
        ])

        return self._send_push_notification(
            tokens=devices.mapped("fcm_token"),
            title="Mission affectee",
            body=f"Vous avez ete affecte a la mission {mission.name or 'sans titre'}.",
            data={
                "type": "mission_assignment",
                "mission_id": str(mission.id),
            },
        )

    def _get_recommended_radiologists(self, mission, limit=3):
        Radiologist = request.env["radiology.radiologist"].sudo()

        domain = []

        has_specialty = bool(mission.speciality_ids)
        has_brand = bool(mission.brand_ids)

        if has_specialty and has_brand:
            domain = [
                "|",
                ("specialty_ids", "in", mission.speciality_ids.ids),
                ("brand_ids", "in", mission.brand_ids.ids),
            ]
        elif has_specialty:
            domain = [("specialty_ids", "in", mission.speciality_ids.ids)]
        elif has_brand:
            domain = [("brand_ids", "in", mission.brand_ids.ids)]
        # else: domain vide → tous les radiologues

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

        # ✅ mission "à moi" ?
        is_owner = (mission.hospital_id.id == hospital.id)

        visible_application_ids = mission.application_ids if is_owner else request.env["radiology.application"].sudo().browse([])

        # ✅ candidatures ?
        has_apps = bool(visible_application_ids)

        # ✅ droit d'affecter (tu peux ajuster les statuts autorisés)
        can_assign = is_owner and has_apps and mission.status in ["published"]

        return request.render("radiology.portal_mission_details_modern", {
            "mission": mission,
            "hospital": mission.hospital_id,
            "is_owner": is_owner,
            "visible_application_ids": visible_application_ids,
            "can_assign": can_assign,
        })

    @http.route("/my/missions/<int:mission_id>/print", type="http", auth="user", website=True)
    def portal_mission_print_pdf(self, mission_id, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        mission = request.env["radiology.mission"].sudo().browse(mission_id)
        if not mission.exists():
            return request.not_found()

        # sécurité (choisis la règle)
        if mission.status != "published":
            return request.not_found()
        # ou bien seulement les missions de cet hôpital:
        # if mission.hospital_id.id != hospital.id:
        #     return request.not_found()

        report_xmlid = "radiology.report_mission_pdf"

        pdf_content, _ = request.env["ir.actions.report"] \
            .with_context(lang=request.env.user.lang or request.env.lang) \
            .sudo() \
            ._render_qweb_pdf(report_xmlid, mission.id)

        filename = f"Mission_{mission.id}.pdf"
        return request.make_response(
            pdf_content,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Length", str(len(pdf_content))),
                ("Content-Disposition", f'inline; filename="{filename}"'),
            ],
        )

    @http.route(
        "/my/missions/<int:mission_id>/assign",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True
    )
    def portal_assign_mission(self, mission_id, application_id=None, message=None, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        Mission = request.env["radiology.mission"].sudo()
        Application = request.env["radiology.application"].sudo()

        mission = Mission.browse(mission_id)
        if not mission.exists():
            return request.not_found()

        # ✅ sécurité: mission appartient à l'hôpital connecté
        if mission.hospital_id.id != hospital.id:
            return request.redirect("/my/missions/%s" % mission.id)

        # ✅ لازم يكون عندها candidatures
        if not mission.application_ids:
            return request.redirect("/my/missions/%s" % mission.id)

        # ✅ application_id obligatoire
        if not application_id:
            return request.redirect("/my/missions/%s" % mission.id)

        # ✅ vérifier que l'application appartient à la mission
        app = Application.browse(int(application_id))
        if (not app.exists()) or (app.mission_id.id != mission.id):
            return request.redirect("/my/missions/%s" % mission.id)

        # ✅ effectuer l'affectation
        mission.write({
            "status": "assigned",
            "assigned_radiologist_id": app.radiologist_id.id,
        })

        # ✅ mettre à jour les statuts des candidatures (conseillé)
        # - celle choisie : accepted
        # - les autres : rejected
        mission.application_ids.write({"status": "rejected"})
        app.write({"status": "accepted"})
        self._notify_radiologist_assignment(mission, app)

        # (optionnel) tu peux exploiter "message" plus tard (mail.message, notification, etc.)

        return request.redirect("/my/missions/%s" % mission.id)

    @http.route("/my/missions/<int:mission_id>/done", type="http", auth="user",
                website=True, methods=["POST"], csrf=True)
    def portal_done_mission(self, mission_id, punctuality=None, human_relation=None, competence=None, comment=None,
                            **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        Mission = request.env["radiology.mission"].sudo()
        Review = request.env["radiology.radiologist.review"].sudo()

        mission = Mission.browse(mission_id)
        if not mission.exists():
            return request.not_found()

        # sécurité : mission appartient à moi
        if mission.hospital_id.id != hospital.id:
            return request.redirect("/my/missions/%s" % mission.id)

        # فقط إذا assigned
        if mission.status == "assigned":
            mission.write({"status": "done"})

        # ✅ create review ONLY if all 3 are filled
        if mission.assigned_radiologist_id and punctuality and human_relation and competence:
            Review.create({
                "radiologist_id": mission.assigned_radiologist_id.id,
                "hospital_id": hospital.id,
                "punctuality": str(punctuality),
                "human_relation": str(human_relation),
                "competence": str(competence),
                "comment": comment or "",
            })

        return request.redirect("/my/missions/%s" % mission.id)
