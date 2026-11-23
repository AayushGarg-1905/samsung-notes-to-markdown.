import unittest

from convert import mark_kind, selected_words, placement_rect, pdf_words, fitz, selected_passages, passage_text, parse_page_range, available_output, normalize_stroke


def stroke(x0, y0, x1, y1, marker=False):
    return {'id': 1, 'bbox': dict(x_min=x0, y_min=y0, x_max=x1, y_max=y1),
            'points': [{'x': x0, 'y': y0}, {'x': x1, 'y': y1}],
            'width': 10 if marker else 2, 'pen': 'Marker4' if marker else 'InkPen2'}


def word(identifier, x0, x1, baseline=100):
    return {'id': identifier, 'rect': [x0, baseline - 10, x1, baseline + 3], 'baseline': baseline, 'size': 10}


class GeometryTests(unittest.TestCase):
    def test_stroke_saved_at_different_page_width_selects_correct_line(self):
        # Like the DDIA export: strokes saved at width 1080, PDF at width 1752.
        original = stroke(20, 60, 90, 60, True)
        original['owner_page_width'] = 1080
        factor = 1752 / 1080
        expected_baseline = 60 * factor + 3.5
        words = [word('correct', 40, 130, expected_baseline), word('wrong', 40, 130, 63.5)]
        normalized = normalize_stroke(original, 1752)
        self.assertEqual([w['id'] for w in selected_words(normalized, words)], ['correct'])
        self.assertAlmostEqual(normalized['width'], 10 * factor)
        self.assertEqual(original['points'][0]['y'], 60)

    def test_same_page_width_leaves_stroke_unchanged(self):
        original = stroke(20, 96, 90, 96, True)
        original['owner_page_width'] = 1752
        self.assertEqual(normalize_stroke(original, 1752), original)

    def test_page_range_is_inclusive_and_bounded(self):
        self.assertEqual(parse_page_range('2-4', 5), {2, 3, 4})
        self.assertEqual(parse_page_range('3', 5), {3})
        self.assertEqual(parse_page_range('', 2), {1, 2})
        for invalid in ('0-2', '4-2', '1-6', 'abc', '1,3'):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                parse_page_range(invalid, 5)

    def test_join_selected_line_break_but_preserve_unselected_gap(self):
        words = [
            dict(word('a', 0, 10), text='train\u2010', line=['0', 1, 0], order=0),
            dict(word('b', 0, 10, 113), text='ing', line=['0', 1, 1], order=0),
            dict(word('c', 20, 30, 113), text='unselected', line=['0', 1, 1], order=1),
            dict(word('d', 40, 50, 113), text='later', line=['0', 1, 1], order=2),
        ]
        passages = selected_passages(words, {'a', 'b', 'd'})
        self.assertEqual([passage_text(p) for p in passages], ['training', 'later'])

    def test_image_before_text_does_not_shift_word_baselines(self):
        with fitz.open() as document:
            page = document.new_page(width=300, height=300)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), False)
            pix.clear_with(255)
            page.insert_image(fitz.Rect(0, 0, 20, 20), pixmap=pix)
            page.insert_text((40, 100), 'Selected words', fontsize=12)
            page.insert_text((40, 150), 'Other line', fontsize=12)
            words = pdf_words(page, [0, 0, 300, 300], '0')
            self.assertEqual(words[0]['text'], 'Selected')
            self.assertAlmostEqual(words[0]['baseline'], 100)
            self.assertAlmostEqual(words[-1]['baseline'], 150)

    def test_highlight_does_not_select_adjacent_words_or_lines(self):
        words = [word('before', 0, 15), word('selected', 25, 65), word('after', 80, 110), word('next-line', 25, 65, 113)]
        self.assertEqual([w['id'] for w in selected_words(stroke(24, 96, 66, 96, True), words)], ['selected'])

    def test_underline_selects_line_above_not_below(self):
        words = [word('above', 20, 90), word('below', 20, 90, 113)]
        self.assertEqual([w['id'] for w in selected_words(stroke(18, 103, 92, 103), words)], ['above'])

    def test_underline_with_larger_gap_still_selects_the_line_above(self):
        words = [word('above', 20, 90), word('below', 20, 90, 113)]
        self.assertEqual([w['id'] for w in selected_words(stroke(18, 107, 92, 107), words)], ['above'])

    def test_narrow_overlap_does_not_pull_in_whole_word(self):
        self.assertEqual(selected_words(stroke(70, 96, 110, 96, True), [word('edge', 0, 75)]), [])

    def test_bracket_is_preserved_as_ink(self):
        self.assertEqual(mark_kind(stroke(50, 10, 54, 100)), 'ink')

    def test_invalid_placement_is_rejected(self):
        with self.assertRaises(ValueError):
            placement_rect({'rectangle': {'Integer': [10, 0, 5, 100]}})

    def test_pen_color_does_not_change_selection(self):
        words = [word('selected', 25, 65)]
        for marker in (False, True):
            for color in ({'r': 255, 'g': 0, 'b': 0}, {'r': 0, 'g': 255, 'b': 0},
                          {'r': 0, 'g': 0, 'b': 255}, {'r': 255, 'g': 255, 'b': 255}):
                with self.subTest(marker=marker, color=color):
                    mark = stroke(18, 96 if marker else 103, 92, 96 if marker else 103, marker)
                    mark['color'] = color
                    self.assertEqual([w['id'] for w in selected_words(mark, words)], ['selected'])


if __name__ == '__main__':
    unittest.main()
