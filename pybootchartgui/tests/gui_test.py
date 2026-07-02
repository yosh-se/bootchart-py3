import sys
import os
import math
import unittest
import gi
from types import SimpleNamespace

sys.path.insert(0, os.getcwd())

gi.require_version('Gdk', '3.0')
from gi.repository import Gdk

import pybootchartgui.gui as gui
from pybootchartgui import themes


class DummyCpuSample:

    def __init__(self, user, sys, io=0.0, swap=0.0):
        self.user = user
        self.sys = sys
        self.io = io
        self.swap = swap


class DummyProcessSample:

    def __init__(self, time, state, cpu_sample):
        self.time = time
        self.state = state
        self.cpu_sample = cpu_sample


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

    def test_widget_background_color_uses_resolved_theme(self):
        dark = gui._widget_background_color(SimpleNamespace(theme='dark', resolved_theme='dark'))
        light = gui._widget_background_color(SimpleNamespace(theme='light', resolved_theme='light'))
        self.assertEqual(themes.load_theme('dark')['colors']['background'], dark)
        self.assertEqual(themes.load_theme('light')['colors']['background'], light)
        self.assertNotEqual(dark, light)

    def test_minimum_zoom_ratio_for_width(self):
        self.assertAlmostEqual(0.5, gui._minimum_zoom_ratio_for_width(1000, 2000))
        self.assertAlmostEqual(2.0, gui._minimum_zoom_ratio_for_width(1000, 500))
        self.assertEqual(0.0, gui._minimum_zoom_ratio_for_width(0, 500))

    def test_widget_to_document_coords_and_hit_test(self):
        proc_a = SimpleNamespace(pid=1000)
        proc_b = SimpleNamespace(pid=2000)
        doc_x, doc_y = gui._widget_to_document_coords(20.0, 10.0, 2.0, 100.0, 50.0)
        self.assertAlmostEqual(110.0, doc_x)
        self.assertAlmostEqual(55.0, doc_y)
        proc = gui._process_at_position([
            (proc_a, (100.0, 50.0, 20.0, 10.0)),
            (proc_b, (130.0, 55.0, 20.0, 10.0)),
        ], doc_x, doc_y)
        self.assertIs(proc_a, proc)

    def test_motion_exceeds_drag_threshold(self):
        self.assertFalse(gui._motion_exceeds_drag_threshold(10.0, 10.0, 12.0, 12.0, 5.0))
        self.assertTrue(gui._motion_exceeds_drag_threshold(10.0, 10.0, 16.0, 10.0, 5.0))

    def test_build_process_details_rows_for_proc_ps_trace(self):
        parent = SimpleNamespace(cmd='init', pid=1000)
        proc = SimpleNamespace(
            pid=42000,
            ppid=1000,
            cmd='ifconfig',
            exe='ifconfig',
            args=[],
            parent=parent,
            child_list=[],
            start_time=250,
            duration=50,
            samples=[
                DummyProcessSample(300, 'R', DummyCpuSample(0.4, 0.1)),
                DummyProcessSample(350, 'D', DummyCpuSample(0.1, 0.0)),
            ],
            active=False,
        )
        row_list = gui._build_process_details_rows(SimpleNamespace(taskstats=False), proc)
        rows = dict(row_list)

        self.assertEqual('42', rows['PID'])
        self.assertEqual('init [1]', rows['Parent'])
        self.assertEqual('D', rows['Last state'])
        self.assertEqual('50.0%', rows['% Blocking:'])
        self.assertEqual('50.0%', rows['% Running:'])
        self.assertNotIn('% Unint.sleep:', rows)
        self.assertEqual('0.0%', rows['% Stopped:'])
        self.assertEqual('0.0%', rows['% Idle:'])
        self.assertEqual('50.0%', rows['Peak sampled CPU'])
        self.assertEqual('30.0%', rows['Avg sampled CPU'])
        self.assertEqual(1, sum(1 for key, _value in row_list if key == 'Peak sampled CPU'))
        self.assertEqual(1, sum(1 for key, _value in row_list if key == 'Avg sampled CPU'))

    def test_process_state_timeline_for_samples(self):
        proc = SimpleNamespace(
            samples=[
                DummyProcessSample(300, 'R', DummyCpuSample(0.4, 0.1)),
                DummyProcessSample(350, 'D', DummyCpuSample(0.1, 0.0)),
            ]
        )
        self.assertEqual([(300, 'R'), (350, 'D')], gui._process_state_timeline(proc))

    def test_process_cpu_sparkline_for_proc_ps_trace(self):
        proc = SimpleNamespace(
            samples=[
                DummyProcessSample(300, 'R', DummyCpuSample(0.4, 0.1)),
                DummyProcessSample(350, 'D', DummyCpuSample(0.1, 0.0)),
            ]
        )
        title, values = gui._process_cpu_sparkline(SimpleNamespace(taskstats=False), proc)
        self.assertEqual('Sampled CPU', title)
        self.assertEqual([(300, 50.0), (350, 10.0)], values)

    def test_process_io_delay_sparkline_for_taskstats_trace(self):
        proc = SimpleNamespace(
            samples=[
                DummyProcessSample(300, 'R', DummyCpuSample(1000.0, 0.0, 0.0)),
                DummyProcessSample(350, 'D', DummyCpuSample(500.0, 0.0, 2000.0)),
            ]
        )
        title, values = gui._process_io_delay_sparkline(SimpleNamespace(taskstats=True), proc)
        self.assertEqual('Blk I/O delay', title)
        self.assertEqual([(300, 0.0), (350, 2000.0)], values)


if __name__ == '__main__':
    unittest.main()