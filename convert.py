"""Extract highlighted and underlined selectable text from Samsung Notes."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import shutil
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
import os

# Keep the everyday command simple after install.py creates the local venv.
if __name__ == '__main__':
    local_python = Path(__file__).resolve().parent / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if local_python.is_file() and Path(sys.prefix).resolve() != local_python.parent.parent.resolve():
        raise SystemExit(subprocess.call([str(local_python), str(Path(__file__).resolve()), *sys.argv[1:]]))

try:
    import pymupdf as fitz
except ImportError as error:
    raise SystemExit('Missing dependency. Run: python install.py') from error


def bounds(stroke):
    b = stroke['bbox']
    return b['x_min'], b['y_min'], b['x_max'], b['y_max']


def normalize_stroke(stroke, page_width):
    """Apply Samsung's uniform load-time owner-page width scaling."""
    owner = stroke.get('owner_page_width')
    if owner is None:
        return stroke
    if not isinstance(owner, (int, float)) or not math.isfinite(owner) or owner <= 0:
        raise ValueError('Invalid stroke owner page width')
    factor = page_width / owner
    if factor == 1:
        return stroke
    return {
        **stroke,
        'bbox': {name: value * factor for name, value in stroke['bbox'].items()},
        'points': [{'x': p['x'] * factor, 'y': p['y'] * factor} for p in stroke['points']],
        'width': stroke['width'] * factor,
    }


def mark_kind(stroke):
    if not stroke.get('visible', True) or stroke.get('eraser'):
        return 'ignored'
    name = stroke.get('pen', '').lower()
    if 'marker' in name or 'highlighter' in name:
        return 'highlight'
    x0, y0, x1, y1 = bounds(stroke)
    if x1 - x0 >= max(45, 8 * stroke['width']) and y1 - y0 <= max(4, (x1 - x0) * .035):
        return 'underline'
    return 'ink'


def segment_distance(x, y, a, b):
    dx, dy = b['x'] - a['x'], b['y'] - a['y']
    length = dx * dx + dy * dy
    t = max(0, min(1, ((x - a['x']) * dx + (y - a['y']) * dy) / length)) if length else 0
    return math.hypot(x - a['x'] - t * dx, y - a['y'] - t * dy)


def selected_words(stroke, words):
    """Match selection geometry without filtering by pen color."""
    kind = mark_kind(stroke)
    if kind not in ('highlight', 'underline') or not stroke['points']:
        return []
    sx0, sy0, sx1, sy1 = bounds(stroke)
    points = stroke['points']
    pairs = list(zip(points, points[1:])) or [(points[0], points[0])]
    chosen = []
    for word in words:
        x0, y0, x1, y1 = word['rect']
        overlap = max(0, min(x1, sx1) - max(x0, sx0))
        if overlap < .35 * (x1 - x0):
            continue
        if kind == 'highlight':
            y = word['baseline'] - .35 * word['size']
            radius = max(stroke['width'] / 2, 1)
            if y < sy0 - radius or y > sy1 + radius:
                continue
            hits = sum(
                any(segment_distance(x0 + f * (x1 - x0), y, a, b) <= radius for a, b in pairs)
                for f in (.1, .3, .5, .7, .9)
            )
            if hits >= 2:
                chosen.append(word)
        else:
            # An underline must lie just below this line's baseline. This avoids
            # selecting the following line, even when its font bbox overlaps.
            y = (sy0 + sy1) / 2
            delta = y - word['baseline']
            if -.10 * word['size'] <= delta <= .80 * word['size']:
                chosen.append(word)
    return chosen


def placement_rect(record):
    value = record['rectangle']
    if 'Integer' in value:
        rect = value['Integer']
    elif 'LegacyFloatBits' in value:
        rect = [struct.unpack('<f', struct.pack('<I', n))[0] for n in value['LegacyFloatBits']]
    else:
        raise ValueError('Unrecognized PDF placement rectangle')
    if not all(math.isfinite(n) for n in rect) or rect[2] <= rect[0] or rect[3] <= rect[1]:
        raise ValueError('Invalid PDF placement rectangle')
    return rect


def pdf_words(page, dest, prefix, textpage=None):
    if page.rotation:
        raise ValueError('Rotated PDF pages are not supported in this first version')
    x0, y0, x1, y1 = dest
    sx, sy = (x1 - x0) / page.rect.width, (y1 - y0) / page.rect.height
    # Reuse one text page: independent extraction defaults include images in
    # dict mode but omit them in words mode, shifting every subsequent block ID.
    if textpage is None:
        textpage = page.get_textpage(flags=fitz.TEXTFLAGS_WORDS)
    line_info = {}
    for block in page.get_text('dict', textpage=textpage)['blocks']:
        bi = block['number']
        for li, line in enumerate(block.get('lines', [])):
            spans = line.get('spans', [])
            if spans:
                line_info[(bi, li)] = (spans[0]['origin'][1], spans[0]['size'], line['dir'])
    words = []
    for ax, ay, bx, by, text, bi, li, wi in page.get_text('words', textpage=textpage):
        info = line_info.get((bi, li))
        if info is None or abs(info[2][0] - 1) > .01 or abs(info[2][1]) > .01:
            continue
        baseline, size, _ = info
        words.append({
            'id': f'{prefix}:{bi}:{li}:{wi}', 'text': text,
            'rect': [x0 + ax * sx, y0 + ay * sy, x0 + bx * sx, y0 + by * sy],
            'baseline': y0 + baseline * sy, 'size': size * sy,
            'line': [prefix, bi, li], 'order': wi,
        })
    return words


