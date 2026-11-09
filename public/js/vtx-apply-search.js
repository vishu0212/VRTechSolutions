(() => {
    "use strict";

    const $ = (selector, root = document) =>
        root.querySelector(selector);

    const $$ = (selector, root = document) =>
        Array.from(root.querySelectorAll(selector));

    function refreshIcons() {
        if (window.lucide &&
            typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons();
        }
    }

    /* Resume upload validation */

    function initializeResumeUpload() {
        const input = $("#applyResume");
        const fileName = $("#vtxResumeFileName");
        const error = $("#vtxResumeError");
        const drop = $("#vtxResumeDrop");
        const form = $("#vtxApplyForm");

        const maxBytes = 5 * 1024 * 1024;
        const allowedExtensions = ["pdf", "doc", "docx"];

        if (!input) return;

        const validateFile = () => {
            if (!input.files || !input.files.length) {
                if (fileName) {
                    fileName.textContent = "Choose your resume";
                }

                if (error) {
                    error.textContent = "";
                }

                if (drop) {
                    drop.classList.remove("has-error");
                }

                return !input.required;
            }

            const file = input.files[0];
            const extension = file.name.split(".").pop().toLowerCase();

            let message = "";

            if (!allowedExtensions.includes(extension)) {
                message = "Please choose a PDF, DOC, or DOCX file.";
            } else if (file.size > maxBytes) {
                message =
                    "The selected file is larger than 5 MB. " +
                    "Please choose a smaller file.";
            }

            if (fileName) {
                fileName.textContent = message
                    ? "Choose a different file"
                    : file.name;
            }

            if (error) {
                error.textContent = message;
            }

            if (drop) {
                drop.classList.toggle("has-error", Boolean(message));
            }

            return !message;
        };

        input.addEventListener("change", validateFile);

        if (form) {
            form.addEventListener("submit", event => {
                if (!validateFile()) {
                    event.preventDefault();
                    input.focus();
                }
            });
        }

        if (drop) {
            ["dragenter", "dragover"].forEach(type => {
                drop.addEventListener(type, event => {
                    event.preventDefault();
                    drop.classList.add("is-dragover");
                });
            });

            ["dragleave", "drop"].forEach(type => {
                drop.addEventListener(type, event => {
                    event.preventDefault();
                    drop.classList.remove("is-dragover");
                });
            });

            drop.addEventListener("drop", event => {
                const files =
                    event.dataTransfer && event.dataTransfer.files;

                if (files && files.length) {
                    try {
                        input.files = files;

                        input.dispatchEvent(
                            new Event("change", { bubbles: true })
                        );
                    } catch (_) {
                        // Use Browse if the browser prevents FileList assignment.
                    }
                }
            });
        }
    }

    /* Brief introduction character counter */

    function initializeCoverLetterCounter() {
        const textarea = $("#applyCoverLetter");
        const count = $("#vtxCoverCount");

        if (!textarea || !count) return;

        const update = () => {
            count.textContent = String(textarea.value.length);
        };

        textarea.addEventListener("input", update);
        update();
    }

    /* Search page suggestions */

    function initializeSearchSuggestions() {
        const input = $("#vtxSearchQuery");
        const form = $("#vtxSearchPageForm");

        if (!input || !form) return;

        $$("[data-search-term]").forEach(button => {
            button.addEventListener("click", () => {
                input.value =
                    button.getAttribute("data-search-term") || "";

                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            });
        });

        const tryAgain = $("#vtxTryAgainButton");

        if (tryAgain) {
            tryAgain.addEventListener("click", () => {
                input.focus();
                input.select();

                window.scrollTo({
                    top: 0,
                    behavior: "smooth"
                });
            });
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        initializeResumeUpload();
        initializeCoverLetterCounter();
        initializeSearchSuggestions();
        refreshIcons();
    });
})();