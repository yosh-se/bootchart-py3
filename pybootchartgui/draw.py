#  This file is part of pybootchartgui.

#  pybootchartgui is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  pybootchartgui is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with pybootchartgui. If not, see <http://www.gnu.org/licenses/>.


import os
import cairo
import math
import re
import random
import colorsys
from operator import itemgetter
from . import themes

class RenderOptions:

	def __init__(self, app_options):
		# should we render a cumulative CPU time chart
		self.cumulative = True
		self.charts = True
		self.kernel_only = False
		self.app_options = app_options

	def proc_tree (self, trace):
		if self.kernel_only:
			return trace.kernel_tree
		else:
			return trace.proc_tree

# Font family
FONT_NAME = "Bitstream Vera Sans"
# Title text font.
TITLE_FONT_SIZE = 18
# Default text font.
TEXT_FONT_SIZE = 12
# Axis label font.
AXIS_FONT_SIZE = 11
# Legend font.
LEGEND_FONT_SIZE = 12

# Process label font.
PROC_TEXT_FONT_SIZE = 12

# Signature font.
SIG_FONT_SIZE = 14
# Signature text.
SIGNATURE = "http://github.com/mmeeks/bootchart"

# Process dependency line stroke.
DEP_STROKE = 1.0

# Process description date format.
DESC_TIME_FORMAT = "mm:ss.SSS"

# Cumulative coloring bits
HSV_MAX_MOD = 31
HSV_STEP = 7

# Process states
STATE_UNDEFINED = 0
STATE_RUNNING   = 1
STATE_SLEEPING  = 2
STATE_WAITING   = 3
STATE_STOPPED   = 4
STATE_ZOMBIE    = 5
STATE_IDLE      = 6
STATE_DEAD      = 7
STATE_PAGING    = 8

# CumulativeStats Types
STAT_TYPE_CPU = 0
STAT_TYPE_IO = 1

PROCESS_STATE_INFO = (
	('R', STATE_RUNNING, 'Running (%cpu)', 'Running samples', 'proc_running'),
	('D', STATE_WAITING, 'Blocking', 'Blocking samples', 'proc_waiting'),
	('S', STATE_SLEEPING, 'Sleeping', 'Sleeping samples', 'proc_sleeping'),
	('T', STATE_STOPPED, 'Stopped', 'Stopped samples', 'proc_stopped'),
	('Z', STATE_ZOMBIE, 'Zombie', 'Zombie samples', 'proc_zombie'),
	('I', STATE_IDLE, 'Idle kthread', 'Idle samples', 'proc_idle'),
	('X', STATE_DEAD, 'Dead', 'Dead samples', 'proc_dead'),
	('W', STATE_PAGING, 'Paging', 'Paging samples', 'proc_paging'),
)

PROCESS_STATE_BY_FLAG = dict((flag, (state, legend_label, sidebar_label, color_name)) for flag, state, legend_label, sidebar_label, color_name in PROCESS_STATE_INFO)

THEME = themes.load_theme(themes.DEFAULT_THEME_NAME)


def _theme_color(name):
	return THEME['colors'][name]


def _state_color(state):
	state_colors = [
		(0, 0, 0, 0),
		_theme_color('proc_running'),
		_theme_color('proc_sleeping'),
		_theme_color('proc_waiting'),
		_theme_color('proc_stopped'),
		_theme_color('proc_zombie'),
		_theme_color('proc_idle'),
		_theme_color('proc_dead'),
		_theme_color('proc_paging'),
	]
	return state_colors[state]


def _core_color(idx, alpha=None):
	palette = THEME['core_palette']
	h = ((idx * 0.61803398875) % 1.0)
	r, g, b = colorsys.hsv_to_rgb(h, palette['saturation'], palette['value'])
	if alpha is None:
		alpha = palette['alpha']
	return (r, g, b, alpha)


def _load_render_theme(app_options):
	resolved_theme = getattr(app_options, 'resolved_theme', None)
	if resolved_theme is None:
		try:
			resolved_theme = themes.resolve_theme_name(getattr(app_options, 'theme', themes.DEFAULT_THEME_NAME), False)
		except themes.ThemeError:
			resolved_theme = themes.DEFAULT_THEME_NAME
	return themes.load_theme(resolved_theme)


def _search_highlight_color():
	color = _theme_color('annotation')
	return (color[0], color[1], color[2], 1.0)


def _selection_highlight_color():
	color = _theme_color('disk_tput')
	return (color[0], color[1], color[2], 1.0)


def process_matches_search(proc, search_term):
	term = (search_term or '').strip().lower()
	if not term:
		return False

	haystacks = []

	def add_haystack(value):
		if not value:
			return
		lower = str(value).lower()
		haystacks.append(lower)
		base = os.path.basename(lower)
		if base and base != lower:
			haystacks.append(base)

	add_haystack(getattr(proc, 'cmd', None))
	add_haystack(getattr(proc, 'exe', None))
	for arg in getattr(proc, 'args', []) or []:
		add_haystack(arg)

	return any(term in value for value in haystacks)


