(function () {
    "use strict";

    var EDGE_WHITESPACE = /^[\s\u00A0\u200B\uFEFF]+|[\s\u00A0\u200B\uFEFF]+$/g;

    function trimEdgeWhitespace(value) {
        if (typeof value !== "string") {
            return value;
        }
        return value.replace(EDGE_WHITESPACE, "");
    }

    function insertTextAtSelection(element, text) {
        var start = element.selectionStart;
        var end = element.selectionEnd;

        if (start === null || end === null) {
            element.value = text;
            return;
        }

        var before = element.value.slice(0, start);
        var after = element.value.slice(end);
        element.value = before + text + after;

        var cursor = before.length + text.length;
        element.setSelectionRange(cursor, cursor);
    }

    function handlePaste(event) {
        var target = event.target;

        if (
            !(target instanceof HTMLInputElement)
            && !(target instanceof HTMLTextAreaElement)
        ) {
            return;
        }

        if (target.dataset.pasteTrim !== "edges") {
            return;
        }

        var clipboard = event.clipboardData;
        if (!clipboard) {
            return;
        }

        var pasted = clipboard.getData("text/plain");
        if (typeof pasted !== "string") {
            return;
        }

        var trimmed = trimEdgeWhitespace(pasted);
        if (trimmed === pasted) {
            return;
        }

        event.preventDefault();
        insertTextAtSelection(target, trimmed);
    }

    function attachPasteEdgeTrim(root) {
        (root || document).addEventListener("paste", handlePaste, true);
    }

    window.IntertopInputPasteNormalize = {
        trimEdgeWhitespace: trimEdgeWhitespace,
        attachPasteEdgeTrim: attachPasteEdgeTrim,
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            attachPasteEdgeTrim(document);
        });
    } else {
        attachPasteEdgeTrim(document);
    }
})();
