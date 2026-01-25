# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import re

EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

class HospitalSignupController(http.Controller):

    @http.route("/hospital/signup", type="http", auth="public", website=True, methods=["GET"])
    def hospital_signup_form(self, **kw):
        return request.render("radiology.hospital_signup_form", {
            "error": kw.get("error"),
            "values": kw,
        })

    @http.route("/hospital/signup", type="http", auth="public", website=True, methods=["POST"], csrf=True)
    def hospital_signup_submit(self, **post):
        name = (post.get("name") or "").strip()
        email = (post.get("email") or "").strip().lower().replace(" ", "")
        phone = (post.get("phone") or "").strip()
        city = (post.get("city") or "").strip()
        password = post.get("password") or ""
        password2 = post.get("password2") or ""

        if not name:
            return self._error("Veuillez saisir le nom de l’établissement.", post)
        if not email or not EMAIL_RE.match(email):
            return self._error("Veuillez saisir un email valide.", post)
        if len(password) < 8:
            return self._error("Le mot de passe doit contenir au moins 8 caractères.", post)
        if password != password2:
            return self._error("Les mots de passe ne correspondent pas.", post)

        Users = request.env["res.users"].sudo()
        Hospitals = request.env["radiology.hospital"].sudo()

        if Users.search([("login", "=", email)], limit=1):
            return self._error("Un compte existe déjà avec cet email. Connectez-vous.", post)

        if Hospitals.search([("email", "=", email)], limit=1):
            return self._error("Un établissement existe déjà avec cet email.", post)

        portal_group = request.env.ref("base.group_portal")

        user = Users.create({
            "name": name,
            "login": email,
            "email": email,
            "active": True,
            "groups_id": [(6, 0, [portal_group.id])],
        })
        user.write({"password": password, "share": True})

        Hospitals.create({
            "name": name,
            "email": email,
            "phone": phone,
            "city": city,
            "user_id": user.id,
        })

        return request.redirect("/web/login?redirect=/my")

    def _error(self, message, values):
        values = dict(values or {})
        values["error"] = message
        print(message)
        return request.redirect_query("/hospital/signup", values)