def _should_draw_parent_connector(parent_proc):
	return parent_proc is not None and parent_proc.pid // 1000 != 1


def _is_selected_process(proc):
	return getattr(OPTIONS, 'selected_process_pid', None) == proc.pid


def _process_block_rect(proc, proc_tree, y_positions, rect):
	x = rect[0] + ((proc.start_time - proc_tree.start_time) * rect[2] / proc_tree.duration)
	w = ((proc.duration) * rect[2] / proc_tree.duration)
	y = y_positions[proc]
	return (x, y, w, proc_h)


def _draw_process_state_legend(ctx, curr_y):
	columns = 4
	column_width = 165
	row_height = 22
	legend_y = curr_y + 25
	for idx, (_, _, legend_label, _, color_name) in enumerate(PROCESS_STATE_INFO):
		row = idx // columns
		col = idx % columns
		draw_legend_box(ctx, legend_label,
				 _theme_color(color_name),
				 off_x + col * column_width,
				 legend_y + row * row_height,
				 leg_s)
	rows = int(math.ceil(float(len(PROCESS_STATE_INFO)) / columns))
	return 20 + rows * row_height

# Convert ps process state to an int
def get_proc_state(flag):
	return {
		'R': STATE_RUNNING,
		'S': STATE_SLEEPING,
		'D': STATE_WAITING,
		'T': STATE_STOPPED,
		'Z': STATE_ZOMBIE,
		'I': STATE_IDLE,
		'X': STATE_DEAD,
		'W': STATE_PAGING,
	}.get(flag, STATE_UNDEFINED)

def draw_text(ctx, text, color, x, y):
	ctx.set_source_rgba(*color)
	ctx.move_to(x, y)
	ctx.show_text(text)

def draw_fill_rect(ctx, color, rect):
	ctx.set_source_rgba(*color)
	ctx.rectangle(*rect)
	ctx.fill()

def draw_rect(ctx, color, rect):
	ctx.set_source_rgba(*color)
	ctx.rectangle(*rect)
	ctx.stroke()

def draw_legend_box(ctx, label, fill_color, x, y, s):
	draw_fill_rect(ctx, fill_color, (x, y - s, s, s))
	draw_rect(ctx, _theme_color('proc_border'), (x, y - s, s, s))
	draw_text(ctx, label, _theme_color('text'), x + s + 5, y)

def draw_legend_line(ctx, label, fill_color, x, y, s):
	draw_fill_rect(ctx, fill_color, (x, y - s/2, s + 1, 3))
	ctx.arc(x + (s + 1)/2.0, y - (s - 3)/2.0, 2.5, 0, 2.0 * math.pi)
	ctx.fill()
	draw_text(ctx, label, _theme_color('text'), x + s + 5, y)

def draw_label_in_box(ctx, color, label, x, y, w, maxx):
	label_w = ctx.text_extents(label)[2]
	label_align = getattr(OPTIONS, 'process_label_align', 'left')
	if label_align == 'center':
		label_x = x + w / 2 - label_w / 2
	else:
		label_x = x + 5
	if label_w + 10 > w:
		label_x = x + w + 5
	if label_x + label_w > maxx:
		label_x = x - label_w - 5
	draw_text(ctx, label, color, label_x, y)

def draw_sec_labels(ctx, rect, sec_w, nsecs):
	ctx.set_font_size(AXIS_FONT_SIZE)
	prev_x = 0
	for i in range(0, rect[2] + 1, sec_w):
		if ((i / sec_w) % nsecs == 0) :
			label = "%ds" % (i / sec_w)
			label_w = ctx.text_extents(label)[2]
			x = rect[0] + i - label_w/2
			if x >= prev_x:
				draw_text(ctx, label, _theme_color('text'), x, rect[1] - 2)
				prev_x = x + label_w

def draw_box_ticks(ctx, rect, sec_w):
	draw_rect(ctx, _theme_color('border'), tuple(rect))

	ctx.set_line_cap(cairo.LINE_CAP_SQUARE)

	for i in range(sec_w, rect[2] + 1, sec_w):
		if ((i / sec_w) % 5 == 0) :
			ctx.set_source_rgba(*_theme_color('tick_bold'))
		else :
			ctx.set_source_rgba(*_theme_color('tick'))
		ctx.move_to(rect[0] + i, rect[1] + 1)
		ctx.line_to(rect[0] + i, rect[1] + rect[3] - 1)
		ctx.stroke()

	ctx.set_line_cap(cairo.LINE_CAP_BUTT)

def draw_annotations(ctx, proc_tree, times, rect):
	ctx.set_line_cap(cairo.LINE_CAP_SQUARE)
	ctx.set_source_rgba(*_theme_color('annotation'))
	ctx.set_dash([4, 4])

	for time in times:
		if time is not None:
			x = ((time - proc_tree.start_time) * rect[2] / proc_tree.duration)

			ctx.move_to(rect[0] + x, rect[1] + 1)
			ctx.line_to(rect[0] + x, rect[1] + rect[3] - 1)
			ctx.stroke()

	ctx.set_line_cap(cairo.LINE_CAP_BUTT)
	ctx.set_dash([])

