# controllers/portal_favorites.py
# -*- coding: utf-8 -*-
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from odoo import http
from odoo.http import request


class PortalFavoritesController(http.Controller):
    MISSION_STATUS_META = {
        "draft": {"label": "Brouillon", "css": "is-draft"},
        "published": {"label": "Publiee", "css": "is-published"},
        "assigned": {"label": "Affectee", "css": "is-assigned"},
        "done": {"label": "Terminee", "css": "is-done"},
    }

    APPLICATION_STATUS_META = {
        "pending": {"label": "En attente", "css": "is-application"},
        "accepted": {"label": "Acceptee", "css": "is-application-ok"},
        "rejected": {"label": "Refusee", "css": "is-application-muted"},
    }

    EVENT_TYPE_OPTIONS = [
        ("all", "Tous"),
        ("mission", "Missions"),
        ("availability", "Disponibilites"),
        ("application", "Candidatures"),
        ("deadline", "Echeances"),
    ]

    STATUS_FILTER_OPTIONS = [
        ("all", "Tous"),
        ("draft", "Brouillon"),
        ("published", "Publiee"),
        ("assigned", "Affectee"),
        ("done", "Terminee"),
        ("pending", "Candidature en attente"),
        ("accepted", "Candidature acceptee"),
        ("rejected", "Candidature refusee"),
    ]

    MONTH_NAMES = [
        "Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre",
    ]
    WEEKDAY_SHORT = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."]
    WEEKDAY_COMPACT = ["L", "M", "M", "J", "V", "S", "D"]
    WEEKDAY_FULL = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

    def _get_hospital_of_user(self):
        return request.env["radiology.hospital"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1
        )

    @staticmethod
    def _parse_date(raw_value, fallback):
        if not raw_value:
            return fallback
        try:
            return datetime.strptime(raw_value, "%Y-%m-%d").date()
        except Exception:
            return fallback

    @staticmethod
    def _float_to_hhmm(raw_value):
        if raw_value is None:
            return "--:--"
        hour = int(raw_value)
        minute = int(round((raw_value - hour) * 60))
        if minute == 60:
            hour += 1
            minute = 0
        return f"{hour % 24:02d}:{minute:02d}"

    @staticmethod
    def _shift_month(anchor_day, delta):
        month_index = anchor_day.month - 1 + delta
        target_year = anchor_day.year + (month_index // 12)
        target_month = (month_index % 12) + 1
        target_day = min(anchor_day.day, monthrange(target_year, target_month)[1])
        return date(target_year, target_month, target_day)

    @staticmethod
    def _safe_date_label(raw_date):
        return raw_date.strftime("%d/%m/%Y") if raw_date else "-"

    def _build_dashboard_url(self, base_params, **updates):
        params = dict(base_params or {})
        for key, value in updates.items():
            if value in (None, "", False):
                params.pop(key, None)
            else:
                params[key] = value

        if not params.get("my_only"):
            params.pop("my_only", None)

        clean = {}
        for key, value in params.items():
            if value in (None, "", False):
                continue
            if isinstance(value, bool):
                clean[key] = "1" if value else "0"
            else:
                clean[key] = str(value)

        return "/my/dashboard" + (f"?{urlencode(clean)}" if clean else "")

    def _build_mini_calendar(self, anchor_day, today_day, current_params):
        month_start = anchor_day.replace(day=1)
        grid_start = month_start - timedelta(days=month_start.weekday())
        weeks = []
        cursor = grid_start

        for _ in range(6):
            current_week = []
            for _ in range(7):
                current_week.append({
                    "number": cursor.day,
                    "iso": cursor.isoformat(),
                    "is_current_month": cursor.month == anchor_day.month,
                    "is_today": cursor == today_day,
                    "is_selected": cursor == anchor_day,
                    "url": self._build_dashboard_url(current_params, anchor=cursor.isoformat()),
                    "date_obj": cursor,
                })
                cursor += timedelta(days=1)
            weeks.append(current_week)

        return weeks

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

        mission.unlink()
        return request.redirect("/my/missions")

    @http.route("/my/dashboard", type="http", auth="user", website=True, sitemap=False)
    def portal_hospital_dashboard(self, **kw):
        hospital = self._get_hospital_of_user()
        if not hospital:
            return request.redirect("/my")

        Mission = request.env["radiology.mission"].sudo()
        Application = request.env["radiology.application"].sudo()
        Specialty = request.env["radiology.specialty"].sudo()
        Availability = request.env["radiology.radiologist.availability"].sudo()

        today_day = date.today()
        now_dt = datetime.now()

        view_mode = (kw.get("view") or "week").strip().lower()
        if view_mode not in {"day", "week", "month"}:
            view_mode = "week"

        selected_type = (kw.get("type") or "all").strip().lower()
        if selected_type not in {item[0] for item in self.EVENT_TYPE_OPTIONS}:
            selected_type = "all"

        selected_status = (kw.get("status") or "all").strip().lower()
        valid_statuses = {item[0] for item in self.STATUS_FILTER_OPTIONS}
        if selected_status not in valid_statuses:
            selected_status = "all"

        selected_specialty = (kw.get("specialty_id") or "").strip()
        selected_radiologist = (kw.get("radiologist_id") or "").strip()
        selected_my_only = (kw.get("my_only") or "1") in {"1", "true", "on", "yes"}

        anchor_day = self._parse_date(kw.get("anchor"), today_day)

        current_params = {
            "view": view_mode,
            "type": None if selected_type == "all" else selected_type,
            "status": None if selected_status == "all" else selected_status,
            "specialty_id": selected_specialty or None,
            "radiologist_id": selected_radiologist or None,
            "my_only": "1" if selected_my_only else None,
            "anchor": anchor_day.isoformat(),
        }

        specialty_id = int(selected_specialty) if selected_specialty.isdigit() else 0
        radiologist_id = int(selected_radiologist) if selected_radiologist.isdigit() else 0

        favorite_options = hospital.favorite_radiologist_ids.sorted(
            key=lambda r: ((r.display_name or "").lower(), r.id)
        )
        filtered_favorites = favorite_options

        if specialty_id:
            filtered_favorites = filtered_favorites.filtered(lambda r: specialty_id in r.specialty_ids.ids)

        if radiologist_id:
            filtered_favorites = filtered_favorites.filtered(lambda r: r.id == radiologist_id)

        favorite_ids = filtered_favorites.ids

        missions = Mission.search(
            [("hospital_id", "=", hospital.id)],
            order="start_date asc, create_date desc, id desc"
        )

        if specialty_id:
            missions = missions.filtered(lambda m: specialty_id in m.speciality_ids.ids)

        if radiologist_id:
            missions = missions.filtered(
                lambda m: (
                    m.assigned_radiologist_id.id == radiologist_id
                    or radiologist_id in m.application_ids.mapped("radiologist_id").ids
                )
            )

        if selected_status in self.MISSION_STATUS_META:
            missions = missions.filtered(lambda m: m.status == selected_status)

        applications = Application.search(
            [("mission_id.hospital_id", "=", hospital.id)],
            order="create_date desc, id desc"
        )

        if specialty_id:
            applications = applications.filtered(lambda a: specialty_id in a.mission_id.speciality_ids.ids)

        if radiologist_id:
            applications = applications.filtered(lambda a: a.radiologist_id.id == radiologist_id)

        if selected_status in self.APPLICATION_STATUS_META:
            applications = applications.filtered(lambda a: a.status == selected_status)

        availability_records = Availability.search(
            [("radiologist_id", "in", favorite_ids), ("active", "=", True)],
            order="weekday, start_time, id"
        ) if favorite_ids else Availability.browse([])

        week_start = anchor_day - timedelta(days=anchor_day.weekday())
        week_days = [week_start + timedelta(days=offset) for offset in range(7)]
        visible_days = [anchor_day] if view_mode == "day" else week_days
        month_start = anchor_day.replace(day=1)
        month_end = anchor_day.replace(day=monthrange(anchor_day.year, anchor_day.month)[1])
        mini_calendar_weeks = self._build_mini_calendar(anchor_day, today_day, current_params)
        month_grid_start = mini_calendar_weeks[0][0]["date_obj"]
        month_grid_end = mini_calendar_weeks[-1][-1]["date_obj"]

        visible_day_set = set(visible_days)
        month_grid_day_set = {
            month_grid_start + timedelta(days=offset)
            for offset in range((month_grid_end - month_grid_start).days + 1)
        }

        allow_mission_events = selected_type in {"all", "mission"} and selected_status in {"all", *self.MISSION_STATUS_META.keys()}
        allow_availability_events = selected_type in {"all", "availability"} and selected_status == "all"
        allow_application_events = selected_type in {"all", "application"} and selected_status in {"all", *self.APPLICATION_STATUS_META.keys()}
        allow_deadline_events = selected_type in {"all", "deadline"} and selected_status in {"all", *self.MISSION_STATUS_META.keys()}

        month_items = defaultdict(list)
        column_map = {}
        for visible_day in visible_days:
            column_map[visible_day] = {
                "date_obj": visible_day,
                "date_iso": visible_day.isoformat(),
                "day_label": self.WEEKDAY_SHORT[visible_day.weekday()],
                "day_short": self.WEEKDAY_COMPACT[visible_day.weekday()],
                "day_full": self.WEEKDAY_FULL[visible_day.weekday()],
                "day_number": visible_day.day,
                "is_today": visible_day == today_day,
                "is_selected": visible_day == anchor_day,
                "anchor_url": self._build_dashboard_url(current_params, anchor=visible_day.isoformat()),
                "all_day_items": [],
                "timed_items": [],
            }

        legend_seen = []

        def remember_legend(key):
            if key not in legend_seen:
                legend_seen.append(key)

        def add_month_item(target_day, item):
            if target_day in month_grid_day_set:
                month_items[target_day].append(item)

        def add_all_day_item(target_day, item):
            if target_day in visible_day_set:
                column_map[target_day]["all_day_items"].append(item)

        for mission in missions:
            mission_start = mission.start_date or mission.end_date
            mission_end = mission.end_date or mission.start_date or mission_start
            if not mission_start:
                continue

            status_meta = self.MISSION_STATUS_META.get(mission.status, self.MISSION_STATUS_META["draft"])
            mission_item = {
                "title": mission.name or "Mission",
                "meta": status_meta["label"],
                "css": status_meta["css"],
                "url": f"/my/missions/{mission.id}",
            }

            if allow_mission_events:
                current_day = mission_start
                while current_day and current_day <= mission_end:
                    add_all_day_item(current_day, dict(mission_item))
                    add_month_item(current_day, dict(mission_item))
                    current_day += timedelta(days=1)
                if mission_start <= anchor_day <= mission_end:
                    remember_legend(status_meta["css"])

            if allow_deadline_events and mission.end_date and mission.status != "done":
                deadline_item = {
                    "title": "Echeance mission",
                    "meta": mission.name or "Mission",
                    "css": "is-deadline",
                    "url": f"/my/missions/{mission.id}",
                }
                add_all_day_item(mission.end_date, dict(deadline_item))
                add_month_item(mission.end_date, dict(deadline_item))
                remember_legend("is-deadline")

        application_event_records = applications
        if selected_status == "all":
            application_event_records = applications.filtered(lambda app: app.status == "pending")

        if allow_application_events:
            for application in application_event_records:
                application_day = application.create_date.date() if application.create_date else None
                if not application_day:
                    continue
                meta = self.APPLICATION_STATUS_META.get(application.status, self.APPLICATION_STATUS_META["pending"])
                app_item = {
                    "title": application.radiologist_id.display_name or "Candidature",
                    "meta": application.mission_id.name or meta["label"],
                    "css": "is-application",
                    "url": f"/my/missions/{application.mission_id.id}",
                }
                add_all_day_item(application_day, dict(app_item))
                add_month_item(application_day, dict(app_item))
                remember_legend("is-application")

        availability_by_weekday = defaultdict(list)
        for availability in availability_records:
            try:
                availability_by_weekday[int(availability.weekday)].append(availability)
            except Exception:
                continue

        if allow_availability_events:
            total_hours = 10.0
            day_start = 8.0
            day_end = 18.0

            for visible_day in visible_days:
                day_slots = availability_by_weekday.get(visible_day.weekday(), [])
                day_events = []
                for availability in day_slots:
                    raw_start = availability.start_time or 0.0
                    raw_end = availability.end_time or 0.0
                    if availability.is_night and raw_end <= raw_start:
                        raw_end += 24.0

                    clipped_start = max(raw_start, day_start)
                    clipped_end = min(raw_end, day_end)
                    if clipped_end <= clipped_start:
                        continue

                    top_pct = ((clipped_start - day_start) / total_hours) * 100.0
                    height_pct = max(((clipped_end - clipped_start) / total_hours) * 100.0, 7.5)

                    day_events.append({
                        "title": f"Disponibilite - {availability.radiologist_id.display_name or 'Radiologue'}",
                        "meta": f"{self._float_to_hhmm(availability.start_time)} - {self._float_to_hhmm(availability.end_time)}",
                        "subtitle": ", ".join(availability.radiologist_id.specialty_ids[:2].mapped("name")) or "Favori RadioVac",
                        "css": "is-availability",
                        "sort": top_pct,
                        "style": f"top: {top_pct:.2f}%; height: {height_pct:.2f}%;",
                        "url": f"/my/radiologists/{availability.radiologist_id.id}",
                    })

                    if visible_day == anchor_day:
                        remember_legend("is-availability")

                day_events.sort(key=lambda item: item["sort"])
                column_map[visible_day]["timed_items"] = day_events

            current_cursor = month_grid_start
            while current_cursor <= month_grid_end:
                for availability in availability_by_weekday.get(current_cursor.weekday(), []):
                    add_month_item(current_cursor, {
                        "title": availability.radiologist_id.display_name or "Disponibilite",
                        "meta": f"{self._float_to_hhmm(availability.start_time)} - {self._float_to_hhmm(availability.end_time)}",
                        "css": "is-availability",
                        "url": f"/my/radiologists/{availability.radiologist_id.id}",
                    })
                current_cursor += timedelta(days=1)

        calendar_columns = []
        for visible_day in visible_days:
            bucket = column_map[visible_day]
            all_day_items = bucket["all_day_items"]
            timed_items = bucket["timed_items"]
            bucket["all_day_visible"] = all_day_items[:3]
            bucket["all_day_more"] = max(0, len(all_day_items) - 3)
            bucket["timed_items"] = timed_items
            calendar_columns.append(bucket)

        month_board_weeks = []
        for raw_week in mini_calendar_weeks:
            board_week = []
            for raw_day in raw_week:
                day_items = month_items.get(raw_day["date_obj"], [])
                board_week.append({
                    "number": raw_day["number"],
                    "iso": raw_day["iso"],
                    "is_current_month": raw_day["is_current_month"],
                    "is_today": raw_day["is_today"],
                    "is_selected": raw_day["is_selected"],
                    "url": raw_day["url"],
                    "items": day_items[:2],
                    "more": max(0, len(day_items) - 2),
                })
            month_board_weeks.append(board_week)

        stats_missions = [
            mission for mission in missions
            if mission.start_date and mission.start_date <= month_end
            and (mission.end_date or mission.start_date) >= month_start
            and mission.status in {"published", "assigned", "done"}
        ]
        available_favorite_ids = {
            availability.radiologist_id.id
            for availability in availability_records
        }
        pending_applications = applications.filtered(lambda app: app.status == "pending")
        upcoming_deadlines = [
            mission for mission in missions
            if mission.end_date and mission.end_date >= anchor_day and mission.status in {"draft", "published", "assigned"}
        ]
        upcoming_deadlines = sorted(upcoming_deadlines, key=lambda mission: mission.end_date)[:6]

        stats_cards = [
            {
                "label": "Missions prevues ce mois",
                "value": len(stats_missions),
                "note": "Chevauchements sur le mois actif",
                "icon": "fa-briefcase",
                "accent": "is-blue",
            },
            {
                "label": "Favoris disponibles",
                "value": len(available_favorite_ids),
                "note": "Radiologues favoris actifs",
                "icon": "fa-user-md",
                "accent": "is-teal",
            },
            {
                "label": "Candidatures en attente",
                "value": len(pending_applications),
                "note": "A traiter rapidement",
                "icon": "fa-files-o",
                "accent": "is-amber",
            },
            {
                "label": "Echeances a venir",
                "value": len(upcoming_deadlines),
                "note": "Missions a surveiller",
                "icon": "fa-flag-o",
                "accent": "is-slate",
            },
        ]

        selected_day_missions = []
        for mission in missions:
            mission_start = mission.start_date or mission.end_date
            mission_end = mission.end_date or mission.start_date or mission_start
            if mission_start and mission_start <= anchor_day <= mission_end:
                selected_day_missions.append({
                    "title": mission.name or "Mission",
                    "status": self.MISSION_STATUS_META.get(mission.status, self.MISSION_STATUS_META["draft"])["label"],
                    "css": self.MISSION_STATUS_META.get(mission.status, self.MISSION_STATUS_META["draft"])["css"],
                    "subtitle": mission.hospital_id.name or "Etablissement",
                    "meta": f"{self._safe_date_label(mission.start_date)} - {self._safe_date_label(mission.end_date or mission.start_date)}",
                    "url": f"/my/missions/{mission.id}",
                })

        selected_day_availabilities = []
        for availability in availability_by_weekday.get(anchor_day.weekday(), []):
            selected_day_availabilities.append({
                "title": availability.radiologist_id.display_name or "Radiologue",
                "subtitle": ", ".join(availability.radiologist_id.specialty_ids[:2].mapped("name")) or "Favori RadioVac",
                "meta": f"{self._float_to_hhmm(availability.start_time)} - {self._float_to_hhmm(availability.end_time)}",
                "url": f"/my/radiologists/{availability.radiologist_id.id}",
            })

        side_pending_applications = [
            {
                "title": application.radiologist_id.display_name or "Radiologue",
                "subtitle": application.mission_id.name or "Mission",
                "meta": self.APPLICATION_STATUS_META.get(application.status, self.APPLICATION_STATUS_META["pending"])["label"],
                "url": f"/my/missions/{application.mission_id.id}",
            }
            for application in pending_applications[:4]
        ]

        side_upcoming_deadlines = [
            {
                "title": mission.name or "Mission",
                "subtitle": self.MISSION_STATUS_META.get(mission.status, self.MISSION_STATUS_META["draft"])["label"],
                "meta": self._safe_date_label(mission.end_date),
                "url": f"/my/missions/{mission.id}",
            }
            for mission in upcoming_deadlines[:4]
        ]

        current_time_marker = False
        if view_mode != "month" and any(day_item["date_obj"] == today_day for day_item in calendar_columns):
            current_time_value = now_dt.hour + (now_dt.minute / 60.0)
            if 8.0 <= current_time_value <= 18.0:
                current_top = ((current_time_value - 8.0) / 10.0) * 100.0
                current_time_marker = {
                    "label": now_dt.strftime("%H:%M"),
                    "style": f"top: {current_top:.2f}%;",
                }

        legend_items = []
        for key in legend_seen:
            if key in {"is-draft", "is-published", "is-assigned", "is-done"}:
                label = next(meta["label"] for meta in self.MISSION_STATUS_META.values() if meta["css"] == key)
            elif key == "is-availability":
                label = "Disponibilite"
            elif key == "is-application":
                label = "Candidature"
            else:
                label = "Echeance"
            legend_items.append({"css": key, "label": label})

        if not legend_items:
            legend_items = [
                {"css": "is-published", "label": "Publiee"},
                {"css": "is-assigned", "label": "Affectee"},
                {"css": "is-availability", "label": "Disponibilite"},
                {"css": "is-application", "label": "Candidature"},
                {"css": "is-deadline", "label": "Echeance"},
            ]

        if view_mode == "day":
            prev_anchor = anchor_day - timedelta(days=1)
            next_anchor = anchor_day + timedelta(days=1)
        elif view_mode == "month":
            prev_anchor = self._shift_month(anchor_day, -1)
            next_anchor = self._shift_month(anchor_day, 1)
        else:
            prev_anchor = anchor_day - timedelta(days=7)
            next_anchor = anchor_day + timedelta(days=7)

        mobile_agenda_groups = []
        if view_mode == "month":
            month_cursor = month_start
            while month_cursor <= month_end:
                day_items = month_items.get(month_cursor, [])
                if day_items or month_cursor == anchor_day:
                    mobile_agenda_groups.append({
                        "label": f"{self.WEEKDAY_FULL[month_cursor.weekday()]} {month_cursor.day} {self.MONTH_NAMES[month_cursor.month - 1]}",
                        "items": day_items[:4],
                    })
                month_cursor += timedelta(days=1)
        else:
            for column in calendar_columns:
                combined_items = list(column["all_day_visible"])
                combined_items.extend([
                    {
                        "title": timed["title"],
                        "meta": timed["meta"],
                        "css": timed["css"],
                        "url": timed["url"],
                    }
                    for timed in column["timed_items"]
                ])
                mobile_agenda_groups.append({
                    "label": f"{column['day_full']} {column['day_number']} {self.MONTH_NAMES[column['date_obj'].month - 1]}",
                    "items": combined_items[:5],
                })

        values = {
            "hospital": hospital,
            "page_name": "calendar",
            "view_mode": view_mode,
            "anchor_day": anchor_day,
            "anchor_month_label": f"{self.MONTH_NAMES[anchor_day.month - 1]} {anchor_day.year}",
            "selected_day_label": f"{self.WEEKDAY_FULL[anchor_day.weekday()]} {anchor_day.day} {self.MONTH_NAMES[anchor_day.month - 1]} {anchor_day.year}",
            "current_params": current_params,
            "visible_column_count": len(visible_days),
            "prev_url": self._build_dashboard_url(current_params, anchor=prev_anchor.isoformat()),
            "next_url": self._build_dashboard_url(current_params, anchor=next_anchor.isoformat()),
            "today_url": self._build_dashboard_url(current_params, anchor=today_day.isoformat()),
            "prev_month_url": self._build_dashboard_url(
                current_params,
                anchor=self._shift_month(anchor_day.replace(day=1), -1).isoformat(),
            ),
            "next_month_url": self._build_dashboard_url(
                current_params,
                anchor=self._shift_month(anchor_day.replace(day=1), 1).isoformat(),
            ),
            "day_url": self._build_dashboard_url(current_params, view="day"),
            "week_url": self._build_dashboard_url(current_params, view="week"),
            "month_url": self._build_dashboard_url(current_params, view="month"),
            "type_options": self.EVENT_TYPE_OPTIONS,
            "status_options": self.STATUS_FILTER_OPTIONS,
            "selected_type": selected_type,
            "selected_status": selected_status,
            "selected_specialty": selected_specialty,
            "selected_radiologist": selected_radiologist,
            "selected_my_only": selected_my_only,
            "specialties": Specialty.search([]),
            "favorite_options": favorite_options,
            "stats_cards": stats_cards,
            "mini_calendar_weeks": mini_calendar_weeks,
            "mini_calendar_letters": self.WEEKDAY_COMPACT,
            "calendar_columns": calendar_columns,
            "calendar_hours": [f"{hour:02d}:00" for hour in range(8, 19)],
            "month_board_weeks": month_board_weeks,
            "legend_items": legend_items,
            "selected_day_missions": selected_day_missions,
            "selected_day_availabilities": selected_day_availabilities,
            "side_pending_applications": side_pending_applications,
            "side_upcoming_deadlines": side_upcoming_deadlines,
            "current_time_marker": current_time_marker,
            "mobile_agenda_groups": mobile_agenda_groups[:12],
        }
        return request.render("radiology.portal_hospital_dashboard", values)
