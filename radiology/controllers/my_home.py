# -*- coding: utf-8 -*-
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request


class CustomerPortalInherit(CustomerPortal):

    def home(self, **kw):
        values = self._prepare_portal_layout_values()

        hospital = request.env["radiology.hospital"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1,
        )

        Mission = request.env["radiology.mission"].sudo()
        Application = request.env["radiology.application"].sudo()
        Notification = request.env["radiology.notification"].sudo()

        domain_hospital = [("hospital_id", "=", hospital.id)] if hospital else [("id", "=", 0)]

        total_missions = Mission.search_count(domain_hospital)
        published_count = Mission.search_count(domain_hospital + [("status", "=", "published")])
        assigned_count = Mission.search_count(domain_hospital + [("status", "=", "assigned")])
        done_count = Mission.search_count(domain_hospital + [("status", "=", "done")])
        active_count = published_count + assigned_count
        favorites_count = len(hospital.favorite_radiologist_ids.ids) if hospital else 0
        applications_count = Application.search_count([("mission_id.hospital_id", "=", hospital.id)]) if hospital else 0
        unread_notifications_count = Notification.search_count(
            [("hospital_id", "=", hospital.id), ("is_read", "=", False)]
        ) if hospital else 0
        recent_missions = Mission.search(domain_hospital, order="create_date desc, id desc", limit=3)
        recent_notifications = Notification.search(
            [("hospital_id", "=", hospital.id)] if hospital else [("id", "=", 0)],
            order="is_read asc, create_date desc, id desc",
            limit=4,
        )

        profile_percent = 0
        if hospital:
            filled = 0
            total_fields = 5
            if hospital.name:
                filled += 1
            if hospital.city:
                filled += 1
            if hospital.email:
                filled += 1
            if hospital.phone:
                filled += 1
            if hospital.image_1920:
                filled += 1
            profile_percent = int((filled / total_fields) * 100) if total_fields else 0

        values.update({
            "hospital": hospital,
            "total_missions": total_missions,
            "published_count": published_count,
            "assigned_count": assigned_count,
            "done_count": done_count,
            "active_count": active_count,
            "favorites_count": favorites_count,
            "applications_count": applications_count,
            "unread_notifications_count": unread_notifications_count,
            "recent_missions": recent_missions,
            "recent_notifications": recent_notifications,
            "profile_percent": profile_percent,
        })

        return request.render("radiology.portal_my_home_custom", values)