def draw_chart(ctx, color, fill, chart_bounds, data, proc_tree, data_range):
	ctx.set_line_width(0.5)
	x_shift = proc_tree.start_time

	def transform_point_coords(point, x_base, y_base, \
				   xscale, yscale, x_trans, y_trans):
		x = (point[0] - x_base) * xscale + x_trans
		y = (point[1] - y_base) * -yscale + y_trans + chart_bounds[3]
		return x, y

	max_x = max (x for (x, y) in data)
	max_y = max (y for (x, y) in data)
	# avoid divide by zero
	if max_y == 0:
		max_y = 1.0
	xscale = float (chart_bounds[2]) / max_x
	# If data_range is given, scale the chart so that the value range in
	# data_range matches the chart bounds exactly.
	# Otherwise, scale so that the actual data matches the chart bounds.
	if data_range:
		yscale = float(chart_bounds[3]) / (data_range[1] - data_range[0])
		ybase = data_range[0]
	else:
		yscale = float(chart_bounds[3]) / max_y
		ybase = 0

	first = transform_point_coords (data[0], x_shift, ybase, xscale, yscale, \
				        chart_bounds[0], chart_bounds[1])
	last =  transform_point_coords (data[-1], x_shift, ybase, xscale, yscale, \
				        chart_bounds[0], chart_bounds[1])

	ctx.set_source_rgba(*color)
	ctx.move_to(*first)
	for point in data:
		x, y = transform_point_coords (point, x_shift, ybase, xscale, yscale, \
					       chart_bounds[0], chart_bounds[1])
		ctx.line_to(x, y)
	if fill:
		ctx.stroke_preserve()
		ctx.line_to(last[0], chart_bounds[1]+chart_bounds[3])
		ctx.line_to(first[0], chart_bounds[1]+chart_bounds[3])
		ctx.line_to(first[0], first[1])
		ctx.fill()
	else:
		ctx.stroke()
	ctx.set_line_width(1.0)

bar_h = 55
meminfo_bar_h = 2 * bar_h
header_text_h = 110
# offsets
off_x, off_y = 10, 10
sec_w_base = 50 # the width of a second
proc_h = 16 # the height of a process
leg_s = 10
MIN_IMG_W = 800
CUML_HEIGHT = 2000 # Increased value to accomodate CPU and I/O Graphs
UNRELATED_PROC_GAP = 5
OPTIONS = None


def _split_cpu_stats(cpu_stats):
	if isinstance(cpu_stats, dict):
		return cpu_stats.get('all', []), cpu_stats.get('per_cpu', {})
	return cpu_stats, {}


def _chart_stack_height(trace):
	all_cpu, per_cpu = _split_cpu_stats(trace.cpu_stats)
	proc_stat_metrics = getattr(trace, 'proc_stat_metrics', None) or {}
	sections = 0
	if all_cpu:
		sections += 1
	sections += len(per_cpu)
	if proc_stat_metrics.get('procs_running') or proc_stat_metrics.get('procs_blocked'):
		sections += 1
	if proc_stat_metrics.get('ctxt_rate') or proc_stat_metrics.get('intr_rate') or proc_stat_metrics.get('softirq_rate'):
		sections += 1
	if trace.disk_stats:
		sections += 1
	height = header_text_h + sections * (30 + bar_h)
	if trace.mem_stats:
		height += 30 + meminfo_bar_h
	return height


def _max_series_value(*series_list):
	values = [point[1] for series in series_list for point in series]
	if not values:
		return 1.0
	return max(values)


def _iter_processes_preorder(processes):
	for proc in processes:
		yield proc
		for child in _iter_processes_preorder(proc.child_list):
			yield child


def _has_direct_parent_transition(prev_proc, proc):
	return getattr(proc, 'parent', None) is prev_proc


def _count_process_row_gaps(proc_tree):
	prev_proc = None
	gaps = 0
	for proc in _iter_processes_preorder(proc_tree.process_tree):
		if prev_proc is not None and not _has_direct_parent_transition(prev_proc, proc):
			gaps += 1
		prev_proc = proc
	return gaps


def _build_process_y_positions(proc_tree, start_y):
	y_positions = {}
	prev_proc = None
	current_y = start_y
	for proc in _iter_processes_preorder(proc_tree.process_tree):
		if prev_proc is not None:
			current_y += proc_h
			if not _has_direct_parent_transition(prev_proc, proc):
				current_y += UNRELATED_PROC_GAP
		y_positions[proc] = current_y
		prev_proc = proc
	return y_positions


def _clip_extents_to_rect(clip_extents):
	x1, y1, x2, y2 = clip_extents
	return (x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))

def extents(options, xscale, trace):
	proc_tree = options.proc_tree(trace)
	w = int (proc_tree.duration * sec_w_base * xscale / 100) + 2*off_x
	h = proc_h * proc_tree.num_proc + _count_process_row_gaps(proc_tree) * UNRELATED_PROC_GAP + 2 * off_y
	if options.charts:
		h += _chart_stack_height(trace)
	if proc_tree.taskstats and options.cumulative:
		h += CUML_HEIGHT + 4 * off_y
	return (w, h)

