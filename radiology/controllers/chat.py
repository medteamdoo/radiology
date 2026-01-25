# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.tools.misc import format_datetime


class PortalChatController(http.Controller):

    @http.route('/my/chat', type='http', auth='user', website=True)
    def portal_chat(self, **kw):
        hospital = request.env['radiology.hospital'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)

        conversations = request.env['radiology.chat.conversation'].sudo().search([
            ('hospital_id', '=', hospital.id)
        ])

        return request.render('radiology.portal_chat', {
            'hospital': hospital,
            'conversations': conversations,
        })

    @http.route('/my/chat/start/<int:radiologist_id>', type='http', auth='user', website=True)
    def start_chat(self, radiologist_id, **kw):
        hospital = request.env['radiology.hospital'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)

        conv = request.env['radiology.chat.conversation'].sudo().search([
            ('hospital_id', '=', hospital.id),
            ('radiologist_id', '=', radiologist_id),
        ], limit=1)

        if not conv:
            conv = request.env['radiology.chat.conversation'].sudo().create({
                'hospital_id': hospital.id,
                'radiologist_id': radiologist_id,
            })

        return request.redirect('/my/chat/%s' % conv.id)

    @http.route('/my/chat/<int:conversation_id>', type='http', auth='user', website=True)
    def chat_room(self, conversation_id, **kw):
        conv = request.env['radiology.chat.conversation'].sudo().browse(conversation_id)

        messages = request.env['radiology.chat.message'].sudo().search([
            ('conversation_id', '=', conv.id)
        ], order='create_date asc')
        tz = request.env.user.tz or 'UTC'
        msg_vals = []
        for m in messages:
            msg_vals.append({
                'id': m.id,
                'message': m.message,
                'sender_type': m.sender_type,
                'date': format_datetime(request.env, m.create_date, tz=tz) if m.create_date else '',
            })

        def _float_to_hhmm(x):
            if x is None:
                return "—"
            h = int(x)
            m = int(round((x - h) * 60))
            if m == 60:
                h += 1
                m = 0
            return f"{h:02d}:{m:02d}"

        day_map = {
            '0': 'Lundi', '1': 'Mardi', '2': 'Mercredi', '3': 'Jeudi',
            '4': 'Vendredi', '5': 'Samedi', '6': 'Dimanche',
        }

        r = conv.radiologist_id
        avs = request.env['radiology.radiologist.availability'].sudo().search([
            ('radiologist_id', '=', r.id),
            ('active', '=', True),
        ], order='weekday, start_time')

        availabilities = []
        for a in avs:
            availabilities.append({
                'day': day_map.get(a.weekday, a.weekday),
                'time': f"{_float_to_hhmm(a.start_time)} – {_float_to_hhmm(a.end_time)}",
                'is_night': bool(a.is_night),
                'is_weekend': bool(a.is_weekend),
            })

        return request.render('radiology.portal_chat_room', {
            'conversation': conv,
            'messages': msg_vals,
            'availabilities': availabilities,
        })

    @http.route('/my/chat/send', type='http', auth='user', website=True, methods=['POST'])
    def chat_send(self, conversation_id, message, **kw):
        hospital = request.env['radiology.hospital'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1
        )
        if not hospital:
            return request.redirect('/my/chat')

        conv = request.env['radiology.chat.conversation'].sudo().browse(int(conversation_id))
        if not conv.exists() or conv.hospital_id.id != hospital.id:
            return request.not_found()

        request.env['radiology.chat.message'].sudo().create({
            'conversation_id': conv.id,
            'sender_type': 'hospital',
            'sender_id': hospital.id,
            'message': message,
        })

        return request.redirect('/my/chat/%s' % conv.id)



    @http.route('/my/chat/send_json', type='json', auth='user', website=True, csrf=True)
    def chat_send_json(self, conversation_id, message):
        hospital = request.env['radiology.hospital'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1
        )
        if not hospital:
            return {'ok': False, 'error': 'no_hospital'}

        conv = request.env['radiology.chat.conversation'].sudo().browse(int(conversation_id))
        if not conv.exists() or conv.hospital_id.id != hospital.id:
            return {'ok': False, 'error': 'forbidden'}

        msg = request.env['radiology.chat.message'].sudo().create({
            'conversation_id': conv.id,
            'sender_type': 'hospital',
            'sender_id': hospital.id,
            'message': message,
        })
        tz = request.env.user.tz or 'UTC'
        return {
            'ok': True,
            'id': msg.id,
            'message': msg.message,
            'sender_type': msg.sender_type,
            'date': format_datetime(request.env, msg.create_date,tz=tz) if msg.create_date else '',
        }

    @http.route('/my/chat/fetch_json', type='json', auth='user', website=True, csrf=True)
    def chat_fetch_json(self, conversation_id, last_id=0):
        hospital = request.env['radiology.hospital'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1
        )
        if not hospital:
            return {'ok': False, 'error': 'no_hospital'}

        conv = request.env['radiology.chat.conversation'].sudo().browse(int(conversation_id))
        if not conv.exists() or conv.hospital_id.id != hospital.id:
            return {'ok': False, 'error': 'forbidden'}

        domain = [('conversation_id', '=', conv.id)]
        if last_id:
            domain.append(('id', '>', int(last_id)))

        msgs = request.env['radiology.chat.message'].sudo().search(domain, order='id asc', limit=50)
        tz = request.env.user.tz or 'UTC'

        return {
            'ok': True,
            'messages': [{
            'id': m.id,
            'message': m.message,
            'sender_type': m.sender_type,
            'date': format_datetime(request.env, m.create_date, tz=tz) if m.create_date else '',
        } for m in msgs]}




