# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class RadioVacWebsiteController(http.Controller):

    @http.route("/radiovac-home", type="http", auth="public", website=True, sitemap=True)
    def radiovac_homepage(self, **kw):
        return request.render("radiology.radiovac_website_homepage")

    @http.route("/radiovac-pricing", type="http", auth="public", website=True, sitemap=True)
    def radiovac_pricing(self, **kw):
        return request.render("radiology.radiovac_website_pricing")