def clip_visible(clip, rect):
	xmax = max (clip[0], rect[0])
	ymax = max (clip[1], rect[1])
	xmin = min (clip[0] + clip[2], rect[0] + rect[2])
	ymin = min (clip[1] + clip[3], rect[1] + rect[3])
	return (xmin > xmax and ymin > ymax)

def render_charts(ctx, options, clip, trace, curr_y, w, h, sec_w):
	proc_tree = options.proc_tree(trace)
	all_cpu, per_cpu = _split_cpu_stats(trace.cpu_stats)
	proc_stat_metrics = getattr(trace, 'proc_stat_metrics', None) or {}

	# render bar legend
	ctx.set_font_size(LEGEND_FONT_SIZE)

	draw_legend_box(ctx, "CPU (user+sys)", _theme_color('cpu'), off_x, curr_y+20, leg_s)
	draw_legend_box(ctx, "I/O (wait)", _theme_color('io'), off_x + 120, curr_y+20, leg_s)

	# render I/O wait
	chart_rect = (off_x, curr_y+30, w, bar_h)
	if clip_visible (clip, chart_rect):
		draw_box_ticks (ctx, chart_rect, sec_w)
		draw_annotations (ctx, proc_tree, trace.times, chart_rect)

		draw_chart (ctx, _theme_color('io'), True, chart_rect, \
			    [(sample.time, sample.user + sample.sys + sample.io) for sample in all_cpu], \
			    proc_tree, None)
		# render CPU load
		draw_chart (ctx, _theme_color('cpu'), True, chart_rect, \
			    [(sample.time, sample.user + sample.sys) for sample in all_cpu], \
			    proc_tree, None)

	curr_y = curr_y + 30 + bar_h

	# If per-cpu data is available, render each core as a separate line chart
	# (filled CPU and filled I/O wait) stacked vertically.
	if per_cpu:
		ctx.set_font_size(LEGEND_FONT_SIZE)
		# render a small legend header once
		draw_text(ctx, "Per-core CPU utilization", _theme_color('text'), off_x, curr_y+20)

		ordered = sorted(per_cpu.items(), key=lambda kv: kv[0])
		for idx, series in ordered:
			chart_rect = (off_x, curr_y+30, w, bar_h)
			if clip_visible(clip, chart_rect):
				draw_box_ticks(ctx, chart_rect, sec_w)
				draw_annotations(ctx, proc_tree, trace.times, chart_rect)
				c = _core_color(idx)
				io_c = _core_color(idx, THEME['core_palette']['io_alpha'])
				draw_chart(ctx, io_c, True, chart_rect,
					   [(s.time, s.user + s.sys + s.io) for s in series],
					   proc_tree, None)
				draw_chart(ctx, c, True, chart_rect,
					   [(s.time, s.user + s.sys) for s in series],
					   proc_tree, None)
				# core label
				draw_text(ctx, f"cpu{idx}", _theme_color('text'), off_x + 5, curr_y + 30 + 15)

			curr_y = curr_y + 30 + bar_h

	# render second chart
	runnable = proc_stat_metrics.get('procs_running', [])
	blocked = proc_stat_metrics.get('procs_blocked', [])
	if runnable or blocked:
		draw_legend_line(ctx, "Runnable tasks", _theme_color('cpu'), off_x, curr_y+20, leg_s)
		draw_legend_line(ctx, "Blocked tasks", _theme_color('io'), off_x + 180, curr_y+20, leg_s)

		chart_rect = (off_x, curr_y+30, w, bar_h)
		if clip_visible(clip, chart_rect):
			draw_box_ticks(ctx, chart_rect, sec_w)
			draw_annotations(ctx, proc_tree, trace.times, chart_rect)
			queue_scale = _max_series_value(runnable, blocked)
			if blocked:
				draw_chart(ctx, _theme_color('io'), False, chart_rect, blocked, proc_tree, [0, queue_scale])
			if runnable:
				draw_chart(ctx, _theme_color('cpu'), False, chart_rect, runnable, proc_tree, [0, queue_scale])

		curr_y = curr_y + 30 + bar_h

	ctxt_rate = proc_stat_metrics.get('ctxt_rate', [])
	intr_rate = proc_stat_metrics.get('intr_rate', [])
	softirq_rate = proc_stat_metrics.get('softirq_rate', [])
	if ctxt_rate or intr_rate or softirq_rate:
		draw_legend_line(ctx, "Context switches/s", _theme_color('disk_tput'), off_x, curr_y+20, leg_s)
		draw_legend_line(ctx, "Interrupts/s", _theme_color('file_open'), off_x + 220, curr_y+20, leg_s)
		draw_legend_line(ctx, "SoftIRQ/s", _theme_color('io'), off_x + 400, curr_y+20, leg_s)

		chart_rect = (off_x, curr_y+30, w, bar_h)
		if clip_visible(clip, chart_rect):
			draw_box_ticks(ctx, chart_rect, sec_w)
			draw_annotations(ctx, proc_tree, trace.times, chart_rect)
			rate_scale = _max_series_value(ctxt_rate, intr_rate, softirq_rate)
			if ctxt_rate:
				draw_chart(ctx, _theme_color('disk_tput'), False, chart_rect, ctxt_rate, proc_tree, [0, rate_scale])
			if intr_rate:
				draw_chart(ctx, _theme_color('file_open'), False, chart_rect, intr_rate, proc_tree, [0, rate_scale])
			if softirq_rate:
				draw_chart(ctx, _theme_color('io'), False, chart_rect, softirq_rate, proc_tree, [0, rate_scale])

		curr_y = curr_y + 30 + bar_h

	max_tput = _max_series_value(
		[(sample.time, sample.read) for sample in trace.disk_stats],
		[(sample.time, sample.write) for sample in trace.disk_stats])
	if max_tput <= 0:
		max_tput = 1.0
	mb_scale = max_tput / 1024.0
	draw_legend_line(ctx, "Disk read (scale: %.1f MB/s)" % mb_scale, _theme_color('disk_tput'), off_x, curr_y+20, leg_s)
	draw_legend_line(ctx, "Disk write", _theme_color('file_open'), off_x + 250, curr_y+20, leg_s)
	draw_legend_box(ctx, "Disk utilization", _theme_color('io'), off_x + 420, curr_y+20, leg_s)

	# render I/O utilization
	chart_rect = (off_x, curr_y+30, w, bar_h)
	if clip_visible (clip, chart_rect):
		draw_box_ticks (ctx, chart_rect, sec_w)
		draw_annotations (ctx, proc_tree, trace.times, chart_rect)
		draw_chart (ctx, _theme_color('io'), True, chart_rect, \
			    [(sample.time, sample.util) for sample in trace.disk_stats], \
			    proc_tree, None)
		draw_chart (ctx, _theme_color('disk_tput'), False, chart_rect, \
			    [(sample.time, sample.read) for sample in trace.disk_stats], \
			    proc_tree, [0, max_tput])
		draw_chart (ctx, _theme_color('file_open'), False, chart_rect, \
			    [(sample.time, sample.write) for sample in trace.disk_stats], \
			    proc_tree, [0, max_tput])

	curr_y = curr_y + 30 + bar_h

	# render mem usage
	chart_rect = (off_x, curr_y+30, w, meminfo_bar_h)
	mem_stats = trace.mem_stats
	if mem_stats and clip_visible (clip, chart_rect):
		mem_scale = max(sample.records['MemTotal'] - sample.records['MemFree'] for sample in mem_stats)
		draw_legend_box(ctx, "Mem cached (scale: %u MiB)" % (float(mem_scale) / 1024), _theme_color('mem_cached'), off_x, curr_y+20, leg_s)
		draw_legend_box(ctx, "Used", _theme_color('mem_used'), off_x + 240, curr_y+20, leg_s)
		draw_legend_box(ctx, "Buffers", _theme_color('mem_buffers'), off_x + 360, curr_y+20, leg_s)
		draw_legend_line(ctx, "Swap (scale: %u MiB)" % max([(sample.records['SwapTotal'] - sample.records['SwapFree'])/1024 for sample in mem_stats]), \
				 _theme_color('mem_swap'), off_x + 480, curr_y+20, leg_s)
		draw_box_ticks(ctx, chart_rect, sec_w)
		draw_annotations(ctx, proc_tree, trace.times, chart_rect)
		draw_chart(ctx, _theme_color('mem_buffers'), True, chart_rect, \
			   [(sample.time, sample.records['MemTotal'] - sample.records['MemFree']) for sample in trace.mem_stats], \
			   proc_tree, [0, mem_scale])
		draw_chart(ctx, _theme_color('mem_used'), True, chart_rect, \
			   [(sample.time, sample.records['MemTotal'] - sample.records['MemFree'] - sample.records['Buffers']) for sample in mem_stats], \
			   proc_tree, [0, mem_scale])
		draw_chart(ctx, _theme_color('mem_cached'), True, chart_rect, \
			   [(sample.time, sample.records['Cached']) for sample in mem_stats], \
			   proc_tree, [0, mem_scale])
		draw_chart(ctx, _theme_color('mem_swap'), False, chart_rect, \
			   [(sample.time, float(sample.records['SwapTotal'] - sample.records['SwapFree'])) for sample in mem_stats], \
			   proc_tree, None)

		curr_y = curr_y + meminfo_bar_h

	return curr_y