def selected_passages(words, chosen_ids):
    lines = defaultdict(list)
    for word in words:
        lines[tuple(word['line'])].append(word)
    passages = []
    for line in sorted(lines.values(), key=lambda line: (line[0]['rect'][1], line[0]['rect'][0])):
        ordered = sorted(line, key=lambda word: word['order'])
        run = []
        for word in ordered:
            if word['id'] in chosen_ids:
                run.append(word)
            elif run:
                passages.append(run)
                run = []
        if run:
            # Join across a line break only when both sides of that break are
            # selected and are consecutive lines in the same PDF text block.
            # Earlier partial runs on this line must not be joined backwards.
            passages.append(run)
    merged = []
    for run in passages:
        if merged:
            previous = merged[-1][-1]
            current = run[0]
            previous_line = lines[tuple(previous['line'])]
            current_line = lines[tuple(current['line'])]
            adjacent = (previous['line'][:2] == current['line'][:2]
                        and previous['line'][2] + 1 == current['line'][2]
                        and previous['order'] == max(w['order'] for w in previous_line)
                        and current['order'] == min(w['order'] for w in current_line))
            if adjacent:
                merged[-1].extend(run)
                continue
        merged.append(run.copy())
    return merged


def passage_text(run):
    text = ''
    previous = None
    for word in run:
        if previous is not None and previous['line'] != word['line'] and text.endswith(('\u2010', '\u00ad')):
            # Unicode discretionary line-end hyphens in this PDF. Keep normal
            # hyphens because they may be part of an actual compound word.
            text = text[:-1] + word['text']
        else:
            text += (' ' if text else '') + word['text']
        previous = word
    return text


def parse_page_range(value, total):
    value = value.strip()
    if not value:
        return set(range(1, total + 1))
    match = re.fullmatch(r'(\d+)\s*(?:-\s*(\d+))?', value)
    if not match:
        raise ValueError('Enter a single page (5), a range (5-20), or leave blank for all.')
    start = int(match[1])
    end = int(match[2] or match[1])
    if not 1 <= start <= end <= total:
        raise ValueError(f'Page range must be between 1 and {total}, with start <= end.')
    return set(range(start, end + 1))


def available_output(source, pages):
    suffix = '-pages-' + re.sub(r'\s+', '', pages) if pages.strip() else ''
    base = Path('output') / (source.stem + suffix)
    candidate = base.with_name(base.name + '.md')
    number = 2
    while candidate.exists() or candidate.with_suffix('.extraction.json').exists():
        candidate = base.with_name(f'{base.name}-{number}.md')
        number += 1
    return candidate


