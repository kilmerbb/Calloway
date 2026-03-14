/**
 * Calloway — Accessibility helpers (progressive enhancement)
 *
 * 1. HTMX afterSwap: announces dynamic content changes to screen readers
 * 2. Focus trap utility for modal-like elements
 */
(function () {
    'use strict';

    // ----------------------------------------------------------------
    // 1. HTMX afterSwap — announce content changes via a live region
    // ----------------------------------------------------------------
    var liveRegion = document.createElement('div');
    liveRegion.setAttribute('role', 'status');
    liveRegion.setAttribute('aria-live', 'polite');
    liveRegion.setAttribute('aria-atomic', 'true');
    liveRegion.className = 'sr-only';
    document.body.appendChild(liveRegion);

    document.body.addEventListener('htmx:afterSwap', function (evt) {
        var target = evt.detail.target;
        if (!target) return;

        // Build a concise announcement from the target's aria-label or id
        var label = target.getAttribute('aria-label');
        if (!label) {
            var id = target.id;
            if (id) {
                // Convert id like "activity-feed" to "activity feed"
                label = id.replace(/[-_]/g, ' ') + ' updated';
            }
        }

        if (label) {
            // Clear then set so the SR re-reads even if the same text
            liveRegion.textContent = '';
            requestAnimationFrame(function () {
                liveRegion.textContent = label;
            });
        }
    });

    // ----------------------------------------------------------------
    // 2. Simple focus trap for modal-like elements
    //    Usage:
    //      var trap = Calloway.a11y.trapFocus(modalElement);
    //      trap.activate();
    //      trap.deactivate();
    // ----------------------------------------------------------------
    var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    function trapFocus(container) {
        var previousFocus = null;

        function handleKeydown(e) {
            if (e.key !== 'Tab') return;
            var focusable = Array.from(container.querySelectorAll(FOCUSABLE));
            if (focusable.length === 0) return;
            var first = focusable[0];
            var last = focusable[focusable.length - 1];
            if (e.shiftKey) {
                if (document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                }
            } else {
                if (document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        }

        return {
            activate: function () {
                previousFocus = document.activeElement;
                container.addEventListener('keydown', handleKeydown);
                var first = container.querySelector(FOCUSABLE);
                if (first) first.focus();
            },
            deactivate: function () {
                container.removeEventListener('keydown', handleKeydown);
                if (previousFocus && previousFocus.focus) {
                    previousFocus.focus();
                }
            }
        };
    }

    // Expose on global namespace for optional use by other scripts
    window.Calloway = window.Calloway || {};
    window.Calloway.a11y = {
        trapFocus: trapFocus
    };
})();
