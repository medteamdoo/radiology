# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.tools.misc import format_datetime


class PortalChatController(http.Controller):
    def _get_portal_hospital(self):
        return request.env['radiology.hospital'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)

    def _mark_conversation_read_for_hospital(self, conversation):
        if not conversation or not conversation.exists():
            return
        unread_messages = request.env['radiology.chat.message'].sudo().search([
            ('conversation_id', '=', conversation.id),
            ('sender_type', '=', 'radiologist'),
            ('is_read_by_hospital', '=', False),
        ])
        if unread_messages:
            unread_messages.write({'is_read_by_hospital': True})

    def _get_header_messages_payload(self, hospital):
        Message = request.env['radiology.chat.message'].sudo()
        Conversation = request.env['radiology.chat.conversation'].sudo()

        if not hospital:
            return {
                'ok': True,
                'unread_count': 0,
                'conversations': [],
            }

        conversations = Conversation.search([
            ('hospital_id', '=', hospital.id),
        ], order='last_message_date desc, id desc', limit=20)

        items = []
        total_unread = 0
        for conversation in conversations:
            unread_count = Message.search_count([
                ('conversation_id', '=', conversation.id),
                ('sender_type', '=', 'radiologist'),
                ('is_read_by_hospital', '=', False),
            ])
            total_unread += unread_count
            items.append({
                'id': conversation.id,
                'radiologist_name': conversation.radiologist_id.display_name or 'Radiologue',
                'radiologist_avatar_url': f'/web/image/radiology.radiologist/{conversation.radiologist_id.id}/image_1920' if conversation.radiologist_id and conversation.radiologist_id.image_1920 else '/web/static/img/user_menu_avatar.png',
                'last_message': conversation.last_message or 'Aucun message',
                'last_message_date': format_datetime(request.env, conversation.last_message_date, tz=request.env.user.tz or 'UTC') if conversation.last_message_date else '',
                'last_message_sort': conversation.last_message_date.isoformat() if conversation.last_message_date else '',
                'unread_count': unread_count,
                'url': f'/my/chat/{conversation.id}',
            })

        items.sort(
            key=lambda item: (
                item['unread_count'] > 0,
                item['last_message_sort'] or '',
            ),
            reverse=True,
        )

        for item in items:
            item.pop('last_message_sort', None)

        return {
            'ok': True,
            'unread_count': total_unread,
            'conversations': items[:6],
        }

    @http.route('/my/chat', type='http', auth='user', website=True)
    def portal_chat(self, **kw):
        hospital = self._get_portal_hospital()

        if not hospital:
            return request.render('radiology.portal_chat', {
                'hospital': hospital,
                'conversations': request.env['radiology.chat.conversation'],
            })

        conversations = request.env['radiology.chat.conversation'].sudo().search([
            ('hospital_id', '=', hospital.id)
        ])

        return request.render('radiology.portal_chat', {
            'hospital': hospital,
            'conversations': conversations,
        })

    @http.route('/my/chat/start/<int:radiologist_id>', type='http', auth='user', website=True)
    def start_chat(self, radiologist_id, **kw):
        hospital = self._get_portal_hospital()
        if not hospital:
            return request.redirect('/my/chat')

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
        hospital = self._get_portal_hospital()
        if not hospital:
            return request.redirect('/my/chat')

        conv = request.env['radiology.chat.conversation'].sudo().browse(conversation_id)
        if not conv.exists() or conv.hospital_id.id != hospital.id:
            return request.not_found()

        self._mark_conversation_read_for_hospital(conv)

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
        hospital = self._get_portal_hospital()
        if not hospital:
            return request.redirect('/my/chat')

        conv = request.env['radiology.chat.conversation'].sudo().browse(int(conversation_id))
        if not conv.exists() or conv.hospital_id.id != hospital.id:
            return request.not_found()

        message = (message or '').strip()
        if not message:
            return request.redirect('/my/chat/%s' % conv.id)

        request.env['radiology.chat.message'].sudo().create({
            'conversation_id': conv.id,
            'sender_type': 'hospital',
            'sender_id': hospital.id,
            'message': message,
        })

        return request.redirect('/my/chat/%s' % conv.id)



    @http.route('/my/chat/send_json', type='json', auth='user', website=True, csrf=True)
    def chat_send_json(self, conversation_id, message):
        hospital = self._get_portal_hospital()
        if not hospital:
            return {'ok': False, 'error': 'no_hospital'}

        conv = request.env['radiology.chat.conversation'].sudo().browse(int(conversation_id))
        if not conv.exists() or conv.hospital_id.id != hospital.id:
            return {'ok': False, 'error': 'forbidden'}

        message = (message or '').strip()
        if not message:
            return {'ok': False, 'error': 'empty_message'}

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
        hospital = self._get_portal_hospital()
        if not hospital:
            return {'ok': False, 'error': 'no_hospital'}

        conv = request.env['radiology.chat.conversation'].sudo().browse(int(conversation_id))
        if not conv.exists() or conv.hospital_id.id != hospital.id:
            return {'ok': False, 'error': 'forbidden'}

        domain = [('conversation_id', '=', conv.id)]
        if last_id:
            domain.append(('id', '>', int(last_id)))

        msgs = request.env['radiology.chat.message'].sudo().search(domain, order='id asc', limit=50)
        self._mark_conversation_read_for_hospital(conv)
        tz = request.env.user.tz or 'UTC'

        return {
            'ok': True,
            'messages': [{
            'id': m.id,
            'message': m.message,
            'sender_type': m.sender_type,
            'date': format_datetime(request.env, m.create_date, tz=tz) if m.create_date else '',
        } for m in msgs]}

    @http.route('/my/chat/header_json', type='json', auth='user', website=True, csrf=False)
    def chat_header_json(self):
        hospital = self._get_portal_hospital()
        return self._get_header_messages_payload(hospital)