def convert(source, output=None, pages=''):
    root = Path(__file__).resolve().parent
    node = shutil.which('node')
    if not node:
        raise ValueError('Node.js was not found. Install Node.js 22+ and run python install.py.')
    if not (root / 'node_modules/@twango/sdocx/package.json').is_file():
        raise ValueError('Samsung Notes parser is missing. Run python install.py.')
    with tempfile.TemporaryDirectory(prefix='sdocx-') as temp:
        compact = Path(temp) / 'geometry.json'
        subprocess.run([node, str(root / 'scripts/parse-sdocx.mjs'), str(source.resolve()), str(compact)], check=True)
        geometry = json.loads(compact.read_text(encoding='utf-8'))
    selected_pages = parse_page_range(pages, len(geometry['pages']))
    output = output or available_output(source, pages)
    if output.suffix.lower() != '.md' or source.resolve() == output.resolve():
        raise ValueError('Output must be a separate .md file')
    if output.exists() or output.with_suffix('.extraction.json').exists():
        raise ValueError(f'Output already exists: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path = output.with_suffix('.extraction.json')
    report = {'input': str(source.resolve()), 'selected_note_pages': sorted(selected_pages), 'pages': [],
              'parser_diagnostics': geometry['diagnostics']}
    md = [f'# {source.stem}', '']
    documents = {}
    try:
        with zipfile.ZipFile(source) as archive:
            media = defaultdict(list)
            for name in archive.namelist():
                match = re.match(r'^media/(\d+)@.*\.pdf$', name, re.IGNORECASE)
                if match:
                    media[int(match[1])].append(name)
            for note in geometry['pages']:
                if note['number'] not in selected_pages:
                    continue
                strokes = [normalize_stroke(s, note['width']) for s in note['strokes']
                           if mark_kind(s) != 'ignored']
                if not strokes:
                    continue
                print(f'Processing note page {note["number"]}...', flush=True)
                number = note['number']
                words, warnings, source_pages = [], [], []
                if not note['pdf_placements']:
                    warnings.append('No embedded PDF text source on this note page.')
                for diagnostic in geometry['diagnostics']:
                    if (diagnostic.get('code') == 'UnresolvedImageMedia'
                            and note['uuid'] in diagnostic.get('archive_entry', '')):
                        warnings.append('The Samsung Notes parser could not resolve an image on this page.')
                        break
                for pi, placement in enumerate(note['pdf_placements']):
                    try:
                        names = media[placement['media_id']]
                        if len(names) != 1:
                            raise ValueError('Embedded PDF binding is missing or ambiguous')
                        name = names[0]
                        if name not in documents:
                            documents[name] = fitz.open(stream=archive.read(name), filetype='pdf')
                        page = documents[name][placement['page_index']]
                        dest = placement_rect(placement)
                        label = f'PDF page {placement["page_index"] + 1}'
                        text_length = len(page.get_text().strip())
                        raster_slide = any(
                            fitz.Rect(image['bbox']).get_area() > .4 * page.rect.get_area()
                            for image in page.get_image_info()
                        ) and text_length < 80
                        source_info = {'file': name, 'page': placement['page_index'] + 1,
                                       'selectable_text_characters': text_length,
                                       'mostly_raster': raster_slide, 'text_method': 'pdf'}
                        source_pages.append(source_info)
                        if raster_slide:
                            warnings.append(f'{label}: image-based slide text was skipped; only selectable text is extracted.')
                        mapped = pdf_words(page, dest, f'{pi}')
                        for word in mapped:
                            word['source'] = label
                        words.extend(mapped)
                        if not mapped:
                            warnings.append(f'{label}: no supported selectable text.')
                    except (ValueError, IndexError, KeyError, RuntimeError) as error:
                        warnings.append(str(error))
                matches, residual, unmatched = [], [], []
                for stroke in strokes:
                    kind = mark_kind(stroke)
                    if kind not in ('highlight', 'underline'):
                        residual.append(stroke)
                        continue
                    selected = selected_words(stroke, words)
                    if selected:
                        matches.append({'stroke_id': stroke['id'], 'kind': kind, 'word_ids': [w['id'] for w in selected]})
                    else:
                        residual.append(stroke)
                        if kind in ('highlight', 'underline'):
                            unmatched.append(stroke['id'])
                # Union overlapping selections, then split at unselected words.
                # Separate highlight/underline styles share one extraction to avoid duplication.
                chosen_ids = {wid for m in matches for wid in m['word_ids']}
                passages = selected_passages(words, chosen_ids)
                if passages:
                    pages_label = ', '.join(str(p['page']) for p in source_pages)
                    md += [f'## PDF page {pages_label}', '']
                    for run in passages:
                        text = passage_text(run)
                        text = re.sub(r'([\\`*_{}\[\]<>])', r'\\\1', text)
                        md += [f'- {text}']
                    md.append('')
                if unmatched:
                    warnings.append('No confident word match for selection strokes: ' + ', '.join(map(str, unmatched)))
                if any('\ufffd' in passage_text(run) for run in passages):
                    warnings.append('The source PDF contains undecodable characters in selected text; compare with the original page.')
                report['pages'].append({'note_page': number, 'sources': source_pages, 'stroke_count': len(strokes),
                                        'rescaled_strokes': sum(s.get('owner_page_width') not in (None, note['width'])
                                                                for s in strokes),
                                        'matches': matches, 'unmatched_selection_strokes': unmatched,
                                        'excluded_strokes': [s['id'] for s in residual],
                                        'passages': [passage_text(r) for r in passages], 'warnings': warnings})
    finally:
        for document in documents.values():
            document.close()
    if not any(p['passages'] for p in report['pages']):
        md += ['No highlighted or underlined text could be extracted.', '']
    output.write_text('\n'.join(md), encoding='utf-8')
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Markdown: {output}')
    print(f'Extraction report: {report_path}')
    print(f'Processed {len(report["pages"])} annotated page(s); '
          f'{sum(len(p["matches"]) for p in report["pages"])} matched selection strokes.')
    unresolved = sum(len(p['unmatched_selection_strokes']) for p in report['pages'])
    if unresolved:
        print(f'{unresolved} candidate selection strokes could not be matched; see the extraction report.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', type=Path, help='Samsung Notes .sdocx export')
    args = parser.parse_args()
    try:
        source = args.input or Path(input('Path to .sdocx file: ').strip().strip('"'))
        if not source.is_file() or source.suffix.lower() != '.sdocx':
            parser.error('Input must be an existing .sdocx file')
        pages = input('Samsung Notes page range (e.g. 5-20; Enter for all): ').strip()
        convert(source, pages=pages)
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f'Conversion failed: {error}', file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print('Conversion cancelled.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
