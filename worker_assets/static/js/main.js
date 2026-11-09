
/* Mouse-following hero light */
.vr-hero::after {
    content: "";
    position: absolute;
    inset: 0;
    z-index: -1;
    pointer-events: none;

    background: radial-gradient(
        300px circle at var(--mouse-x, 50%) var(--mouse-y, 50%),
        rgba(0, 140, 255, 0.08),
        transparent 70%
    );
}

/* Interactive globe */
.vr-globe {
    transform-style: preserve-3d;
    transition: transform 0.25s ease-out;
    will-change: transform;
}

/* Floating panel highlight */
.vr-float-card.is-highlighted {
    border-color: #00c8ff;

    box-shadow:
        0 0 25px rgba(0, 174, 255, 0.35),
        inset 0 0 18px rgba(0, 174, 255, 0.12);
}

/* Scroll reveal */
.vr-reveal {
    opacity: 0;
    transform: translateY(24px);

    transition:
        opacity 0.65s ease,
        transform 0.65s ease;
}

.vr-reveal.vr-visible {
    opacity: 1;
    transform: translateY(0);
}

/* Service card light */
.vr-service-card {
    background-image:
        radial-gradient(
            180px circle at var(--card-mouse-x, -200px)
            var(--card-mouse-y, -200px),
            rgba(0, 153, 255, 0.09),
            transparent 70%
        ),
        linear-gradient(
            145deg,
            rgba(14, 31, 54, 0.97),
            rgba(4, 14, 29, 0.97)
        );
}

/* Keep anchor targets visible below sticky navigation */
#our-services,
.vr-cta {
    scroll-margin-top: 90px;
}

/* Accessibility */
@media (prefers-reduced-motion: reduce) {
    .vr-reveal,
    .vr-globe,
    .vr-float-card,
    .vr-service-card {
        animation: none !important;
        transition: none !important;
        transform: none !important;
    }

    .vr-reveal {
        opacity: 1;
    }
}

