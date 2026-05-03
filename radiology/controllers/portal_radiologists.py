# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class PortalRadiologistsController(http.Controller):

    def _get_hospital_of_user(self):
        return request.env["radiology.hospital"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1
        )

    @http.route('/my/radiologists/attachment/<int:radiologist_id>/<int:att_id>/view',
                type='http', auth='user', website=True)
    def view_radiologist_attachment(self, radiologist_id, att_id, **kw):
        Radiologist = request.env['radiology.radiologist'].sudo()
        r = Radiologist.browse(radiologist_id)
        if not r.exists():
            return request.not_found()

        att = request.env['ir.attachment'].sudo().browse(att_id)
        if not att.exists():
            return request.not_found()

        allowed_ids = set((r.diplome_ids | r.cv_attachment_ids).ids)
        if att.id not in allowed_ids:
            return request.not_found()

        mimetype = (att.mimetype or "").lower()
        allowed = mimetype.startswith("image/") or mimetype == "application/pdf"
        if not allowed:
            return request.not_found()

        filename = att.name or "document"
        headers = [
            ("Content-Type", att.mimetype or "application/octet-stream"),
            ("Content-Disposition", f'inline; filename="{filename}"'),
        ]
        return request.make_response(att.raw, headers=headers)

    @http.route(['/my/radiologists/<int:radiologist_id>'], type='http', auth='user', website=True)
    def portal_radiologist_profile(self, radiologist_id, **kw):
        Radiologist = request.env['radiology.radiologist'].sudo()
        r = Radiologist.browse(radiologist_id)
        if not r.exists():
            return request.not_found()
        hospital = self._get_hospital_of_user()


        Review = request.env['radiology.radiologist.review'].sudo()
        can_see = hospital.subscription_plan in ("premium", "pro")


        values = {
            'radiologist': r,
            'ratings': Review.search(
                [('radiologist_id', '=', r.id)],
                order='date desc, id desc'
            ),
            'diplomes': r.diplome_ids,
            'cvs': r.cv_attachment_ids,
            'availabilities': r.availability_ids.filtered(lambda a: a.active).sorted(
                key=lambda a: (a.weekday, a.start_time)
            ),
            "can_see": can_see,

        }
        return request.render('radiology.portal_radiologist_profile_modern', values)

    @http.route("/my/radiologists", type="http", auth="user", website=True)
    def portal_radiologists(self, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        fav_ids = set(hospital.favorite_radiologist_ids.ids)

        Radiologist = request.env["radiology.radiologist"].sudo()
        Specialty = request.env["radiology.specialty"].sudo()
        Brand = request.env["radiology.brand"].sudo()

        domain = []

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
        can_see = hospital.subscription_plan in ("premium", "pro")

        return request.render("radiology.portal_all_radiologists", {
            "radiologists": radiologists,
            "specialties": Specialty.search([]),
            "brands": Brand.search([]),
            "fav_ids": fav_ids,
            "can_see": can_see,

        })

    # ✅ JSON route (important: radiologist_id=None + **kw)
    @http.route("/my/radiologists/favorite/toggle", type="json", auth="user", website=True, csrf=True)
    def toggle_favorite_radiologist(self, radiologist_id=None, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return {"ok": False, "error": "Hospital not found"}

        try:
            rid = int(radiologist_id)
        except Exception:
            return {"ok": False, "error": "Invalid radiologist_id"}

        radiologist = request.env["radiology.radiologist"].sudo().browse(rid)
        if not radiologist.exists():
            return {"ok": False, "error": "Radiologist not found"}

        if rid in hospital.favorite_radiologist_ids.ids:
            hospital.write({"favorite_radiologist_ids": [(3, rid)]})
            return {"ok": True, "is_favorite": False}
        else:
            hospital.write({"favorite_radiologist_ids": [(4, rid)]})
            return {"ok": True, "is_favorite": True}
