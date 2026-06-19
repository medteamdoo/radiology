/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import {jsonrpc} from "@web/core/network/rpc_service";

publicWidget.registry.RadiologyPortalChat = publicWidget.Widget.extend({
    selector: ".o_portal_chat_room",
    events: {
        "submit #chat_form": "_onSubmit",
        "click .rv-messages-conversation": "_onConversationClick",
    },

    start() {
        this._refreshThreadRefs();

        this._scrollBottom();
        this._pollTimer = setInterval(() => this._fetchNew(), 2000);
        this._boundPopState = this._onPopState.bind(this);
        window.addEventListener("popstate", this._boundPopState);

        return this._super(...arguments);
    },

    destroy() {
        if (this._pollTimer) clearInterval(this._pollTimer);
        if (this._boundPopState) {
            window.removeEventListener("popstate", this._boundPopState);
        }
        return this._super(...arguments);
    },

    _refreshThreadRefs() {
        this.$layout = this.$(".rv-messages-layout");
        this.$box = this.$("#chat_box");
        this.$input = this.$("#chat_input");
        const convRaw = this.$("#conv_id").val();
        this.convId = convRaw ? parseInt(convRaw, 10) : 0;
        this.lastId = this._getLastId();
    },

    _getLastId() {
        if (!this.$box?.length) return 0;
        const $last = this.$box.find("[data-id]").last();
        return $last.length ? parseInt($last.attr("data-id")) : 0;
    },

    _scrollBottom() {
        if (this.$box?.length) this.$box.scrollTop(this.$box[0].scrollHeight);
    },

    _appendMessage(m) {
        if (!this.$box?.length) return;

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
        if (!this.convId || !this.$input?.length) return;

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

    async _onConversationClick(ev) {
        const link = ev.currentTarget;
        if (!link) return;
        if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;

        const targetUrl = new URL(link.href, window.location.origin);
        if (!targetUrl.search && window.location.search) {
            targetUrl.search = window.location.search;
        }

        if (link.classList.contains("is-active") && targetUrl.pathname === window.location.pathname && targetUrl.search === window.location.search) {
            ev.preventDefault();
            return;
        }

        ev.preventDefault();
        await this._loadConversation(targetUrl.toString(), {pushState: true});
    },

    async _loadConversation(url, {pushState = false} = {}) {
        const panel = this.el.querySelector(".rv-messages-thread-panel");
        const layout = this.el.querySelector(".rv-messages-layout");
        if (!layout) {
            window.location.href = url;
            return;
        }

        panel?.classList.add("is-loading");
        layout.classList.add("is-loading");

        try {
            const response = await fetch(url, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, "text/html");
            const nextLayout = doc.querySelector(".rv-messages-layout");

            if (!nextLayout) {
                throw new Error("Missing messages layout in response");
            }

            layout.replaceWith(nextLayout);
            this._refreshThreadRefs();
            this._scrollBottom();

            if (pushState) {
                window.history.pushState({url}, "", url);
            }
        } catch (error) {
            console.error("conversation switch failed:", error);
            window.location.href = url;
        } finally {
            const currentLayout = this.el.querySelector(".rv-messages-layout");
            const currentPanel = this.el.querySelector(".rv-messages-thread-panel");
            currentLayout?.classList.remove("is-loading");
            currentPanel?.classList.remove("is-loading");
        }
    },

    async _onPopState() {
        if (!window.location.pathname.startsWith("/my/chat")) return;
        await this._loadConversation(window.location.href, {pushState: false});
    },

    async _fetchNew() {
        if (!this.convId || !this.$box?.length) return;

        const res = await jsonrpc("/my/chat/fetch_json", {
            conversation_id: this.convId,
            last_id: this.lastId,
        });

        if (res?.ok && res.messages?.length) {
            res.messages.forEach((m) => this._appendMessage(m));
        }
    },
});
