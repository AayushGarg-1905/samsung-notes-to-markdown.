# Changelog

## 0.1.1

- Normalize each stroke using its saved owner-page width before matching it to the PDF. Exports can retain strokes saved at a different canvas size from the PDF placement.
- Decode the owner-page metadata through the upstream parser instead of guessing dimensions from the page or stroke extents.
- Allow a slightly larger underline-to-text gap.
- Report undecodable source-PDF characters in selected text.
- Add regression tests for mixed canvas sizes and underline spacing.

## 0.1.0

- Local extraction of S Pen highlights and underlines into clean Markdown.
- Interactive page ranges, automatic output naming, and a separate extraction report.
- Source-only GitHub package, installation helper, and tests.
