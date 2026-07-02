import sys
import os
import math
import unittest
import gi

sys.path.insert(0, os.getcwd())

gi.require_version('Gdk', '3.0')
from gi.repository import Gdk

import pybootchartgui.gui as gui


class TestGuiHelpers(unittest.TestCase):

    def test_pointer_zoom_event_mask_includes_wheel_and_smooth_scroll(self):
        mask = gui._pointer_zoom_event_mask()
        self.assertTrue(mask & Gdk.EventMask.SCROLL_MASK)
        self.assertTrue(mask & Gdk.EventMask.SMOOTH_SCROLL_MASK)

    def test_zoom_origin_for_focus_preserves_world_point(self):
        origin = gui._zoom_origin_for_focus(50.0, 60.0, 1.0, 2.0)
        self.assertAlmostEqual(80.0, origin)
        self.assertAlmostEqual(110.0, 50.0 + 60.0 / 1.0)
        self.assertAlmostEqual(110.0, origin + 60.0 / 2.0)

    def test_zoom_ratio_for_scroll_handles_wheel_and_smooth(self):
        self.assertAlmostEqual(1.25, gui._zoom_ratio_for_scroll(1.0, Gdk.ScrollDirection.UP, 0.0, 1.25))
        self.assertAlmostEqual(0.8, gui._zoom_ratio_for_scroll(1.0, Gdk.ScrollDirection.DOWN, 0.0, 1.25))
        self.assertAlmostEqual(1.25, gui._zoom_ratio_for_scroll(1.0, Gdk.ScrollDirection.SMOOTH, -1.0, 1.25))
        self.assertAlmostEqual(0.8, gui._zoom_ratio_for_scroll(1.0, Gdk.ScrollDirection.SMOOTH, 1.0, 1.25))
        self.assertIsNone(gui._zoom_ratio_for_scroll(1.0, Gdk.ScrollDirection.SMOOTH, 0.0, 1.25))


if __name__ == '__main__':
    unittest.main()