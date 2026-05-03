/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { jsonrpc } from "@web/core/network/rpc_service";

function escapeHtml(value) {
    return `${value || ""}`
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#39;");
}

publicWidget.registry.RadiologyHeaderMessages = publicWidget.Widget.extend({
    selector: ".o_radiology_header_messages",

    start() {
        this.$badge = this.$("[data-role='message-badge']");
        this.$count = this.$("[data-role='message-count']");
        this.$list = this.$("[data-role='message-list']");
        this._pollTimer = setInterval(() => this._refresh(), 5000);
        this._refresh();
        return this._super(...arguments);
    },

    destroy() {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
        }
        return this._super(...arguments);
    },

    async _refresh() {
        try {
            const payload = await jsonrpc("/my/chat/header_json", {});
            if (!payload?.ok) {
                return;
            }
            this._render(payload);
        } catch (error) {
            console.error("header_json error:", error);
        }
    },

    _render(payload) {
        const unreadCount = parseInt(payload.unread_count || 0, 10);
        if (unreadCount > 0) {
            this.$badge.removeClass("d-none").text(unreadCount);
        } else {
            this.$badge.addClass("d-none").text("0");
        }

        this.$count.text(`${unreadCount} non lus`);

        const conversations = payload.conversations || [];
        if (!conversations.length) {
            this.$list.html(`
                <div class="rl-message-empty">
                    Aucun message pour le moment.
                </div>
            `);
            return;
        }

        const itemsHtml = conversations.map((conversation) => {
            const unreadBadge = conversation.unread_count > 0
                ? `<span class="rl-message-item-badge">${conversation.unread_count}</span>`
                : "";
            return `
                <a href="${escapeHtml(conversation.url)}" class="dropdown-item rl-message-item">
                    <span class="rl-message-avatar">
                        <img src="${escapeHtml(conversation.radiologist_avatar_url || "/web/static/img/user_menu_avatar.png")}" alt="${escapeHtml(conversation.radiologist_name)}" />
                    </span>
                    <span class="rl-message-content">
                        <strong class="rl-message-title">${escapeHtml(conversation.radiologist_name)}</strong>
                        <span class="rl-message-preview">${escapeHtml(conversation.last_message)}</span>
                        <span class="rl-message-date">${escapeHtml(conversation.last_message_date)}</span>
                    </span>
                    ${unreadBadge}
                </a>
            `;
        }).join("");

        this.$list.html(`
            ${itemsHtml}
            <div class="rl-message-menu-footer">
                <a href="/my/chat" class="btn btn-sm rl-message-link">Voir tous les messages</a>
            </div>
        `);
    },
});