#
# Render the chart.
#
def render(ctx, options, xscale, trace, render_state=None):
	(w, h) = extents (options, xscale, trace)
	global OPTIONS, THEME
	OPTIONS = options.app_options
	THEME = _load_render_theme(OPTIONS)
	if render_state is not None:
		render_state.clear()
		render_state['process_bounds'] = []

	proc_tree = options.proc_tree (trace)

	# x, y, w, h
	clip = _clip_extents_to_rect(ctx.clip_extents())

	sec_w = int (xscale * sec_w_base)
	ctx.set_line_width(1.0)
	ctx.select_font_face(FONT_NAME)
	draw_fill_rect(ctx, _theme_color('canvas'), (0, 0, max(w, MIN_IMG_W), h))
	w -= 2*off_x
	# draw the title and headers
	if proc_tree.idle:
		duration = proc_tree.idle
	else:
		duration = proc_tree.duration

	if not options.kernel_only:
		curr_y = draw_header (ctx, trace.headers, duration)
	else:
		curr_y = off_y;

	if options.charts:
		curr_y = render_charts (ctx, options, clip, trace, curr_y, w, h, sec_w)

	# draw process boxes
	proc_height = h
	if proc_tree.taskstats and options.cumulative:
		proc_height -= CUML_HEIGHT

	draw_process_bar_chart(ctx, clip, options, proc_tree, trace.times,
			       curr_y, w, proc_height, sec_w, render_state)

	curr_y = proc_height
	ctx.set_font_size(SIG_FONT_SIZE)
	draw_text(ctx, SIGNATURE, _theme_color('signature'), off_x + 5, proc_height - 8)

	# draw a cumulative CPU-time-per-process graph
	if proc_tree.taskstats and options.cumulative:
		cuml_rect = (off_x, curr_y + off_y, w, CUML_HEIGHT/2 - off_y * 2)
		if clip_visible (clip, cuml_rect):
			draw_cuml_graph(ctx, proc_tree, cuml_rect, duration, sec_w, STAT_TYPE_CPU)

	# draw a cumulative I/O-time-per-process graph
	if proc_tree.taskstats and options.cumulative:
		cuml_rect = (off_x, curr_y + off_y * 100, w, CUML_HEIGHT/2 - off_y * 2)
		if clip_visible (clip, cuml_rect):
			draw_cuml_graph(ctx, proc_tree, cuml_rect, duration, sec_w, STAT_TYPE_IO)

