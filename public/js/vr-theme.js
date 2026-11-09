
(() => {
    "use strict";

    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

    function refreshIcons() {
        if (window.lucide && typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons();
        }
    }

    function setTheme(theme) {
        const safeTheme = theme === "dark" ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", safeTheme);
        const label = $("#vtxThemeLabel");
        const icon = $("#vtxThemeIcon");
        const metaTheme = $('meta[name="theme-color"]');
        if (label) label.textContent = safeTheme === "dark" ? "Crystal Light" : "Neon Dark";
        if (icon) icon.setAttribute("data-lucide", safeTheme === "dark" ? "sun" : "moon");
        if (metaTheme) metaTheme.setAttribute("content", safeTheme === "dark" ? "#050711" : "#f2f5ff");
        try { localStorage.setItem("vrtech-theme", safeTheme); } catch (_) { /* Storage can be unavailable in private contexts. */ }
        refreshIcons();
    }

    function initializeTheme() {
        let saved = null;
        try { saved = localStorage.getItem("vrtech-theme"); } catch (_) { /* Use light theme. */ }
        setTheme(saved === "dark" ? "dark" : "light");
        const toggle = $("#vtxThemeToggle");
        if (toggle) {
            toggle.addEventListener("click", () => {
                setTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
            });
        }
    }

    function initializeMobileNavigation() {
        const button = $("#vtxMobileToggle");
        const navigation = $("#vtxNavigation");
        if (!button || !navigation) return;

        const closeMenu = () => {
            navigation.classList.remove("is-open");
            button.setAttribute("aria-expanded", "false");
            button.setAttribute("aria-label", "Open navigation");
        };
        button.addEventListener("click", () => {
            const open = navigation.classList.toggle("is-open");
            button.setAttribute("aria-expanded", String(open));
            button.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
        });
        $$('a', navigation).forEach(link => link.addEventListener("click", closeMenu));
        window.addEventListener("resize", () => { if (window.innerWidth > 980) closeMenu(); });
    }

    function initializeSearch() {
        const button = $("#vtxSearchButton");
        const startSearch = () => {
            const query = window.prompt("Search VR Tech Solutions");
            if (query && query.trim()) {
                const url = window.VRTECH && window.VRTECH.searchUrl;
                if (url) window.location.href = `${url}?q=${encodeURIComponent(query.trim())}`;
            }
        };
        if (button) button.addEventListener("click", startSearch);
        document.addEventListener("keydown", event => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                startSearch();
            }
        });
    }

    function initializeLaunchModal() {
        const modal = $("#vtxLaunchModal");
        if (!modal) return;
        const email = $("#vtxLaunchEmail", modal);
        const service = $("#vtxLaunchService", modal);
        const message = $("#vtxLaunchMessage", modal);
        const form = $("#vtxLaunchForm", modal);
        let lastFocused = null;

        const open = () => {
            lastFocused = document.activeElement;
            modal.hidden = false;
            document.body.style.overflow = "hidden";
            window.setTimeout(() => { if (email) email.focus(); }, 30);
        };
        const close = () => {
            modal.hidden = true;
            document.body.style.overflow = "";
            if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus();
        };
        $$('[data-open-launch]').forEach(button => button.addEventListener("click", open));
        $$('[data-close-launch]', modal).forEach(button => button.addEventListener("click", close));
        document.addEventListener("keydown", event => { if (event.key === "Escape" && !modal.hidden) close(); });
        if (service && message) {
            const updateMessage = () => {
                message.value = `Please contact me about ${service.value}. I would like to discuss a possible project with VR Tech Solutions.`;
            };
            service.addEventListener("change", updateMessage);
            if (form) form.addEventListener("submit", updateMessage);
        }
    }

    function initializeProjectFilters() {
        const filters = $$('[data-project-filter]');
        const cards = $$('[data-project-card]');
        if (!filters.length || !cards.length) return;

        filters.forEach(button => {
            button.addEventListener("click", () => {
                const filter = button.getAttribute("data-project-filter") || "all";
                filters.forEach(item => {
                    const selected = item === button;
                    item.classList.toggle("is-selected", selected);
                    item.setAttribute("aria-pressed", String(selected));
                });
                cards.forEach(card => {
                    const categories = (card.getAttribute("data-category") || "").split(/\s+/);
                    card.hidden = filter !== "all" && !categories.includes(filter);
                });
            });
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        initializeTheme();
        initializeMobileNavigation();
        initializeSearch();
        initializeLaunchModal();
        initializeProjectFilters();
        refreshIcons();
    });
})();

