/* Shift+Enter inserts a line break in the chat input; plain Enter submits.
 *
 * The dash-mantine-components Textarea increments n_submit on every Enter
 * keydown regardless of modifier keys, so the split has to happen before
 * React's delegated listener (attached at the app root) sees the event.
 * A capture-phase listener on document runs first: for Shift+Enter it stops
 * propagation — the browser's default newline insertion still happens, but
 * n_submit never fires. For plain Enter it prevents the default newline and
 * lets the event through to submit as before.
 */
document.addEventListener(
    "keydown",
    function (event) {
        if (event.key !== "Enter") return;
        if (!event.target || event.target.id !== "chat-input") return;
        // Enter during IME composition confirms the composed text; it is
        // neither a newline nor a submit.
        if (event.isComposing || event.keyCode === 229) return;
        if (event.shiftKey) {
            event.stopPropagation();
        } else {
            event.preventDefault();
        }
    },
    true
);