def draw_process_bar_chart(ctx, clip, options, proc_tree, times, curr_y, w, h, sec_w, render_state=None):
	header_size = 0
	if not options.kernel_only:
		header_size = _draw_process_state_legend(ctx, curr_y)

	chart_rect = [off_x, curr_y + header_size + 15,
		      w, h - 2 * off_y - (curr_y + header_size + 15) + proc_h]
	ctx.set_font_size (PROC_TEXT_FONT_SIZE)

	draw_box_ticks (ctx, chart_rect, sec_w)
	if sec_w > 100:
		nsec = 1
	else:
		nsec = 5
	draw_sec_labels (ctx, chart_rect, sec_w, nsec)
	draw_annotations (ctx, proc_tree, times, chart_rect)

	y_positions = _build_process_y_positions(proc_tree, curr_y + header_size + 15)
	for root in proc_tree.process_tree:
		if y_positions[root] > clip[1] + clip[3]:
			break
		draw_processes_recursively(ctx, root, proc_tree, y_positions, proc_h, chart_rect, clip, render_state)


def draw_header (ctx, headers, duration):
	toshow = [
	  ('system.uname', 'uname', lambda s: s),
	  ('system.release', 'release', lambda s: s),
	  ('system.cpu', 'CPU', lambda s: re.sub(r'model name\s*:\s*', '', s, 1)),
	  ('system.kernel.options', 'kernel options', lambda s: s),
	]

	header_y = ctx.font_extents()[2] + 10
	ctx.set_font_size(TITLE_FONT_SIZE)
	draw_text(ctx, headers['title'], _theme_color('text'), off_x, header_y)
	ctx.set_font_size(TEXT_FONT_SIZE)

	for (headerkey, headertitle, mangle) in toshow:
		header_y += ctx.font_extents()[2]
		if headerkey in headers:
			value = headers.get(headerkey)
		else:
			value = ""
		txt = headertitle + ': ' + mangle(value)
		draw_text(ctx, txt, _theme_color('text'), off_x, header_y)

	dur = duration / 100.0
	txt = 'time : %02d:%05.2f' % (math.floor(dur/60), dur - 60 * math.floor(dur/60))
	if headers.get('system.maxpid') is not None:
		txt = txt + '      max pid: %s' % (headers.get('system.maxpid'))

	header_y += ctx.font_extents()[2]
	draw_text (ctx, txt, _theme_color('text'), off_x, header_y)

	return header_y

