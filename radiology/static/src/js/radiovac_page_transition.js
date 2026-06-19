/** @odoo-module **/

const TRANSITION_CLASS = "rv-page-transition-active";
const REVEAL_CLASS = "is-visible";

function ensureTransitionLayer() {
    if (document.querySelector(".rv-page-transition-layer")) {
        return;
    }

    const layer = document.createElement("div");
    layer.className = "rv-page-transition-layer";
    document.body.appendChild(layer);
}

function bindTransitionLinks() {
    document.querySelectorAll('a[data-rv-transition-link="true"]').forEach((link) => {
        if (link.dataset.rvTransitionBound === "true") {
            return;
        }

        link.dataset.rvTransitionBound = "true";
        link.addEventListener("click", (event) => {
            if (
                event.defaultPrevented ||
                event.button !== 0 ||
                event.metaKey ||
                event.ctrlKey ||
                event.shiftKey ||
                event.altKey ||
                link.target === "_blank" ||
                link.hasAttribute("download")
            ) {
                return;
            }

            const href = link.getAttribute("href");
            if (!href || href.startsWith("#")) {
                return;
            }

            const nextUrl = new URL(href, window.location.href);
            const currentUrl = new URL(window.location.href);
            const samePage = nextUrl.pathname === currentUrl.pathname && nextUrl.search === currentUrl.search;

            if (nextUrl.origin !== currentUrl.origin || (samePage && nextUrl.hash)) {
                return;
            }

            event.preventDefault();
            document.documentElement.classList.add(TRANSITION_CLASS);
            window.setTimeout(() => {
                window.location.assign(nextUrl.toString());
            }, 420);
        });
    });
}

function revealSections() {
    const items = [...document.querySelectorAll("[data-rv-reveal]")];
    if (!items.length) {
        return;
    }

    if (!("IntersectionObserver" in window)) {
        items.forEach((item) => item.classList.add(REVEAL_CLASS));
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) {
                return;
            }

            entry.target.classList.add(REVEAL_CLASS);
            observer.unobserve(entry.target);
        });
    }, {
        threshold: 0.18,
        rootMargin: "0px 0px -48px 0px",
    });

    items.forEach((item) => observer.observe(item));
}

function initRadioVacTransitions() {
    if (!document.body) {
        return;
    }

    document.documentElement.classList.add("rv-page-enhanced");
    ensureTransitionLayer();
    bindTransitionLinks();
    revealSections();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initRadioVacTransitions);
} else {
    initRadioVacTransitions();
}

window.addEventListener("pageshow", () => {
    document.documentElement.classList.remove(TRANSITION_CLASS);
});
