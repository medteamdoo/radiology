/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

const OPEN_CLASS = "is-open";
const LIVE_CLASS = "is-live";
const CLOSING_CLASS = "is-closing";
const BODY_LOCK_CLASS = "rv-match-modal-open";

publicWidget.registry.RVMissionMatchModal = publicWidget.Widget.extend({
    selector: ".rv-mission-detail-page",
    events: {
        "click [data-rv-match-open]": "_onOpenClick",
        "click [data-rv-match-close]": "_onCloseClick",
    },

    start() {
        this.activeModal = null;
        this._boundKeydown = this._onKeydown.bind(this);
        document.addEventListener("keydown", this._boundKeydown);
        return this._super(...arguments);
    },

    destroy() {
        document.removeEventListener("keydown", this._boundKeydown);
        document.documentElement.classList.remove(BODY_LOCK_CLASS);
        return this._super(...arguments);
    },

    _getModal(matchId) {
        return this.el.querySelector(`[data-rv-match-modal="${matchId}"]`);
    },

    _onOpenClick(ev) {
        const trigger = ev.currentTarget;
        if (!trigger) {
            return;
        }
        if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || trigger.target === "_blank") {
            return;
        }

        const matchId = trigger.dataset.rvMatchOpen;
        const modal = this._getModal(matchId);
        if (!modal) {
            return;
        }

        ev.preventDefault();
        this._openModal(modal);
    },

    _onCloseClick(ev) {
        ev.preventDefault();
        const modal = ev.currentTarget.closest(".rv-match-modal");
        this._closeModal(modal);
    },

    _onKeydown(ev) {
        if (ev.key !== "Escape" || !this.activeModal) {
            return;
        }
        this._closeModal(this.activeModal);
    },

    _openModal(modal) {
        if (!modal) {
            return;
        }

        if (this.activeModal && this.activeModal !== modal) {
            this._closeModal(this.activeModal, {immediate: true});
        }

        clearTimeout(modal._rvCloseTimer);
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
        modal.classList.remove(CLOSING_CLASS, OPEN_CLASS, LIVE_CLASS);
        void modal.offsetWidth;

        this.activeModal = modal;
        document.documentElement.classList.add(BODY_LOCK_CLASS);

        requestAnimationFrame(() => {
            modal.classList.add(OPEN_CLASS);
            window.setTimeout(() => {
                modal.classList.add(LIVE_CLASS);
            }, 70);
        });

        const closeButton = modal.querySelector(".rv-match-modal-close");
        closeButton?.focus({preventScroll: true});
    },

    _closeModal(modal, {immediate = false} = {}) {
        if (!modal) {
            return;
        }

        clearTimeout(modal._rvCloseTimer);
        modal.classList.remove(LIVE_CLASS);

        if (immediate) {
            modal.classList.remove(OPEN_CLASS, CLOSING_CLASS);
            modal.hidden = true;
            modal.setAttribute("aria-hidden", "true");
            if (this.activeModal === modal) {
                this.activeModal = null;
            }
            document.documentElement.classList.remove(BODY_LOCK_CLASS);
            return;
        }

        modal.classList.add(CLOSING_CLASS);
        modal._rvCloseTimer = window.setTimeout(() => {
            modal.classList.remove(OPEN_CLASS, CLOSING_CLASS);
            modal.hidden = true;
            modal.setAttribute("aria-hidden", "true");
            if (this.activeModal === modal) {
                this.activeModal = null;
            }
            document.documentElement.classList.remove(BODY_LOCK_CLASS);
        }, 260);
    },
});