def draw_processes_recursively(ctx, proc, proc_tree, y_positions, proc_h, rect, clip, render_state=None) :
	x, y, w, h = _process_block_rect(proc, proc_tree, y_positions, rect)
	highlighted = process_matches_search(proc, getattr(OPTIONS, 'process_search', ''))
	selected = _is_selected_process(proc)
	if render_state is not None:
		render_state['process_bounds'].append((proc, (x, y, w, h)))

	draw_process_activity_colors(ctx, proc, proc_tree, x, y, w, proc_h, rect, clip)
	draw_rect(ctx, _theme_color('proc_border'), (x, y, w, proc_h))
	if selected:
		selection_color = _selection_highlight_color()
		draw_fill_rect(ctx, selection_color, (x, y + proc_h - 3, min(max(w, 1), 8), 3))
		ctx.set_line_width(2.0)
		draw_rect(ctx, selection_color, (x, y, w, proc_h))
		ctx.set_line_width(1.0)
	if highlighted:
		highlight_color = _search_highlight_color()
		draw_fill_rect(ctx, highlight_color, (x, y, min(max(w, 1), 3), proc_h))
		ctx.set_line_width(2.0)
		draw_rect(ctx, highlight_color, (x, y, w, proc_h))
		ctx.set_line_width(1.0)
	ipid = int(proc.pid)
	if not OPTIONS.show_all:
		cmdString = proc.cmd
	else:
		cmdString = ''
	if (OPTIONS.show_pid or OPTIONS.show_all) and ipid != 0:
		cmdString = cmdString + " [" + str(ipid // 1000) + "]"
	if OPTIONS.show_all:
		if proc.args:
			cmdString = cmdString + " '" + "' '".join(proc.args) + "'"
		else:
			cmdString = cmdString + " " + proc.exe

	label_color = _search_highlight_color() if highlighted else _theme_color('proc_text')
	draw_label_in_box(ctx, label_color, cmdString, x, y + proc_h - 4, w, rect[0] + rect[2])

	for child in proc.child_list:
		child_y = y_positions[child]
		if child_y > clip[1] + clip[3]:
			break
		child_x, child_y = draw_processes_recursively(ctx, child, proc_tree, y_positions, proc_h, rect, clip, render_state)
		if _should_draw_parent_connector(proc):
			draw_process_connecting_lines(ctx, x, y, child_x, child_y, proc_h)

	return x, y


def draw_process_activity_colors(ctx, proc, proc_tree, x, y, w, proc_h, rect, clip):

	if y > clip[1] + clip[3] or y + proc_h + 2 < clip[1]:
		return

	draw_fill_rect(ctx, _theme_color('proc_sleeping'), (x, y, w, proc_h))

	last_tx = -1
	for sample in proc.samples :
		tx = rect[0] + round(((sample.time - proc_tree.start_time) * rect[2] / proc_tree.duration))

		# samples are sorted chronologically
		if tx < clip[0]:
			continue
		if tx > clip[0] + clip[2]:
			break

		tw = round(proc_tree.sample_period * rect[2] / float(proc_tree.duration))
		if last_tx != -1 and abs(last_tx - tx) <= tw:
			tw -= last_tx - tx
			tx = last_tx
		tw = max (tw, 1) # nice to see at least something

		last_tx = tx + tw
		state = get_proc_state( sample.state )

		color = _state_color(state)
		if state == STATE_RUNNING:
			alpha = min (sample.cpu_sample.user + sample.cpu_sample.sys, 1.0)
			color = tuple(list(_theme_color('proc_running')[0:3]) + [alpha])
#			print "render time %d [ tx %d tw %d ], sample state %s color %s alpha %g" % (sample.time, tx, tw, state, color, alpha)
		elif state == STATE_SLEEPING:
			continue

		draw_fill_rect(ctx, color, (tx, y, tw, proc_h))

def draw_process_connecting_lines(ctx, px, py, x, y, proc_h):
	ctx.set_source_rgba(*_theme_color('dependency'))
	ctx.set_dash([2, 2])
	if abs(px - x) < 3:
		dep_off_x = 3
		dep_off_y = proc_h / 4
		ctx.move_to(x, y + proc_h / 2)
		ctx.line_to(px - dep_off_x, y + proc_h / 2)
		ctx.line_to(px - dep_off_x, py - dep_off_y)
		ctx.line_to(px, py - dep_off_y)
	else:
		ctx.move_to(x, y + proc_h / 2)
		ctx.line_to(px, y + proc_h / 2)
		ctx.line_to(px, py)
	ctx.stroke()
	ctx.set_dash([])

# elide the bootchart collector - it is quite distorting
def elide_bootchart(proc):
	return proc.cmd == 'bootchartd' or proc.cmd == 'bootchart-colle'

class CumlSample:
	def __init__(self, proc):
		self.cmd = proc.cmd
		self.samples = []
		self.merge_samples (proc)
		self.color = None

	def merge_samples(self, proc):
		self.samples.extend (proc.samples)
		self.samples.sort (key = lambda p: p.time)

	def __next__(self):
		global palette_idx
		palette_idx += HSV_STEP
		return palette_idx

	def get_color(self):
		if self.color is None:
			i = next(self) % HSV_MAX_MOD
			h = 0.0
			if i != 0:
				h = (1.0 * i) / HSV_MAX_MOD
			palette = THEME['cumulative_palette']
			s = palette['saturation']
			v = palette['value']
			c = colorsys.hsv_to_rgb (h, s, v)
			self.color = (c[0], c[1], c[2], 1.0)
		return self.color


def draw_cuml_graph(ctx, proc_tree, chart_bounds, duration, sec_w, stat_type):
	global palette_idx
	palette_idx = 0

	time_hash = {}
	total_time = 0.0
	m_proc_list = {}

	if stat_type is STAT_TYPE_CPU:
		sample_value = 'cpu'
	else:
		sample_value = 'io'
	for proc in proc_tree.process_list:
		if elide_bootchart(proc):
			continue

		for sample in proc.samples:
			total_time += getattr(sample.cpu_sample, sample_value)
			if not sample.time in time_hash:
				time_hash[sample.time] = 1

		# merge pids with the same cmd
		if not proc.cmd in m_proc_list:
			m_proc_list[proc.cmd] = CumlSample (proc)
			continue
		s = m_proc_list[proc.cmd]
		s.merge_samples (proc)

	# all the sample times
	times = sorted(time_hash)
	if len (times) < 2 or total_time == 0:
		print("degenerate boot chart")
		return

	pix_per_ns = chart_bounds[3] / total_time
#	print "total time: %g pix-per-ns %g" % (total_time, pix_per_ns)

	# FIXME: we have duplicates in the process list too [!] - why !?

	# Render bottom up, left to right
	below = {}
	for time in times:
		below[time] = chart_bounds[1] + chart_bounds[3]

	# same colors each time we render
	random.seed (0)

	ctx.set_line_width(1)

	legends = []
	labels = []

	# render each pid in order
	for cs in list(m_proc_list.values()):
		row = {}
		cuml = 0.0

		# print "pid : %s -> %g samples %d" % (proc.cmd, cuml, len (cs.samples))
		for sample in cs.samples:
			cuml += getattr(sample.cpu_sample, sample_value)
			row[sample.time] = cuml

		process_total_time = cuml

		# hide really tiny processes
		if cuml * pix_per_ns <= 2:
			continue

		last_time = times[0]
		y = last_below = below[last_time]
		last_cuml = cuml = 0.0

		ctx.set_source_rgba(*cs.get_color())
		for time in times:
			render_seg = False

			# did the underlying trend increase ?
			if below[time] != last_below:
				last_below = below[last_time]
				last_cuml = cuml
				render_seg = True

			# did we move up a pixel increase ?
			if time in row:
				nc = round (row[time] * pix_per_ns)
				if nc != cuml:
					last_cuml = cuml
					cuml = nc
					render_seg = True

#			if last_cuml > cuml:
#				assert fail ... - un-sorted process samples

			# draw the trailing rectangle from the last time to
			# before now, at the height of the last segment.
			if render_seg:
				w = math.ceil ((time - last_time) * chart_bounds[2] / proc_tree.duration) + 1
				x = chart_bounds[0] + round((last_time - proc_tree.start_time) * chart_bounds[2] / proc_tree.duration)
				ctx.rectangle (x, below[last_time] - last_cuml, w, last_cuml)
				ctx.fill()
#				ctx.stroke()
				last_time = time
				y = below [time] - cuml

			row[time] = y

		# render the last segment
		x = chart_bounds[0] + round((last_time - proc_tree.start_time) * chart_bounds[2] / proc_tree.duration)
		y = below[last_time] - cuml
		ctx.rectangle (x, y, chart_bounds[2] - x, cuml)
		ctx.fill()
#		ctx.stroke()

		# render legend if it will fit
		if cuml > 8:
			label = cs.cmd
			extnts = ctx.text_extents(label)
			label_w = extnts[2]
			label_h = extnts[3]
#			print "Text extents %g by %g" % (label_w, label_h)
			labels.append((label,
				       chart_bounds[0] + chart_bounds[2] - label_w - off_x * 2,
				       y + (cuml + label_h) / 2))
			if cs in legends:
				print("ARGH - duplicate process in list !")

		legends.append ((cs, process_total_time))

		below = row

	# render grid-lines over the top
	draw_box_ticks(ctx, chart_bounds, sec_w)

	# render labels
	for l in labels:
		draw_text(ctx, l[0], _theme_color('text'), l[1], l[2])

	# Render legends
	font_height = 20
	label_width = 300
	LEGENDS_PER_COL = 15
	LEGENDS_TOTAL = 45
	ctx.set_font_size (TITLE_FONT_SIZE)
	dur_secs = duration / 100
	cpu_secs = total_time / 1000000000

	# misleading - with multiple CPUs ...
#	idle = ((dur_secs - cpu_secs) / dur_secs) * 100.0
	if stat_type is STAT_TYPE_CPU:
		label = "Cumulative CPU usage, by process; total CPU: " \
			" %.5g(s) time: %.3g(s)" % (cpu_secs, dur_secs)
	else:
		label = "Cumulative I/O usage, by process; total I/O: " \
			" %.5g(s) time: %.3g(s)" % (cpu_secs, dur_secs)

	draw_text(ctx, label, _theme_color('text'), chart_bounds[0] + off_x,
		  chart_bounds[1] + font_height)

	i = 0
	legends = sorted(legends, key=itemgetter(1), reverse=True)
	ctx.set_font_size(TEXT_FONT_SIZE)
	for t in legends:
		cs = t[0]
		time = t[1]
		x = chart_bounds[0] + off_x + int (i/LEGENDS_PER_COL) * label_width
		y = chart_bounds[1] + font_height * ((i % LEGENDS_PER_COL) + 2)
		str = "%s - %.0f(ms) (%2.2f%%)" % (cs.cmd, time/1000000, (time/total_time) * 100.0)
		draw_legend_box(ctx, str, cs.color, x, y, leg_s)
		i = i + 1
		if i >= LEGENDS_TOTAL:
			break
