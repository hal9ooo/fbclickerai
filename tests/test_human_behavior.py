"""Test unit per le utility di movimento umano (nessun browser)."""

import unittest

from src.browser.human_behavior import bezier_point, gaussian_random, generate_bezier_path


class GaussianRandomTests(unittest.TestCase):
    def test_respects_minimum_floor(self):
        for _ in range(200):
            value = gaussian_random(mean=0.0, std=0.5, min_val=0.1)
            self.assertGreaterEqual(value, 0.1)


class BezierTests(unittest.TestCase):
    def test_endpoints(self):
        p0, p1, p2, p3 = (0.0, 0.0), (10.0, 30.0), (20.0, -10.0), (30.0, 10.0)
        self.assertEqual(bezier_point(0.0, p0, p1, p2, p3), p0)
        self.assertEqual(bezier_point(1.0, p0, p1, p2, p3), p3)

    def test_path_length_and_endpoints(self):
        start, end = (5, 7), (105, 207)
        path = generate_bezier_path(start, end, num_points=10)
        self.assertEqual(len(path), 10)
        self.assertEqual(path[0], start)
        self.assertEqual(path[-1], end)

    def test_single_point_path_does_not_crash(self):
        path = generate_bezier_path((0, 0), (10, 10), num_points=2)
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (10, 10))


if __name__ == "__main__":
    unittest.main()
