/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.RadioLinkDemoPage = publicWidget.Widget.extend({
    selector: ".rl-demo-page",

    start() {
        this._bindScrollLinks();
        this._initRevealObserver();
        return this._super(...arguments);
    },

    _bindScrollLinks() {
        this.el.querySelectorAll("[data-rl-demo-scroll]").forEach((link) => {
            link.addEventListener("click", (event) => {
                const href = link.getAttribute("href") || "";
                if (!href.startsWith("#")) {
                    return;
                }
                const target = document.querySelector(href);
                if (!target) {
                    return;
                }
                event.preventDefault();
                target.scrollIntoView({
                    behavior: "smooth",
                    block: "start",
                });
            });
        });
    },

    _initRevealObserver() {
        const items = [...this.el.querySelectorAll(".rl-demo-reveal")];
        if (!items.length) {
            return;
        }

        if (!("IntersectionObserver" in window)) {
            items.forEach((item) => item.classList.add("is-visible"));
            return;
        }

        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) {
                    return;
                }
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, {
            threshold: 0.14,
            rootMargin: "0px 0px -8% 0px",
        });

        items.forEach((item) => observer.observe(item));
    },
});
