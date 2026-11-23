"""End-to-end Python extraction tests using authored PDFs and parser geometry."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from convert import convert, fitz


class ConversionTests(unittest.TestCase):
    def make_document(self, directory):
        source = directory / 'test.sdocx'
        with fitz.open() as pdf:
            for text in ('First selected passage', 'Second selected passage'):
                page = pdf.new_page(width=300, height=100)
                page.insert_text((20, 40), text, fontsize=12)
            content = pdf.tobytes()
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('media/0@source.pdf', content)
        pages = []
        for number in (1, 2):
            pages.append({
                'number': number, 'uuid': str(number), 'width': 300, 'height': 100,
                'pdf_placements': [{'media_id': 0, 'page_index': number - 1,
                                    'rectangle': {'Integer': [0, 0, 300, 100]}}],
                'strokes': [
                    {'id': 1, 'pen': 'Marker4', 'width': 12, 'visible': True,
                     'bbox': {'x_min': 18, 'y_min': 36, 'x_max': 200, 'y_max': 37},
                     'points': [{'x': 18, 'y': 36}, {'x': 200, 'y': 36}]},
                    {'id': 2, 'pen': 'InkPen2', 'width': 2, 'visible': True,
                     'bbox': {'x_min': 230, 'y_min': 20, 'x_max': 232, 'y_max': 75},
                     'points': [{'x': 230, 'y': 20}, {'x': 232, 'y': 75}]},
                ],
            })
        geometry = {'diagnostics': [], 'pages': pages}

        def parser_run(command, **kwargs):
            Path(command[-1]).write_text(json.dumps(geometry), encoding='utf-8')

        return source, parser_run

    def test_range_extracts_only_requested_page_without_images_or_ocr(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, parser_run = self.make_document(directory)
            output = directory / 'result.md'
            with patch('convert.subprocess.run', side_effect=parser_run), patch.object(
                fitz.Page, 'get_textpage_ocr', side_effect=AssertionError('OCR must never run')
            ):
                convert(source, output, pages='2')
            text = output.read_text(encoding='utf-8')
            self.assertIn('Second selected passage', text)
            self.assertNotIn('First selected', text)
            self.assertNotIn('![', text)
            report = json.loads(output.with_suffix('.extraction.json').read_text(encoding='utf-8'))
            self.assertEqual(report['selected_note_pages'], [2])
            self.assertEqual(len(report['pages']), 1)
            self.assertEqual(report['pages'][0]['excluded_strokes'], [2])
            self.assertFalse(list(directory.glob('*.png')))

    def test_invalid_range_writes_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, parser_run = self.make_document(directory)
            output = directory / 'result.md'
            with patch('convert.subprocess.run', side_effect=parser_run):
                with self.assertRaises(ValueError):
                    convert(source, output, pages='3-5')
            self.assertFalse(output.exists())

    def test_mixed_stroke_canvas_sizes_are_normalized_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, parser_run = self.make_document(directory)

            def different_canvas_sizes(command, **kwargs):
                parser_run(command, **kwargs)
                path = Path(command[-1])
                geometry = json.loads(path.read_text(encoding='utf-8'))
                for stroke in geometry['pages'][0]['strokes']:
                    stroke['owner_page_width'] = 150
                    stroke['width'] /= 2
                    stroke['bbox'] = {k: v / 2 for k, v in stroke['bbox'].items()}
                    stroke['points'] = [{k: v / 2 for k, v in p.items()} for p in stroke['points']]
                for stroke in geometry['pages'][1]['strokes']:
                    stroke['owner_page_width'] = 300
                path.write_text(json.dumps(geometry), encoding='utf-8')

            output = directory / 'result.md'
            with patch('convert.subprocess.run', side_effect=different_canvas_sizes):
                convert(source, output)
            text = output.read_text(encoding='utf-8')
            self.assertIn('First selected passage', text)
            self.assertIn('Second selected passage', text)
            report = json.loads(output.with_suffix('.extraction.json').read_text(encoding='utf-8'))
            self.assertEqual([p['rescaled_strokes'] for p in report['pages']], [2, 0])

    def test_existing_notes_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, parser_run = self.make_document(directory)
            output = directory / 'result.md'
            output.write_text('My own additions', encoding='utf-8')
            with patch('convert.subprocess.run', side_effect=parser_run):
                with self.assertRaises(ValueError):
                    convert(source, output)
            self.assertEqual(output.read_text(encoding='utf-8'), 'My own additions')


if __name__ == '__main__':
    unittest.main()
