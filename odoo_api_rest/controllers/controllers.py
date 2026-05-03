import ast
import base64
import binascii
import json
import math
import logging
import secrets
from urllib import request as urllib_request
from urllib.error import URLError, HTTPError

from odoo import http, _, exceptions, fields
from odoo.http import request
from odoo.models import check_method_name

from .serializers import Serializer
from .exceptions import QueryFormatError

_logger = logging.getLogger(__name__)


# ============================= Legacy HTTP type ============================= #

def error_response(error, msg):
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": 200,
            "message": msg,
            "data": {
                "name": str(error),
                "debug": "",
                "message": msg,
                "arguments": list(error.args),
                "exception_type": type(error).__name__
            }
        }
    }


class OdooAPI(http.Controller):

    # ======================================================================== #
    #                                  Helpers                                 #
    # ======================================================================== #

    def seralize_one(self, current_user, query):
        try:
            serializer = Serializer(current_user, query)
            data = serializer.data
        except (SyntaxError, QueryFormatError) as e:
            raise exceptions.ValidationError(e.msg)
        return data

    def _build_current_user_default_payload(self, current_user, radiologist=None, hospital=None):
        profile = radiologist or hospital

        return {
            "id": current_user.id,
            "name": (
                (radiologist and (radiologist.display_name or current_user.name))
                or (hospital and (hospital.name or current_user.name))
                or current_user.name
            ),
            "image": ((profile and profile.image_1920) or current_user.image_1920 or False),
            "brands": [brand.name for brand in radiologist.brand_ids] if radiologist else [],
            "specialties": [specialty.name for specialty in radiologist.specialty_ids] if radiologist else [],
            "bio": radiologist.bio if radiologist else False,
            "email": ((profile and profile.email) or current_user.email or False),
            "has_diplome": bool(radiologist and radiologist.diplome_ids),
            "has_cv": bool(radiologist and radiologist.cv_attachment_ids),
            "hospital_id": radiologist.hospital_id.id if radiologist and radiologist.hospital_id else False,
            "hospital_name": (
                radiologist.hospital_id.name if radiologist and radiologist.hospital_id else False
            ),
            "hide_profile_for_current_hospital": (
                radiologist.hide_profile_for_current_hospital if radiologist else False
            ),
        }

    def _get_token_record(self):
        token = request.httprequest.headers.get("Token")
        if not token:
            return None, None, request.make_json_response({
                "status": "error",
                "message": "Missing token in Authorization header"
            }, status=401)

        radiologist = request.env["radiology.radiologist"].sudo().search([("api_token", "=", token)], limit=1)
        hospital = request.env["radiology.hospital"].sudo().search([("api_token", "=", token)], limit=1)

        if not radiologist and not hospital:
            return None, None, request.make_json_response({
                "status": "error",
                "message": "Invalid token"
            }, status=401)

        return radiologist, hospital, None

    def _create_hospital_notification(self, mission, title, message, notif_type="info"):
        hospital = mission.hospital_id
        if not hospital:
            return False

        request.env["radiology.notification"].sudo().create({
            "hospital_id": hospital.id,
            "title": title,
            "message": message,
            "type": notif_type,
            "action_url": f"/my/missions/{mission.id}",
        })
        return True

    def _get_chat_actor(self):
        radiologist, hospital, error = self._get_token_record()
        if error:
            return None, None, None, error

        if radiologist:
            return "radiologist", radiologist.id, radiologist, None
        return "hospital", hospital.id, hospital, None

    def _get_actor_conversation(self, conversation_id):
        actor_type, actor_id, actor_record, error = self._get_chat_actor()
        if error:
            return None, None, None, None, error

        conversation = request.env["radiology.chat.conversation"].sudo().browse(int(conversation_id))
        if not conversation.exists():
            return None, None, None, None, request.make_json_response({
                "status": "error",
                "message": "Conversation not found"
            }, status=404)

        if actor_type == "radiologist" and conversation.radiologist_id.id != actor_id:
            return None, None, None, None, request.make_json_response({
                "status": "error",
                "message": "Forbidden conversation"
            }, status=403)
        if actor_type == "hospital" and conversation.hospital_id.id != actor_id:
            return None, None, None, None, request.make_json_response({
                "status": "error",
                "message": "Forbidden conversation"
            }, status=403)

        return actor_type, actor_id, actor_record, conversation, None

    def _serialize_chat_conversation(self, conversation, actor_type):
        if actor_type == "radiologist":
            unread_count = request.env["radiology.chat.message"].sudo().search_count([
                ("conversation_id", "=", conversation.id),
                ("sender_type", "=", "hospital"),
                ("is_read_by_radiologist", "=", False),
            ])
            peer_name = conversation.hospital_id.name or "Hopital"
            peer_image = conversation.hospital_id.image_1920 or False
            peer_city = conversation.hospital_id.city or False
        else:
            unread_count = request.env["radiology.chat.message"].sudo().search_count([
                ("conversation_id", "=", conversation.id),
                ("sender_type", "=", "radiologist"),
                ("is_read_by_hospital", "=", False),
            ])
            peer_name = conversation.radiologist_id.display_name or "Radiologue"
            peer_image = conversation.radiologist_id.image_1920 or False
            peer_city = False

        return {
            "id": conversation.id,
            "hospital_id": conversation.hospital_id.id,
            "hospital_name": conversation.hospital_id.name or False,
            "radiologist_id": conversation.radiologist_id.id,
            "radiologist_name": conversation.radiologist_id.display_name or False,
            "peer_name": peer_name,
            "peer_city": peer_city,
            "peer_image": peer_image,
            "last_message": conversation.last_message or False,
            "last_message_date": conversation.last_message_date.isoformat() if conversation.last_message_date else False,
            "unread_count": unread_count,
            "is_active": conversation.is_active,
        }

    def _serialize_chat_message(self, message):
        return {
            "id": message.id,
            "conversation_id": message.conversation_id.id,
            "sender_type": message.sender_type,
            "sender_id": message.sender_id,
            "message": message.message,
            "create_date": message.create_date.isoformat() if message.create_date else False,
            "is_read_by_hospital": bool(message.is_read_by_hospital),
            "is_read_by_radiologist": bool(message.is_read_by_radiologist),
        }

    def _serialize_radiologist_availability(self, availability):
        return {
            "id": availability.id,
            "radiologist_id": availability.radiologist_id.id,
            "weekday": availability.weekday,
            "weekday_label": dict(
                availability._fields["weekday"].selection
            ).get(availability.weekday, availability.weekday),
            "start_time": availability.start_time,
            "end_time": availability.end_time,
            "is_night": bool(availability.is_night),
            "is_weekend": bool(availability.is_weekend),
            "active": bool(availability.active),
        }

    def _normalize_time_float(self, value, field_name):
        if value in (None, False, ""):
            raise exceptions.ValidationError(f"Field `{field_name}` is required")
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            raise exceptions.ValidationError(f"Field `{field_name}` must be a number")

        if normalized < 0 or normalized > 24:
            raise exceptions.ValidationError(f"Field `{field_name}` must be between 0 and 24")
        return normalized

    def _prepare_availability_vals(self, data):
        if not isinstance(data, dict):
            raise exceptions.ValidationError("Each availability item must be an object")

        weekday = data.get("weekday")
        if weekday in (None, ""):
            raise exceptions.ValidationError("Field `weekday` is required")

        vals = {
            "weekday": str(weekday),
            "start_time": self._normalize_time_float(data.get("start_time"), "start_time"),
            "end_time": self._normalize_time_float(data.get("end_time"), "end_time"),
            "is_night": self._normalize_boolean_value(data.get("is_night", False), "is_night"),
            "active": self._normalize_boolean_value(data.get("active", True), "active"),
        }
        allowed_weekdays = {key for key, _ in request.env["radiology.radiologist.availability"]._fields["weekday"].selection}
        if vals["weekday"] not in allowed_weekdays:
            raise exceptions.ValidationError("Field `weekday` contains an invalid value")
        return vals

    def _serialize_mobile_mission(self, mission):
        hospital = mission.hospital_id
        return {
            "id": mission.id,
            "name": mission.name or False,
            "hospital_id": {
                "id": hospital.id,
                "name": hospital.name or False,
                "city": hospital.city or False,
                "email": hospital.email or False,
                "phone": hospital.phone or False,
                "longitude": hospital.longitude or False,
                "latitude": hospital.latitude or False,
                "image_1920": hospital.image_1920 or False,
            } if hospital else False,
            "speciality_ids": [
                {"id": specialty.id, "name": specialty.name or False}
                for specialty in mission.speciality_ids
            ],
            "brand_ids": [
                {"id": brand.id, "name": brand.name or False}
                for brand in mission.brand_ids
            ],
            "description": mission.description or False,
            "avantage": mission.avantage or False,
            "tarif": mission.tarif or False,
            "tarif_type": mission.tarif_type or False,
            "start_date": mission.start_date.isoformat() if mission.start_date else False,
            "end_date": mission.end_date.isoformat() if mission.end_date else False,
            "status": mission.status or False,
            "assigned_radiologist_id": mission.assigned_radiologist_id.id if mission.assigned_radiologist_id else False,
            "create_date": mission.create_date.isoformat() if mission.create_date else False,
            "write_date": mission.write_date.isoformat() if mission.write_date else False,
        }

    def _mission_sort_key(self, mission):
        status_rank = 0 if mission.status == "assigned" else 1
        date_value = (
            mission.start_date
            or mission.end_date
            or fields.Date.to_date(mission.write_date)
            or fields.Date.today()
        )
        return status_rank, date_value.toordinal() * -1, mission.id * -1

    def _send_push_notification(self, *, tokens, title, body, data=None):
        tokens = [token for token in (tokens or []) if token]
        if not tokens:
            return False

        params = request.env["ir.config_parameter"].sudo()
        push_url = (params.get_param("radiology.firebase_push_url") or "").strip()
        push_secret = (params.get_param("radiology.firebase_push_secret") or "").strip()
        if not push_url:
            _logger.info("Firebase push skipped: missing radiology.firebase_push_url")
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
                    return True
                _logger.warning("Firebase push returned status %s", status)
        except (HTTPError, URLError, TimeoutError) as e:
            _logger.warning("Firebase push failed: %s", str(e))
        except Exception as e:
            _logger.exception("Unexpected Firebase push error: %s", str(e))
        return False

    def _normalize_m2m_ids(self, value, field_name):
        if value in (None, False, ""):
            return False

        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]

        if not isinstance(value, list):
            raise exceptions.ValidationError(f"Field `{field_name}` must be a list of ids")

        try:
            ids = [int(item) for item in value]
        except (TypeError, ValueError):
            raise exceptions.ValidationError(f"Field `{field_name}` must contain only integer ids")

        return [(6, 0, ids)]

    def _normalize_m2o_id(self, value, field_name):
        if value in (None, False, ""):
            return False

        if isinstance(value, str):
            value = value.strip()

        try:
            return int(value)
        except (TypeError, ValueError):
            raise exceptions.ValidationError(f"Field `{field_name}` must be an integer id")

    def _normalize_base64_value(self, value, field_name):
        if value in (None, False, ""):
            return False

        if not isinstance(value, str):
            raise exceptions.ValidationError(f"Field `{field_name}` must be a base64 string")

        normalized = value.strip()
        if normalized.startswith("data:"):
            parts = normalized.split(",", 1)
            if len(parts) != 2:
                raise exceptions.ValidationError(f"Field `{field_name}` contains an invalid data URL")
            normalized = parts[1].strip()

        try:
            base64.b64decode(normalized, validate=True)
        except (binascii.Error, ValueError):
            raise exceptions.ValidationError(f"Field `{field_name}` must be valid base64")

        return normalized

    def _normalize_boolean_value(self, value, field_name):
        if value in (None, ""):
            return False

        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            if value in (0, 1):
                return bool(value)
            raise exceptions.ValidationError(f"Field `{field_name}` must be a boolean")

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("true", "1", "yes", "y", "on"):
                return True
            if normalized in ("false", "0", "no", "n", "off"):
                return False

        raise exceptions.ValidationError(f"Field `{field_name}` must be a boolean")

    def _attachment_payload_from_base64(self, value, field_name, index=1, default_name=None):
        normalized = value.strip() if isinstance(value, str) else value
        mimetype = "application/octet-stream"

        if isinstance(normalized, str) and normalized.startswith("data:"):
            header = normalized.split(",", 1)[0]
            mimetype = header[5:].split(";", 1)[0] or mimetype

        return {
            "name": default_name or f"{field_name}_{index}",
            "datas": self._normalize_base64_value(value, f"{field_name}[{index}].data"),
            "mimetype": mimetype,
        }

    def _prepare_attachment_commands(self, value, field_name):
        if value in (None, False, ""):
            return False

        if isinstance(value, dict):
            value = [value]

        if isinstance(value, str):
            normalized = value.strip()
            if normalized.startswith("["):
                try:
                    value = json.loads(normalized)
                except json.JSONDecodeError:
                    value = [item.strip() for item in normalized.split(",") if item.strip()]
            else:
                try:
                    value = [self._attachment_payload_from_base64(normalized, field_name)]
                except exceptions.ValidationError:
                    value = [item.strip() for item in normalized.split(",") if item.strip()]

        if not isinstance(value, list):
            raise exceptions.ValidationError(
                f"Field `{field_name}` must be a list of ids or attachment objects"
            )

        if all(not isinstance(item, dict) for item in value):
            return self._normalize_m2m_ids(value, field_name)

        attachment_commands = []
        Attachment = request.env["ir.attachment"].sudo()

        for index, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                raise exceptions.ValidationError(
                    f"Field `{field_name}` cannot mix ids and attachment objects"
                )

            datas_value = (
                item.get("data")
                or item.get("datas")
                or item.get("base64")
                or item.get("content")
            )
            datas = self._normalize_base64_value(datas_value, f"{field_name}[{index}].data")
            attachment = Attachment.create({
                "name": item.get("name") or item.get("filename") or f"{field_name}_{index}",
                "datas": datas,
                "mimetype": item.get("mimetype") or "application/octet-stream",
                "type": "binary",
            })
            attachment_commands.append(attachment.id)

        return [(6, 0, attachment_commands)]

    def _prepare_radiologist_create_vals(self, data, user):
        vals = {
            "user_id": user.id,
            "display_name": data.get("name") or data.get("display_name"),
            "email": data["email"],
        }

        direct_field_aliases = {
            "phone": ["phone"],
            "bio": ["bio"],
            "birthday_date": ["birthday_date", "birthday"],
            "experience_years": ["experience_years"],
        }
        for field_name, aliases in direct_field_aliases.items():
            for alias in aliases:
                if alias in data:
                    vals[field_name] = data.get(alias)
                    break

        m2o_field_aliases = {
            "hospital_id": ["hospital_id", "current_hospital_id"],
        }
        for field_name, aliases in m2o_field_aliases.items():
            for alias in aliases:
                if alias in data:
                    vals[field_name] = self._normalize_m2o_id(data.get(alias), alias)
                    break

        hide_hospital_aliases = [
            "hide_profile_for_current_hospital",
            "hide_profile_for_hospital",
            "hide_from_current_hospital",
        ]
        hide_hospital_key = next((alias for alias in hide_hospital_aliases if alias in data), None)

        if vals.get("hospital_id"):
            if not hide_hospital_key:
                raise exceptions.ValidationError(
                    "Field `hide_profile_for_current_hospital` is required when `hospital_id` is provided"
                )
            vals["hide_profile_for_current_hospital"] = self._normalize_boolean_value(
                data.get(hide_hospital_key),
                hide_hospital_key,
            )
        else:
            vals["hide_profile_for_current_hospital"] = False
            if hide_hospital_key:
                raise exceptions.ValidationError(
                    "Field `hospital_id` is required when `hide_profile_for_current_hospital` is provided"
                )

        boolean_field_aliases = {
            "hide_profile_for_current_hospital": [
                "hide_profile_for_current_hospital",
                "hide_profile_for_hospital",
                "hide_from_current_hospital",
            ],
        }
        for field_name, aliases in boolean_field_aliases.items():
            for alias in aliases:
                if alias in data and field_name not in vals:
                    vals[field_name] = self._normalize_boolean_value(data.get(alias), alias)
                    break

        for image_key in ["image", "image_1920", "photo", "photo_base64", "profile_image"]:
            if image_key in data and data.get(image_key):
                vals["image_1920"] = self._normalize_base64_value(data.get(image_key), image_key)
                break

        m2m_field_aliases = {
            "specialty_ids": ["specialty_ids"],
            "brand_ids": ["brand_ids"],
            "cv_attachment_ids": ["cv_attachment_ids", "cv_attachement_ids", "cv", "cv_base64"],
            "diplome_ids": ["diplome_ids", "diplome", "diploma", "diploma_ids", "diplome_base64"],
        }
        for field_name, aliases in m2m_field_aliases.items():
            for alias in aliases:
                if alias not in data:
                    continue

                if field_name in ("cv_attachment_ids", "diplome_ids"):
                    vals[field_name] = self._prepare_attachment_commands(data.get(alias), alias)
                else:
                    vals[field_name] = self._normalize_m2m_ids(data.get(alias), alias)
                break

        return vals

    # ======================================================================== #
    #                                   AUTH                                   #
    # ======================================================================== #

    @http.route('/auth/create_radiologist', type='http', auth='none', methods=['POST'], csrf=False)
    def create_radiologist(self, **kwargs):
        try:
            # Lecture du JSON depuis le body
            data = request.httprequest.json if request.httprequest.is_json else {}

            if not data:
                return request.make_json_response({
                    "status": "error",
                    "message": "No JSON data provided or invalid JSON"
                }, status=400)

            required_fields = ["name", "email", "password"]
            for f in required_fields:
                if f not in data:
                    return request.make_json_response({
                        "status": "error",
                        "message": f"Missing field: {f}"
                    }, status=400)

            # Vérifier si l'email existe déjà
            existing_user = request.env['res.users'].sudo().search([('login', '=', data['email'])], limit=1)
            if existing_user:
                return request.make_json_response({
                    "status": "error",
                    "message": "Email already exists"
                }, status=400)

            # Créer le user
            company = request.env['res.company'].sudo().search([], limit=1)
            if not company:
                return request.make_json_response({
                    "status": "error",
                    "message": "No company found in the system"
                }, status=500)

            user = request.env['res.users'].sudo().create({
                "name": data['name'],
                "login": data['email'],
                "password": data['password'],
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],  # Assign company to user
                "groups_id": [
                    (4, request.env.ref('base.group_user').id),
                    # Add any additional groups your radiologists need
                ]
            })

            # Créer le radiologue
            radiologist_vals = self._prepare_radiologist_create_vals(data, user)
            radiologist = request.env['radiology.radiologist'].sudo().create(radiologist_vals)

            # Générer le token API
            radiologist.sudo().generate_api_token()

            return request.make_json_response({
                "status": "ok",
                "user_id": user.id,
                "radiologist_id": radiologist.id,
                "token": radiologist.api_token
            })

        except Exception as e:
            # Log l'erreur pour le débogage
            _logger.error("Error creating radiologist: %s", str(e))

            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred while creating the radiologist: {str(e)}"
            }, status=500)

    @http.route('/auth/create_hospital', type='http', auth='none', methods=['POST'], csrf=False)
    def create_hospital(self, **kwargs):
        try:
            # Lecture du JSON depuis le body
            data = request.httprequest.json if request.httprequest.is_json else {}

            if not data:
                return request.make_json_response({
                    "status": "error",
                    "message": "No JSON data provided or invalid JSON"
                }, status=400)

            required_fields = ["name", "email", "password"]
            for f in required_fields:
                if f not in data:
                    return request.make_json_response({
                        "status": "error",
                        "message": f"Missing field: {f}"
                    }, status=400)

            # Vérifier si l'email existe déjà
            existing_user = request.env['res.users'].sudo().search([('login', '=', data['email'])], limit=1)
            if existing_user:
                return request.make_json_response({
                    "status": "error",
                    "message": "Email already exists"
                }, status=400)

            # Récupérer la compagnie par défaut
            company = request.env['res.company'].sudo().search([], limit=1)
            if not company:
                return request.make_json_response({
                    "status": "error",
                    "message": "No company found in the system"
                }, status=500)

            # Créer l'utilisateur
            user = request.env['res.users'].sudo().create({
                "name": data['name'],
                "login": data['email'],
                "password": data['password'],
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],
                "groups_id": [
                    (4, request.env.ref('base.group_user').id),
                    # ajouter d'autres groupes si nécessaire
                ]
            })

            # Créer l'hôpital
            hospital = request.env['radiology.hospital'].sudo().create({
                "user_id": user.id,
                "name": data['name'],
                "email": data['email'],
                "city": data.get('city'),
                "phone": data.get('phone'),

            })

            hospital.sudo().generate_api_token()

            return request.make_json_response({
                "status": "ok",
                "user_id": user.id,
                "hospital_id": hospital.id,
                "token": hospital.api_token
            })

        except Exception as e:
            _logger.error("Error creating hospital: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred while creating the hospital: {str(e)}"
            }, status=500)

    @http.route('/auth/token', type='http', auth='none', methods=['POST'], csrf=False)
    def authenticate_token(self, **kwargs):
        try:
            # Lecture JSON
            data = request.httprequest.json if request.httprequest.is_json else {}

            email = data.get("email")
            password = data.get("password")
            db = request.env.cr.dbname  # récupère la DB courante

            if not email or not password:
                return request.make_json_response({
                    "status": "error",
                    "message": "Missing email or password"
                }, status=400)

            # Rechercher dans Radiologist
            radiologist = request.env["radiology.radiologist"].sudo().search([("email", "=", email)], limit=1)
            if radiologist:
                user = radiologist.user_id
                if not user:
                    return request.make_json_response({
                        "status": "error",
                        "message": "Radiologist has no linked user"
                    }, status=500)

                # Authentification officielle Odoo
                try:
                    uid = request.session.authenticate(db, user.login, password)
                except Exception:
                    return request.make_json_response({
                        "status": "error",
                        "message": "Invalid credentials"
                    }, status=401)

                if not radiologist.api_token:
                    radiologist.sudo().generate_api_token()

                return request.make_json_response({
                    "status": "ok",
                    "token": radiologist.api_token,
                    "user_id": user.id,
                    "user_type": "radiologist",
                    "related_record_id": radiologist.id
                })

            # Rechercher dans Hospital
            hospital = request.env["radiology.hospital"].sudo().search([("email", "=", email)], limit=1)
            if hospital:
                user = hospital.user_id
                if not user:
                    return request.make_json_response({
                        "status": "error",
                        "message": "Hospital has no linked user"
                    }, status=500)

                try:
                    uid = request.session.authenticate(db, user.login, password)
                except Exception:
                    return request.make_json_response({
                        "status": "error",
                        "message": "Invalid credentials"
                    }, status=401)

                if not hospital.api_token:
                    hospital.sudo().generate_api_token()

                return request.make_json_response({
                    "status": "ok",
                    "token": hospital.api_token,
                    "user_id": user.id,
                    "user_type": "hospital",
                    "related_record_id": hospital.id
                })

            # Utilisateur non trouvé
            return request.make_json_response({
                "status": "error",
                "message": "User not found"
            }, status=404)

        except Exception as e:
            _logger.error("Error in token authentication: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred during authentication: {str(e)}"
            }, status=500)

    @http.route("/api/current_user", type='http', auth='none', methods=['GET'], csrf=False)
    def get_current_user(self, **kwargs):
        try:
            # 1️⃣ Récupérer le token depuis les headers
            token = request.httprequest.headers.get("Token")
            if not token:
                return request.make_json_response({
                    "status": "error",
                    "message": "Missing token in Authorization header"
                }, status=401)

            # 2️⃣ Rechercher le radiologist ou hospital correspondant au token
            radiologist = request.env["radiology.radiologist"].sudo().search([("api_token", "=", token)], limit=1)
            hospital = request.env["radiology.hospital"].sudo().search([("api_token", "=", token)], limit=1)

            if radiologist:
                current_user = radiologist.user_id
            elif hospital:
                current_user = hospital.user_id
            else:
                return request.make_json_response({
                    "status": "error",
                    "message": "Invalid token"
                }, status=401)

            # 3️⃣ Sérialiser les données
            params = {}
            if request.httprequest.is_json:
                params.update(request.httprequest.json or {})
            params.update(request.httprequest.args.to_dict())

            query = params.get("query")

            if query:
                data = self.seralize_one(current_user, query)
            else:
                data = self._build_current_user_default_payload(
                    current_user,
                    radiologist=radiologist,
                    hospital=hospital,
                )

            return request.make_json_response({
                "status": "ok",
                "data": data
            })

        except Exception as e:
            _logger.error("Error fetching current user: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/my/missions", type='http', auth='none', methods=['GET'], csrf=False)
    def get_my_missions(self, **kwargs):
        try:
            radiologist, hospital, error = self._get_token_record()
            if error:
                return error
            if hospital:
                return request.make_json_response({
                    "status": "error",
                    "message": "Only radiologists can access assigned missions"
                }, status=403)

            statuses_raw = (kwargs.get("statuses") or "").strip()
            requested_statuses = [
                status.strip()
                for status in statuses_raw.split(",")
                if status.strip()
            ]
            allowed_statuses = {"assigned", "done"}
            statuses = [
                status for status in requested_statuses if status in allowed_statuses
            ] or ["assigned", "done"]

            missions = request.env["radiology.mission"].sudo().search([
                ("assigned_radiologist_id", "=", radiologist.id),
                ("status", "in", statuses),
            ])
            ordered_missions = sorted(missions, key=self._mission_sort_key)

            serialized = [
                self._serialize_mobile_mission(mission)
                for mission in ordered_missions
            ]

            return request.make_json_response({
                "status": "ok",
                "data": serialized,
                "meta": {
                    "total": len(serialized),
                    "assigned_count": len([mission for mission in ordered_missions if mission.status == "assigned"]),
                    "done_count": len([mission for mission in ordered_missions if mission.status == "done"]),
                }
            })

        except Exception as e:
            _logger.error("Error fetching mobile missions: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/radiologist/availabilities", type='http', auth='none', methods=['GET'], csrf=False)
    def get_radiologist_availabilities(self, **kwargs):
        try:
            radiologist, hospital, error = self._get_token_record()
            if error:
                return error
            if hospital or not radiologist:
                return request.make_json_response({
                    "status": "error",
                    "message": "Only radiologists can access availabilities"
                }, status=403)

            include_inactive_raw = request.httprequest.args.get("include_inactive", "")
            include_inactive = str(include_inactive_raw).strip().lower() in ("1", "true", "yes", "on")

            domain = [("radiologist_id", "=", radiologist.id)]
            if not include_inactive:
                domain.append(("active", "=", True))

            availabilities = request.env["radiology.radiologist.availability"].sudo().search(
                domain,
                order="weekday, start_time, id",
            )

            return request.make_json_response({
                "status": "ok",
                "data": [
                    self._serialize_radiologist_availability(availability)
                    for availability in availabilities
                ],
                "meta": {
                    "total": len(availabilities),
                    "active_count": len(availabilities.filtered("active")),
                },
            })
        except Exception as e:
            _logger.error("Error fetching radiologist availabilities: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/radiologist/availabilities", type='http', auth='none', methods=['PUT'], csrf=False)
    def replace_radiologist_availabilities(self, **kwargs):
        try:
            radiologist, hospital, error = self._get_token_record()
            if error:
                return error
            if hospital or not radiologist:
                return request.make_json_response({
                    "status": "error",
                    "message": "Only radiologists can update availabilities"
                }, status=403)

            data = request.httprequest.json if request.httprequest.is_json else {}
            if not data or "availabilities" not in data:
                return request.make_json_response({
                    "status": "error",
                    "message": "Missing field: availabilities"
                }, status=400)

            items = data.get("availabilities")
            if not isinstance(items, list):
                return request.make_json_response({
                    "status": "error",
                    "message": "Field `availabilities` must be a list"
                }, status=400)

            Availability = request.env["radiology.radiologist.availability"].sudo()
            existing = Availability.search([("radiologist_id", "=", radiologist.id)])
            existing_by_id = {record.id: record for record in existing}
            kept_ids = set()

            for item in items:
                vals = self._prepare_availability_vals(item)
                vals["radiologist_id"] = radiologist.id

                record_id = item.get("id")
                if record_id not in (None, False, ""):
                    try:
                        record_id = int(record_id)
                    except (TypeError, ValueError):
                        return request.make_json_response({
                            "status": "error",
                            "message": "Field `id` must be an integer"
                        }, status=400)

                    record = existing_by_id.get(record_id)
                    if not record:
                        return request.make_json_response({
                            "status": "error",
                            "message": f"Availability {record_id} not found"
                        }, status=404)
                    record.write(vals)
                    kept_ids.add(record.id)
                else:
                    record = Availability.create(vals)
                    kept_ids.add(record.id)

            to_remove = existing.filtered(lambda record: record.id not in kept_ids)
            if to_remove:
                to_remove.unlink()

            updated = Availability.search(
                [("radiologist_id", "=", radiologist.id)],
                order="weekday, start_time, id",
            )

            return request.make_json_response({
                "status": "ok",
                "message": "Availabilities updated successfully",
                "data": [
                    self._serialize_radiologist_availability(availability)
                    for availability in updated
                ],
                "meta": {
                    "total": len(updated),
                    "active_count": len(updated.filtered("active")),
                },
            })
        except exceptions.ValidationError as e:
            return request.make_json_response({
                "status": "error",
                "message": e.name or str(e),
            }, status=400)
        except Exception as e:
            _logger.error("Error updating radiologist availabilities: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/missions/<int:mission_id>/apply", type='http', auth='none', methods=['POST'], csrf=False)
    def apply_to_mission(self, mission_id, **kwargs):
        try:
            radiologist, hospital, error = self._get_token_record()
            if error:
                return error
            if hospital:
                return request.make_json_response({
                    "status": "error",
                    "message": "Only radiologists can apply to a mission"
                }, status=403)

            Mission = request.env["radiology.mission"].sudo()
            Application = request.env["radiology.application"].sudo()

            mission = Mission.browse(mission_id)
            if not mission.exists():
                return request.make_json_response({
                    "status": "error",
                    "message": "Mission not found"
                }, status=404)

            if mission.status in ["assigned", "done"]:
                return request.make_json_response({
                    "status": "error",
                    "message": "This mission is no longer open for applications"
                }, status=400)

            existing_application = Application.search([
                ("mission_id", "=", mission.id),
                ("radiologist_id", "=", radiologist.id),
            ], limit=1)
            if existing_application:
                return request.make_json_response({
                    "status": "error",
                    "message": "You have already applied to this mission",
                    "data": {
                        "application_id": existing_application.id,
                        "status": existing_application.status,
                    }
                }, status=409)

            application = Application.create({
                "mission_id": mission.id,
                "radiologist_id": radiologist.id,
                "status": "pending",
            })

            radiologist_name = (
                radiologist.display_name
                or radiologist.user_id.name
                or "Un radiologue"
            )
            mission_name = mission.name or f"mission #{mission.id}"
            self._create_hospital_notification(
                mission,
                title="Nouvelle candidature",
                message=f"{radiologist_name} a postule a {mission_name}.",
                notif_type="info",
            )

            return request.make_json_response({
                "status": "ok",
                "message": "Application submitted successfully",
                "data": {
                    "application_id": application.id,
                    "mission_id": mission.id,
                    "radiologist_id": radiologist.id,
                    "status": application.status,
                }
            }, status=201)

        except Exception as e:
            _logger.error("Error applying to mission %s: %s", mission_id, str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/missions/<int:mission_id>/cancel_application", type='http', auth='none', methods=['POST'], csrf=False)
    def cancel_mission_application(self, mission_id, **kwargs):
        try:
            radiologist, hospital, error = self._get_token_record()
            if error:
                return error
            if hospital:
                return request.make_json_response({
                    "status": "error",
                    "message": "Only radiologists can cancel an application"
                }, status=403)

            Mission = request.env["radiology.mission"].sudo()
            Application = request.env["radiology.application"].sudo()

            mission = Mission.browse(mission_id)
            if not mission.exists():
                return request.make_json_response({
                    "status": "error",
                    "message": "Mission not found"
                }, status=404)

            application = Application.search([
                ("mission_id", "=", mission.id),
                ("radiologist_id", "=", radiologist.id),
            ], limit=1)
            if not application:
                return request.make_json_response({
                    "status": "error",
                    "message": "No application found for this mission"
                }, status=404)

            if application.status == "accepted" or mission.assigned_radiologist_id.id == radiologist.id:
                return request.make_json_response({
                    "status": "error",
                    "message": "Accepted or assigned applications cannot be cancelled"
                }, status=400)

            radiologist_name = (
                radiologist.display_name
                or radiologist.user_id.name
                or "Un radiologue"
            )
            mission_name = mission.name or f"mission #{mission.id}"
            application.unlink()
            self._create_hospital_notification(
                mission,
                title="Candidature annulee",
                message=f"{radiologist_name} a annule sa candidature pour {mission_name}.",
                notif_type="warning",
            )

            return request.make_json_response({
                "status": "ok",
                "message": "Application cancelled successfully",
                "data": {
                    "mission_id": mission.id,
                    "radiologist_id": radiologist.id,
                }
            })

        except Exception as e:
            _logger.error("Error cancelling application for mission %s: %s", mission_id, str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/chat/conversations", type='http', auth='none', methods=['GET'], csrf=False)
    def get_chat_conversations(self, **kwargs):
        try:
            actor_type, actor_id, _, error = self._get_chat_actor()
            if error:
                return error

            domain = [(f"{actor_type}_id", "=", actor_id)]
            conversations = request.env["radiology.chat.conversation"].sudo().search(
                domain,
                order="last_message_date desc, id desc",
            )

            return request.make_json_response({
                "status": "ok",
                "data": [
                    self._serialize_chat_conversation(conversation, actor_type)
                    for conversation in conversations
                ],
            })
        except Exception as e:
            _logger.error("Error fetching chat conversations: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/chat/conversations/start", type='http', auth='none', methods=['POST'], csrf=False)
    def start_chat_conversation(self, **kwargs):
        try:
            actor_type, actor_id, _, error = self._get_chat_actor()
            if error:
                return error

            data = request.httprequest.json if request.httprequest.is_json else {}
            if not data:
                return request.make_json_response({
                    "status": "error",
                    "message": "No JSON data provided or invalid JSON"
                }, status=400)

            Conversation = request.env["radiology.chat.conversation"].sudo()
            Hospital = request.env["radiology.hospital"].sudo()
            Radiologist = request.env["radiology.radiologist"].sudo()

            if actor_type == "radiologist":
                hospital_id = data.get("hospital_id")
                if not hospital_id:
                    return request.make_json_response({
                        "status": "error",
                        "message": "Missing field: hospital_id"
                    }, status=400)
                hospital = Hospital.browse(int(hospital_id))
                if not hospital.exists():
                    return request.make_json_response({
                        "status": "error",
                        "message": "Hospital not found"
                    }, status=404)
                conversation = Conversation.search([
                    ("hospital_id", "=", hospital.id),
                    ("radiologist_id", "=", actor_id),
                ], limit=1)
                if not conversation:
                    conversation = Conversation.create({
                        "hospital_id": hospital.id,
                        "radiologist_id": actor_id,
                    })
            else:
                radiologist_id = data.get("radiologist_id")
                if not radiologist_id:
                    return request.make_json_response({
                        "status": "error",
                        "message": "Missing field: radiologist_id"
                    }, status=400)
                radiologist = Radiologist.browse(int(radiologist_id))
                if not radiologist.exists():
                    return request.make_json_response({
                        "status": "error",
                        "message": "Radiologist not found"
                    }, status=404)
                conversation = Conversation.search([
                    ("hospital_id", "=", actor_id),
                    ("radiologist_id", "=", radiologist.id),
                ], limit=1)
                if not conversation:
                    conversation = Conversation.create({
                        "hospital_id": actor_id,
                        "radiologist_id": radiologist.id,
                    })

            return request.make_json_response({
                "status": "ok",
                "data": self._serialize_chat_conversation(conversation, actor_type),
            })
        except Exception as e:
            _logger.error("Error starting chat conversation: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/chat/conversations/<int:conversation_id>/messages", type='http', auth='none', methods=['GET'], csrf=False)
    def get_chat_messages(self, conversation_id, **kwargs):
        try:
            actor_type, _, _, conversation, error = self._get_actor_conversation(conversation_id)
            if error:
                return error

            last_id = int(request.httprequest.args.get("last_id", 0) or 0)
            domain = [("conversation_id", "=", conversation.id)]
            if last_id:
                domain.append(("id", ">", last_id))

            messages = request.env["radiology.chat.message"].sudo().search(
                domain,
                order="id asc",
                limit=100,
            )

            unread_domain = [
                ("conversation_id", "=", conversation.id),
                ("sender_type", "!=", actor_type),
            ]
            if actor_type == "radiologist":
                unread_messages = request.env["radiology.chat.message"].sudo().search(
                    unread_domain + [("is_read_by_radiologist", "=", False)]
                )
                if unread_messages:
                    unread_messages.write({"is_read_by_radiologist": True})
            else:
                unread_messages = request.env["radiology.chat.message"].sudo().search(
                    unread_domain + [("is_read_by_hospital", "=", False)]
                )
                if unread_messages:
                    unread_messages.write({"is_read_by_hospital": True})

            return request.make_json_response({
                "status": "ok",
                "data": [self._serialize_chat_message(message) for message in messages],
            })
        except Exception as e:
            _logger.error("Error fetching chat messages: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/chat/conversations/<int:conversation_id>/messages", type='http', auth='none', methods=['POST'], csrf=False)
    def send_chat_message(self, conversation_id, **kwargs):
        try:
            actor_type, actor_id, _, conversation, error = self._get_actor_conversation(conversation_id)
            if error:
                return error

            data = request.httprequest.json if request.httprequest.is_json else {}
            message_text = (data.get("message") or "").strip() if data else ""
            if not message_text:
                return request.make_json_response({
                    "status": "error",
                    "message": "Missing field: message"
                }, status=400)

            message = request.env["radiology.chat.message"].sudo().create({
                "conversation_id": conversation.id,
                "sender_type": actor_type,
                "sender_id": actor_id,
                "message": message_text,
            })

            return request.make_json_response({
                "status": "ok",
                "data": self._serialize_chat_message(message),
            }, status=201)
        except Exception as e:
            _logger.error("Error sending chat message: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/mobile/device/register", type='http', auth='none', methods=['POST'], csrf=False)
    def register_mobile_device(self, **kwargs):
        try:
            radiologist, hospital, error = self._get_token_record()
            if error:
                return error
            if hospital or not radiologist:
                return request.make_json_response({
                    "status": "error",
                    "message": "Only radiologists can register a mobile device"
                }, status=403)

            data = request.httprequest.json if request.httprequest.is_json else {}
            token = (data.get("fcm_token") or "").strip() if data else ""
            if not token:
                return request.make_json_response({
                    "status": "error",
                    "message": "Missing field: fcm_token"
                }, status=400)

            Device = request.env["radiology.mobile.device"].sudo()
            device = Device.search([("fcm_token", "=", token)], limit=1)
            vals = {
                "radiologist_id": radiologist.id,
                "fcm_token": token,
                "platform": (data.get("platform") or "").strip() or False,
                "device_name": (data.get("device_name") or "").strip() or False,
                "is_active": True,
                "last_seen": fields.Datetime.now(),
            }
            if device:
                device.write(vals)
            else:
                device = Device.create(vals)

            return request.make_json_response({
                "status": "ok",
                "data": {
                    "device_id": device.id,
                    "radiologist_id": radiologist.id,
                },
            })
        except Exception as e:
            _logger.error("Error registering mobile device: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    @http.route("/api/mobile/device/unregister", type='http', auth='none', methods=['POST'], csrf=False)
    def unregister_mobile_device(self, **kwargs):
        try:
            radiologist, hospital, error = self._get_token_record()
            if error:
                return error
            if hospital or not radiologist:
                return request.make_json_response({
                    "status": "error",
                    "message": "Only radiologists can unregister a mobile device"
                }, status=403)

            data = request.httprequest.json if request.httprequest.is_json else {}
            token = (data.get("fcm_token") or "").strip() if data else ""

            domain = [("radiologist_id", "=", radiologist.id)]
            if token:
                domain.append(("fcm_token", "=", token))

            devices = request.env["radiology.mobile.device"].sudo().search(domain)
            if devices:
                devices.write({"is_active": False})

            return request.make_json_response({
                "status": "ok",
                "data": {"count": len(devices)},
            })
        except Exception as e:
            _logger.error("Error unregistering mobile device: %s", str(e))
            return request.make_json_response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=500)

    # ======================================================================== #
    #                                    GET                                   #
    # ======================================================================== #

    @http.route('/api/<string:model>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_model_data(self, model):
        try:
            records = request.env[model]
        except KeyError:
            msg = f"Le modèle '{model}' n'existe pas."
            return request.make_response(msg, headers=[('Content-Type', 'application/json')], status=404)

        # Lire les paramètres depuis l'URL
        params = request.httprequest.args
        context = {}

        if "context" in params:
            try:
                context = ast.literal_eval(params["context"])
            except:
                context = {}

        # Paramètre query
        if "query" in params:
            query = params["query"]
        else:
            query = "{id,name}"

        # Paramètre order
        if "order" in params:
            orders = params["order"]
        else:
            orders = ""

        # Paramètre domain (remplace filter)
        domain = []
        if "domain" in params:
            try:
                domain = ast.literal_eval(params["domain"])
            except:
                domain = []

        # Recherche avec domain
        records = records.with_context(**context).search(domain, order=orders)
        total_count = len(records)

        # Pagination
        prev_page = None
        next_page = None
        total_page_number = 1
        current_page = 1

        if "page_size" in params:
            page_size = int(params["page_size"])
            total_page_number = math.ceil(total_count / page_size) if page_size else 1

            if "page" in params:
                current_page = int(params["page"])
            else:
                current_page = 1

            start = page_size * (current_page - 1)
            stop = current_page * page_size
            records = records[start:stop]
            next_page = current_page + 1 if 0 < current_page + 1 <= total_page_number else None
            prev_page = current_page - 1 if 0 < current_page - 1 <= total_page_number else None

        # Limite
        if "limit" in params:
            limit = int(params["limit"])
            records = records[0:limit]
            total_count = min(total_count, limit)

        # Sérialisation
        try:
            serializer = Serializer(records, query, many=True)
            data = serializer.data
        except (SyntaxError, QueryFormatError) as e:
            return request.make_response(
                json.dumps({"error": str(e)}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # Réponse
        res = {
            "count": total_count,
            "prev": prev_page,
            "current": current_page,
            "next": next_page,
            "total_pages": total_page_number,
            "result": data
        }

        return request.make_response(
            json.dumps(res),
            headers=[('Content-Type', 'application/json')]
        )
    @http.route('/api/<string:model>/<int:rec_id>', type='json', auth='user', methods=['GET'], csrf=False)
    def get_model_rec(self, model, rec_id):
        try:
            records = request.env[model].search([])
        except KeyError:
            msg = "The model `%s` does not exist." % model
            raise exceptions.ValidationError(msg)

        params = request.get_http_params()

        if "query" in params:
            query = params["query"]
        else:
            query = "{*}"

        # TODO: Handle the error raised by `ensure_one`
        try:
            record = records.browse([rec_id]).exists().ensure_one()
            serializer = Serializer(record, query)
            data = serializer.data
        except ValueError:
            msg = "Record with id `%s` does not exist." % rec_id
            raise exceptions.ValidationError(msg)

        return data

    # ======================================================================== #
    #                                   POST                                   #
    # ======================================================================== #

    @http.route('/api/<string:model>/', type='json', auth="user", methods=['POST'], csrf=False)
    def post_model_data(self, model, **post):
        try:
            data = post['data']
        except KeyError:
            msg = "`data` parameter is not found on POST request body"
            raise exceptions.ValidationError(msg)

        try:
            model_to_post = request.env[model]
        except KeyError:
            msg = "The model `%s` does not exist." % model
            raise exceptions.ValidationError(msg)

        # TODO: Handle data validation

        if "context" in post:
            context = post["context"]
            record = model_to_post.with_context(**context).create(data)
        else:
            record = model_to_post.create(data)
        return record.id

    # This is for single record update
    @http.route('/api/<string:model>/<int:rec_id>/', type='json', auth="user", methods=['PUT'], csrf=False)
    def put_model_record(self, model, rec_id, **post):
        try:
            data = post['data']
        except KeyError:
            msg = "`data` parameter is not found on PUT request body"
            raise exceptions.ValidationError(msg)

        try:
            model_to_put = request.env[model]
        except KeyError:
            msg = "The model `%s` does not exist." % model
            raise exceptions.ValidationError(msg)

        if "context" in post:
            # TODO: Handle error raised by `ensure_one`
            rec = model_to_put.with_context(**post["context"]) \
                .browse(rec_id).ensure_one()
        else:
            rec = model_to_put.browse(rec_id).ensure_one()

        # TODO: Handle data validation
        for field in data:
            if isinstance(data[field], dict):
                operations = []
                for operation in data[field]:
                    if operation == "push":
                        operations.extend(
                            (4, rec_id, _)
                            for rec_id
                            in data[field].get("push")
                        )
                    elif operation == "pop":
                        operations.extend(
                            (3, rec_id, _)
                            for rec_id
                            in data[field].get("pop")
                        )
                    elif operation == "delete":
                        operations.extend(
                            (2, rec_id, _)
                            for rec_id
                            in data[field].get("delete")
                        )
                    else:
                        data[field].pop(operation)  # Invalid operation

                data[field] = operations
            elif isinstance(data[field], list):
                data[field] = [(6, _, data[field])]  # Replace operation
            else:
                pass

        try:
            return rec.write(data)
        except Exception as e:
            # TODO: Return error message(e.msg) on a response
            return False

    @http.route('/object/<string:model>/<string:function>', type='json', auth='user', methods=["POST"], csrf=False)
    def call_model_function(self, model, function, **post):
        args = []
        kwargs = {}
        check_method_name(function)
        if "args" in post:
            args = post["args"]
        if "kwargs" in post:
            kwargs = post["kwargs"]
        model = request.env[model]
        result = getattr(model, function)(*args, **kwargs)
        return result

    @http.route('/object/<string:model>/<int:rec_id>/<string:function>', type='json', auth='user', methods=["POST"],
                csrf=False)
    def call_obj_function(self, model, rec_id, function, **post):
        args = []
        kwargs = {}
        check_method_name(function)
        if "args" in post:
            args = post["args"]
        if "kwargs" in post:
            kwargs = post["kwargs"]
        obj = request.env[model].browse(rec_id).ensure_one()
        result = getattr(obj, function)(*args, **kwargs)
        return result

    @http.route('/record_filter/<string:model>/<string:function>', type='json', auth='user', methods=["POST"],
                csrf=False)
    def call_model_function(self, model, function, **post):
        args = []
        kwargs = {}
        check_method_name(function)
        if "args" in post:
            args = post["args"]
        if "kwargs" in post:
            kwargs = post["kwargs"]
        if "query" in post:
            query = post["query"]
        else:
            query = "{id}"

        if "limit" in post:
            limit = int(post["limit"])
        else:
            limit = None

        model = request.env[model]
        records = getattr(model, function)(*args, **kwargs)

        if limit is not None:
            records = records[0:limit]

        serializer = Serializer(records, query, many=True)
        data = serializer.data

        return data

    # ======================================================================== #
    #                                    PUT                                   #
    # ======================================================================== #

    # This is for bulk update
    @http.route('/api/<string:model>/', type='json', auth="user", methods=['PUT'], csrf=False)
    def put_model_records(self, model, **post):
        try:
            data = post['data']
        except KeyError:
            msg = "`data` parameter is not found on PUT request body"
            raise exceptions.ValidationError(msg)

        try:
            model_to_put = request.env[model]
        except KeyError:
            msg = "The model `%s` does not exist." % model
            raise exceptions.ValidationError(msg)

        # TODO: Handle errors on filter
        filters = post["filter"]

        if "context" in post:
            recs = model_to_put.with_context(**post["context"]) \
                .search(filters)
        else:
            recs = model_to_put.search(filters)

        # TODO: Handle data validation
        for field in data:
            if isinstance(data[field], dict):
                operations = []
                for operation in data[field]:
                    if operation == "push":
                        operations.extend(
                            (4, rec_id, _)
                            for rec_id
                            in data[field].get("push")
                        )
                    elif operation == "pop":
                        operations.extend(
                            (3, rec_id, _)
                            for rec_id
                            in data[field].get("pop")
                        )
                    elif operation == "delete":
                        operations.extend(
                            (2, rec_id, _)
                            for rec_id in
                            data[field].get("delete")
                        )
                    else:
                        pass  # Invalid operation

                data[field] = operations
            elif isinstance(data[field], list):
                data[field] = [(6, _, data[field])]  # Replace operation
            else:
                pass

        if recs.exists():
            try:
                return recs.write(data)
            except Exception as e:
                # TODO: Return error message(e.msg) on a response
                return False
        else:
            # No records to update
            return True

    # ======================================================================== #
    #                                  DELETE                                  #
    # ======================================================================== #

    # This is for bulk deletion
    @http.route('/api/<string:model>/', type='http', auth="user", methods=['DELETE'], csrf=False)
    def delete_model_records(self, model, **post):
        filters = json.loads(post["filter"])

        try:
            model_to_del_rec = request.env[model]
        except KeyError as e:
            msg = "The model `%s` does not exist." % model
            res = error_response(e, msg)
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )

        # TODO: Handle error raised by `filters`
        recs = model_to_del_rec.search(filters)

        try:
            is_deleted = recs.unlink()
            res = {
                "result": is_deleted
            }
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )
        except Exception as e:
            res = error_response(e, str(e))
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )

    # This is for deleting one record
    @http.route('/api/<string:model>/<int:rec_id>/', type='http', auth="user", methods=['DELETE'], csrf=False)
    def delete_model_record(self, model, rec_id, **post):
        try:
            model_to_del_rec = request.env[model]
        except KeyError as e:
            msg = "The model `%s` does not exist." % model
            res = error_response(e, msg)
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )

        # TODO: Handle error raised by `ensure_one`
        rec = model_to_del_rec.browse(rec_id).ensure_one()

        try:
            is_deleted = rec.unlink()
            res = {
                "result": is_deleted
            }
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )
        except Exception as e:
            res = error_response(e, str(e))
            return http.Response(
                json.dumps(res),
                status=200,
                mimetype='application/json'
            )


