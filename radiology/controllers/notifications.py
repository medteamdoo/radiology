# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class RadiologyNotificationController(http.Controller):

    @http.route(
        "/my/notifications/<int:notification_id>/read",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def mark_notification_as_read(self, notification_id, redirect=None, **kw):
        hospital = request.env["radiology.hospital"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1,
        )
        if not hospital:
            return request.redirect("/my")

        notification = request.env["radiology.notification"].sudo().browse(notification_id)
        if not notification.exists() or notification.hospital_id.id != hospital.id:
            return request.not_found()

        notification.action_mark_as_read()

        target = redirect or notification.action_url or request.httprequest.referrer or "/my"
        return request.redirect(target)
