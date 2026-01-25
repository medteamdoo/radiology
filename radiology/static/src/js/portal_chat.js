/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import {jsonrpc} from "@web/core/network/rpc_service";

publicWidget.registry.RadiologyPortalChat = publicWidget.Widget.extend({
    selector: ".o_portal_chat_room",
    events: {
        "submit #chat_form": "_onSubmit",
    },

    start() {
        this.$box = this.$("#chat_box");
        this.$input = this.$("#chat_input");
        this.convId = parseInt(this.$("#conv_id").val());
        this.lastId = this._getLastId();

        this._scrollBottom();
        this._pollTimer = setInterval(() => this._fetchNew(), 2000);

        return this._super(...arguments);
    },

    destroy() {
        if (this._pollTimer) clearInterval(this._pollTimer);
        return this._super(...arguments);
    },

    _getLastId() {
        const $last = this.$box.find("[data-id]").last();
        return $last.length ? parseInt($last.attr("data-id")) : 0;
    },

    _scrollBottom() {
        if (this.$box?.length) this.$box.scrollTop(this.$box[0].scrollHeight);
    },

    _appendMessage(m) {
        const isMe = (m.sender_type === "hospital");
        const who = isMe ? "Vous" : "Radiologue";
        const safe = (m.message || "").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

        // date déjà prête si tu l’envoies (voir partie B)
        const dateTxt = m.date || (m.date || "");

        this.$box.append(`
      <div class="rlx-row ${isMe ? 'me' : 'other'}">
        <div class="rlx-bubble ${isMe ? 'me' : 'other'}" data-id="${m.id}">
          <div class="rlx-meta">
            <span>${who}</span>
            <span class="rlx-date">${dateTxt}</span>
          </div>
          <div class="rlx-text">${safe}</div>
        </div>
      </div>
    `);

        this.lastId = Math.max(this.lastId, m.id);
        this._scrollBottom();
    }
    ,

    async _onSubmit(ev) {
        ev.preventDefault();

        const text = (this.$input.val() || "").trim();
        if (!text) return;

        const res = await jsonrpc("/my/chat/send_json", {
            conversation_id: this.convId,
            message: text,
        });

        if (res?.ok) {
            this.$input.val("");
            this._appendMessage(res);
        } else {
            console.error("send_json error:", res);
        }
    },

    async _fetchNew() {
        const res = await jsonrpc("/my/chat/fetch_json", {
            conversation_id: this.convId,
            last_id: this.lastId,
        });

        if (res?.ok && res.messages?.length) {
            res.messages.forEach((m) => this._appendMessage(m));
        }
    },
});
