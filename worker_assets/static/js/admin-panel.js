
(() => {
    "use strict";

    const $ = (selector, root = document) =>
        root.querySelector(selector);

    const $$ = (selector, root = document) =>
        Array.from(root.querySelectorAll(selector));

    /* ---------------------------------------
       Lucide icons
    --------------------------------------- */

    function refreshIcons() {
        if (
            window.lucide &&
            typeof window.lucide.createIcons === "function"
        ) {
            window.lucide.createIcons();
        }
    }

    /* ---------------------------------------
       Light / dark theme
    --------------------------------------- */

    function initializeTheme() {
        const root = document.documentElement;
        let savedTheme = "light";

        try {
            savedTheme =
                localStorage.getItem("vrtech-admin-theme") || "light";
        } catch (_) {
            // Local storage may be disabled.
        }

        const setTheme = theme => {
            const nextTheme = theme === "dark" ? "dark" : "light";

            root.setAttribute("data-admin-theme", nextTheme);

            const icon = $("#vaThemeIcon");
            const meta = $('meta[name="theme-color"]');

            if (icon) {
                icon.setAttribute(
                    "data-lucide",
                    nextTheme === "dark" ? "sun" : "moon"
                );
            }

            if (meta) {
                meta.content =
                    nextTheme === "dark" ? "#050711" : "#f2f5ff";
            }

            try {
                localStorage.setItem(
                    "vrtech-admin-theme",
                    nextTheme
                );
            } catch (_) {
                // Theme still works for the current page.
            }

            refreshIcons();
        };

        setTheme(savedTheme);

        const toggle = $("#vaThemeToggle");

        if (toggle) {
            toggle.addEventListener("click", () => {
                const current =
                    root.getAttribute("data-admin-theme");

                setTheme(current === "dark" ? "light" : "dark");
            });
        }
    }

    /* ---------------------------------------
       Responsive sidebar
    --------------------------------------- */

    function initializeSidebar() {
        const sidebar = $("#vaSidebar");
        const toggle = $("#vaSidebarToggle");
        const scrim = $("#vaMobileScrim");

        if (!sidebar || !toggle || !scrim) {
            return;
        }

        const close = () => {
            sidebar.classList.remove("is-open");
            scrim.classList.remove("is-visible");
            scrim.hidden = true;

            toggle.setAttribute("aria-expanded", "false");
            toggle.setAttribute("aria-label", "Open navigation");
        };

        const open = () => {
            sidebar.classList.add("is-open");
            scrim.hidden = false;

            requestAnimationFrame(() => {
                scrim.classList.add("is-visible");
            });

            toggle.setAttribute("aria-expanded", "true");
            toggle.setAttribute("aria-label", "Close navigation");
        };

        toggle.addEventListener("click", () => {
            if (sidebar.classList.contains("is-open")) {
                close();
            } else {
                open();
            }
        });

        scrim.addEventListener("click", close);

        $$("a", sidebar).forEach(link => {
            link.addEventListener("click", close);
        });

        document.addEventListener("keydown", event => {
            if (event.key === "Escape") {
                close();
            }
        });

        window.addEventListener("resize", () => {
            if (window.innerWidth > 850) {
                close();
            }
        });
    }

    /* ---------------------------------------
       Dismiss flash messages
    --------------------------------------- */

    function initializeFlashMessages() {
        $$(".va-flash-close").forEach(button => {
            button.addEventListener("click", () => {
                const flash = button.closest(".va-flash");

                if (flash) {
                    flash.remove();
                }
            });
        });
    }

    /* ---------------------------------------
       Confirm destructive form actions
    --------------------------------------- */

    function initializeConfirmForms() {
        $$("form[data-confirm]").forEach(form => {
            form.addEventListener("submit", event => {
                const message =
                    form.getAttribute("data-confirm") ||
                    "Are you sure you want to continue?";

                if (!window.confirm(message)) {
                    event.preventDefault();
                }
            });
        });
    }

    /* ---------------------------------------
       Client-side admin table filtering
    --------------------------------------- */

    function initializeTableSearch() {
        const input = $("#vaTableSearch");
        const table = $("#vaFilterTable");

        if (!input || !table) {
            return;
        }

        input.addEventListener("input", () => {
            const query = input.value
                .trim()
                .toLocaleLowerCase();

            const rows = $$(
                "tbody tr:not(.va-subrow)",
                table
            );

            rows.forEach(row => {
                const text =
                    row.textContent.toLocaleLowerCase();

                const visible =
                    !query || text.includes(query);

                row.hidden = !visible;

                // Keep an application's details row in sync
                // with the main application row.
                const next = row.nextElementSibling;

                if (
                    next &&
                    next.classList.contains("va-subrow")
                ) {
                    next.hidden = !visible;
                }
            });
        });
    }

    /* ---------------------------------------
       Initialize all admin interactions
    --------------------------------------- */

    document.addEventListener("DOMContentLoaded", () => {
        initializeTheme();
        initializeSidebar();
        initializeFlashMessages();
        initializeConfirmForms();
        initializeTableSearch();
        refreshIcons();
    });
})();
