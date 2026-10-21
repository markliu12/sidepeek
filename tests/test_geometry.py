"""Unit tests for the pure geometry helpers."""

import unittest

from sidepeek.overlay import fit_rect


class FitRectTest(unittest.TestCase):
    def test_same_aspect_fills_the_box(self):
        self.assertEqual(fit_rect((0, 0, 160, 90), 320, 180), (0, 0, 160, 90))

    def test_wide_source_gets_pillarboxed(self):
        # 2:1 source in a 1:1 box -> bars left and right
        self.assertEqual(fit_rect((0, 0, 200, 200), 400, 100), (0, 75, 200, 125))

    def test_tall_source_gets_letterboxed(self):
        # 1:4 source in a 4:1 box -> bars top and bottom
        self.assertEqual(fit_rect((0, 0, 400, 200), 100, 400), (175, 0, 225, 200))

    def test_result_is_centred_in_the_box(self):
        left, top, right, bottom = fit_rect((10, 20, 210, 220), 400, 100)
        self.assertEqual(right - left, 200)
        self.assertEqual(bottom - top, 50)
        self.assertEqual(left - 10, 210 - right)       # equal margins
        self.assertEqual(top - 20, 220 - bottom)

    def test_aspect_ratio_is_preserved_within_a_pixel(self):
        left, top, right, bottom = fit_rect((0, 0, 480, 270), 2560, 1440)
        self.assertAlmostEqual((right - left) / (bottom - top), 2560 / 1440, delta=0.02)

    def test_unknown_source_size_returns_the_box(self):
        box = (0, 0, 100, 50)
        self.assertEqual(fit_rect(box, 0, 0), box)
        self.assertEqual(fit_rect(box, -1, 20), box)

    def test_never_exceeds_the_box(self):
        for box in ((0, 0, 101, 57), (5, 5, 301, 199), (0, 0, 1, 1)):
            left, top, right, bottom = fit_rect(box, 1920, 1080)
            self.assertGreaterEqual(left, box[0])
            self.assertGreaterEqual(top, box[1])
            self.assertLessEqual(right, box[2])
            self.assertLessEqual(bottom, box[3])


if __name__ == "__main__":
    unittest.main()
