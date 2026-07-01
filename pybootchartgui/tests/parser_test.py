import io
import sys, os, re, struct, operator, math
from collections import defaultdict
import unittest

sys.path.insert(0, os.getcwd())

import pybootchartgui.parsing as parsing
import pybootchartgui.main as main

debug = False

def floatEq(f1, f2):
	return math.fabs(f1-f2) < 0.00001

bootchart_dir = os.path.join(os.path.dirname(sys.argv[0]), '../../examples/1/')
parser = main._mk_options_parser()
options, args = parser.parse_args(['--q', bootchart_dir])
writer = main._mk_writer(options)

class TestBCParser(unittest.TestCase):
    
	def setUp(self):
		self.name = "My first unittest"
		self.rootdir = bootchart_dir

	def mk_fname(self,f):
		return os.path.join(self.rootdir, f)

	def testParseHeader(self):
		trace = parsing.Trace(writer, args, options)
		state = parsing.parse_file(writer, trace, self.mk_fname('header'))
		self.assertEqual(6, len(state.headers))
		self.assertEqual(2, parsing.get_num_cpus(state.headers))

	def test_parseTimedBlocks(self):
		trace = parsing.Trace(writer, args, options)
		state = parsing.parse_file(writer, trace, self.mk_fname('proc_diskstats.log'))
		self.assertEqual(141, len(state.disk_stats))		

	def testParseProcPsLog(self):
		trace = parsing.Trace(writer, args, options)
		state = parsing.parse_file(writer, trace, self.mk_fname('proc_ps.log'))
		samples = state.ps_stats
		processes = samples.process_map
		sorted_processes = [processes[k] for k in sorted(processes.keys())]

		ps_data = open(self.mk_fname('extract2.proc_ps.log'))
		for index, line in enumerate(ps_data):
			tokens = line.split();
			process = sorted_processes[index]
			if debug:
				print((tokens[0:4]))
				print((process.pid / 1000, process.cmd, process.ppid, len(process.samples)))
				print('-------------------')

			self.assertEqual(tokens[0], str(process.pid // 1000))
			self.assertEqual(tokens[1], str(process.cmd))
			self.assertEqual(tokens[2], str(process.ppid // 1000))
			self.assertEqual(tokens[3], str(len(process.samples)))
		ps_data.close()

	def testparseProcDiskStatLog(self):
		trace = parsing.Trace(writer, args, options)
		state_with_headers = parsing.parse_file(writer, trace, self.mk_fname('header'))
		state_with_headers.headers['system.cpu'] = 'xxx (2)'
		samples = parsing.parse_file(writer, state_with_headers, self.mk_fname('proc_diskstats.log')).disk_stats
		self.assertEqual(141, len(samples))

		diskstats_data = open(self.mk_fname('extract.proc_diskstats.log'))
		for index, line in enumerate(diskstats_data):
			tokens = line.split('\t')
			sample = samples[index]
			if debug:		
				print((line.rstrip()))
				print(sample)
				print('-------------------')
			
			self.assertEqual(tokens[0], str(sample.time))
			self.assertTrue(floatEq(float(tokens[1]), sample.read))
			self.assertTrue(floatEq(float(tokens[2]), sample.write))
			self.assertTrue(floatEq(float(tokens[3]), sample.util))
		diskstats_data.close()

	def testParseProcPsRenameKeepsExeInSync(self):
		ps_data = b"".join([
			b"100\n",
			b"371 (sh) R 368 138 138 0 -1 4194368 0 0 0 0 0 0 0 0 20 0 1 0 2456 3932160 29 4294967295 4878336 5750512 3200396848 0 0 0 0 4 65538 1 0 0 17 0 0 0 0 0 0 5752840 5759001 32964608 3200397104 3200397146 3200397146 3200397300 0\n",
			b"\n",
			b"200\n",
			b"371 (storage-device) R 1 138 138 0 -1 4194304 77 0 1 0 1 0 0 0 20 0 1 0 2456 3796992 271 4294967295 4952064 5824240 3202321920 0 0 0 0 6 0 0 0 0 17 0 0 0 0 0 0 5826568 5832729 36864000 3202322193 3202322232 3202322232 3202322403 0\n",
			b"\n",
		])

		stats = parsing._parse_proc_ps_log(writer, io.BytesIO(ps_data))
		process = stats.process_map[371000]

		self.assertEqual('storage-device', process.cmd)
		self.assertEqual('storage-device', process.exe)
	
	def testparseProcStatLog(self):
		trace = parsing.Trace(writer, args, options)
		state = parsing.parse_file(writer, trace, self.mk_fname('proc_stat.log'))
		cpu_stats = state.cpu_stats
		# Backwards compat: cpu_stats can be List[CPUSample] or
		# {'all': List[CPUSample], 'per_cpu': {idx: List[CPUSample]}}
		if isinstance(cpu_stats, dict):
			samples = cpu_stats.get('all', [])
		else:
			samples = cpu_stats
		self.assertEqual(141, len(samples))

		stat_data = open(self.mk_fname('extract.proc_stat.log'))
		for index, line in enumerate(stat_data):
			tokens = line.split('\t')
			sample = samples[index]
			if debug:
				print((line.rstrip()))
				print(sample)
				print('-------------------')
			self.assertTrue(floatEq(float(tokens[0]), sample.time))
			self.assertTrue(floatEq(float(tokens[1]), sample.user))
			self.assertTrue(floatEq(float(tokens[2]), sample.sys))
			self.assertTrue(floatEq(float(tokens[3]), sample.io))
		stat_data.close()

		self.assertIsNotNone(state.proc_stat_metrics)
		self.assertEqual(len(samples) + 1, len(state.proc_stat_metrics['procs_running']))
		self.assertEqual(len(samples), len(state.proc_stat_metrics['ctxt_rate']))
		self.assertEqual(len(samples), len(state.proc_stat_metrics['intr_rate']))
		self.assertGreater(sum(value for (_, value) in state.proc_stat_metrics['ctxt_rate']), 0.0)
		softirq_rate = state.proc_stat_metrics['softirq_rate']
		self.assertTrue(len(softirq_rate) in (0, len(samples)))
		if softirq_rate:
			self.assertGreater(sum(value for (_, value) in softirq_rate), 0.0)

if __name__ == '__main__':
    unittest.main()

