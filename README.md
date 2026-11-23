# Samsung Notes to Markdown

A small local tool for turning S Pen highlights and underlines into Markdown study notes.

Export a `.sdocx` file from Samsung Notes, choose a page range, and get clean excerpts ready to paste into ChatGPT web. Add handwritten thoughts yourself.

- Matches highlights and nearly horizontal underlines, regardless of pen color.
- Groups selected text by the original PDF page and joins consecutive selected lines.
- Leaves your documents and existing Markdown files unchanged.
- Runs locally, with **no OCR, LLM, API key, or document upload**.

**Only selectable text in embedded PDFs is supported. Text inside screenshots or scanned pages cannot be extracted.**

## Install

Download this repository using **Code → Download ZIP**, then extract it. Alternatively, clone your own GitHub repository.

Install [Python 3.11 or newer](https://www.python.org/downloads/) and [Node.js 22 LTS or newer](https://nodejs.org/). Node.js is needed for the Samsung Notes parser; no Rust compiler is required.

### Windows

Open a terminal in the extracted folder and run:

```powershell
python install.py
```

This creates a local `.venv` and installs the pinned Python and Node dependencies. The initial installation needs internet access; conversion does not.

## Use

```powershell
python convert.py "C:\Books\chapter.sdocx"
```

Or simply run `python convert.py` and enter the file path when prompted.

The script asks:

```text
Samsung Notes page range (e.g. 5-20; Enter for all):
```

Enter `5-20`, a single page such as `5`, or press Enter to process all pages. Ranges are inclusive and use the **visible page positions in Samsung Notes**, starting at 1. These can differ from the book's printed page numbers.

Output appears in `output/` beneath the directory where you run the command:

```text
output/
  chapter-pages-5-20.md
  chapter-pages-5-20.extraction.json
```

The Markdown contains only page headings and selected excerpts. The JSON report records unmatched candidate marks and extraction warnings. If an output filename exists, a numbered filename is used instead, preserving your edits.

### Example output

```markdown
# chapter

## PDF page 12

- Learning adjusts a model using examples.
- A validation set helps compare model choices.
```

Copy the Markdown into ChatGPT web with [chatgpt-prompt.txt](chatgpt-prompt.txt) to paraphrase and organize it. The tool itself does not summarize or invent missing context.

## macOS and Linux

With Python 3.11+ and Node.js installed:

```sh
python3 install.py
python3 convert.py /path/to/chapter.sdocx
```

The same local `.venv` setup is used on all platforms. Conversion automatically uses that environment when launched through `convert.py`.

## How it works

1. The [twangodev/sdocx](https://github.com/twangodev/sdocx) parser reads stroke geometry and the PDF page placements from your export.
2. Each stroke is scaled from its saved canvas width into the PDF placement's coordinate system. PyMuPDF reads word positions from the embedded original PDF.
3. The script matches highlights and underlines to words, removes duplicate selections, and writes Markdown.

The npm parser is pinned to `@twango/sdocx` 1.2.0. PyMuPDF is pinned to the version tested with this project. Dependencies are installed locally; the upstream repository does not need to be cloned.

## Limitations

- Handwriting, ticks, arrows, brackets, and image-only text are excluded.
- Very short, curved, or ambiguous underlines may not match.
- Rotated PDF pages, vertical text, and unresolved PDF bindings are unsupported.
- Only text from embedded PDFs is supported; other Samsung Notes object types are not converted.
- Some exports have broken spacing or character mappings in their source PDF.
- Page-range selection limits extraction; the parser still opens the whole `.sdocx` archive.

Check the JSON report for skipped selections. Your Samsung Notes export remains the complete record.

## Development

After installation:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On macOS/Linux use `.venv/bin/python` instead. The tests use generated content and do not require your personal books or notes. GitHub Actions is configured to run them on Windows and Linux.

Build a clean source ZIP:

```powershell
python scripts/build_release.py
```

It writes a versioned ZIP, such as `dist/sdocx-to-md-0.1.1.zip`, using an explicit file list. Your reading files, outputs, dependencies, downloaded language data, and upstream clone are excluded. The ZIP contains source code; Python and Node.js are still required.

## Put it on GitHub

Create an empty repository, extract the source ZIP into a new folder, and upload that folder's contents using GitHub's **Add file → Upload files**. Include the hidden `.github`, `.gitignore`, and `.gitattributes` files if using Git. Do not upload your entire working folder of books and notes.

For Git users, initialize and push the **extracted source folder** to your empty repository. The included `.gitignore` excludes common personal inputs and generated files. Once uploaded, use **Code → Download ZIP** on another PC and run `python install.py` there.

## License and acknowledgements

This tool's source is licensed under **AGPL-3.0-only**; see [LICENSE](LICENSE). Dependencies retain their own licenses. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) records the upstream parser and PyMuPDF notices and source links.

This is an independent personal tool, not an official Samsung product.
