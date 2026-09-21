/* Collects what the mock preview's error shim reports.
 *
 * The Designer preview runs the drawn mock in a sandboxed iframe
 * (`sandbox="allow-scripts"`, no same-origin), so the page cannot look
 * inside it. `layouts.designer.MOCK_ERROR_SHIM`, injected into the preview
 * copy of the mock, posts three kinds of message to this window instead:
 * `mock-loaded` when the shim starts (a fresh document: reset), `mock-error`
 * for each distinct error the mock throws or resource it fails to load, and
 * `mock-ready` on the document's load event. Each one is written to the
 * `mock-render-errors` store through `dash_clientside.set_props`, which is
 * what a clientside painter (app.py) and the Fix-errors callback read.
 * Only messages from the preview iframe itself are accepted.
 */
(function () {
    var errors = [];
    var seen = {};
    var ready = false;
    var seq = 0;
    var LIMIT = 20;

    function publish() {
        seq += 1;
        try {
            window.dash_clientside.set_props("mock-render-errors", {
                data: { errors: errors.slice(), ready: ready, seq: seq },
            });
        } catch (e) {
            // The store is mounted only while the wizard is; a message
            // arriving in between is nothing to record.
        }
    }

    window.addEventListener("message", function (event) {
        var data = event.data;
        if (!data || typeof data.spec4 !== "string") return;
        var frame = document.getElementById("mock-iframe");
        if (!frame || event.source !== frame.contentWindow) return;
        if (data.spec4 === "mock-loaded") {
            errors = [];
            seen = {};
            ready = false;
        } else if (data.spec4 === "mock-error") {
            var detail = data.detail || {};
            var key = String(detail.message) + "@" + (detail.line || 0);
            if (seen[key] || errors.length >= LIMIT) return;
            seen[key] = true;
            errors.push({
                message: String(detail.message || "Script error"),
                source: String(detail.source || ""),
                line: Number(detail.line) || 0,
            });
        } else if (data.spec4 === "mock-ready") {
            ready = true;
        } else {
            return;
        }
        publish();
    });
})();
