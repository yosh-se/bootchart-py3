import sys
import os
import unittest

sys.path.insert(0, os.getcwd())

import pybootchartgui.draw as draw


class DummyProc:

	def __init__(self, cmd, exe=None, args=None, pid=0):
		self.cmd = cmd
		self.exe = exe or cmd
		self.args = args or []
		self.pid = pid


class TestDraw(unittest.TestCase):

	def test_proc_idle_state_is_supported(self):
		self.assertEqual(draw.STATE_IDLE, draw.get_proc_state('I'))
		self.assertEqual(draw._theme_color('proc_idle'), draw._state_color(draw.STATE_IDLE))

	def test_unknown_proc_state_falls_back_to_undefined(self):
		self.assertEqual(draw.STATE_UNDEFINED, draw.get_proc_state('?'))

	def test_process_search_matches_cmd_and_is_case_insensitive(self):
		proc = DummyProc('storage-device')
		self.assertTrue(draw.process_matches_search(proc, 'Storage'))
		self.assertFalse(draw.process_matches_search(proc, 'logger'))

	def test_process_search_matches_exe_basename_and_args(self):
		proc = DummyProc('sh', '/usr/sbin/storage-device', ['/usr/sbin/storage-device', '--probe'])
		self.assertTrue(draw.process_matches_search(proc, 'storage-device'))
		self.assertTrue(draw.process_matches_search(proc, '--probe'))
		self.assertFalse(draw.process_matches_search(proc, 'syslog-ng'))

	def test_parent_connector_is_hidden_for_init(self):
		self.assertFalse(draw._should_draw_parent_connector(DummyProc('init', pid=1000)))
		self.assertTrue(draw._should_draw_parent_connector(DummyProc('service', pid=2000)))

	def test_process_state_info_covers_all_known_states(self):
		self.assertEqual(['R', 'D', 'S', 'T', 'Z', 'I', 'X', 'W'], [flag for flag, _state, _legend, _sidebar, _color in draw.PROCESS_STATE_INFO])
		self.assertEqual(draw.STATE_STOPPED, draw.PROCESS_STATE_BY_FLAG['T'][0])
		self.assertEqual('Stopped', draw.PROCESS_STATE_BY_FLAG['T'][1])


if __name__ == '__main__':
	unittest.main()