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

import math
from collections import Counter
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GObject', '2.0')
from gi.repository import Gtk, Gdk, GObject
from . import draw
from . import themes
from .draw import RenderOptions


def _zoom_origin_for_focus(origin, focus, old_zoom, new_zoom):
    return origin + (focus / old_zoom) - (focus / new_zoom)


def _pointer_zoom_event_mask():
    return Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK


def _widget_to_document_coords(widget_x, widget_y, zoom_ratio, origin_x, origin_y):
    return (widget_x / zoom_ratio) + origin_x, (widget_y / zoom_ratio) + origin_y


def _point_in_rect(x, y, rect):
    rect_x, rect_y, rect_w, rect_h = rect
    return rect_x <= x <= rect_x + rect_w and rect_y <= y <= rect_y + rect_h


def _process_at_position(process_bounds, doc_x, doc_y):
    for proc, rect in reversed(process_bounds):
        if _point_in_rect(doc_x, doc_y, rect):
            return proc
    return None


def _motion_exceeds_drag_threshold(start_x, start_y, x, y, threshold):
    return math.hypot(x - start_x, y - start_y) >= threshold


def _zoom_ratio_for_scroll(current_zoom, direction, delta_y, zoom_increment):
    if direction == Gdk.ScrollDirection.UP:
        return current_zoom * zoom_increment
    if direction == Gdk.ScrollDirection.DOWN:
        return current_zoom / zoom_increment
    if direction == Gdk.ScrollDirection.SMOOTH and abs(delta_y) > 0.01:
        return current_zoom * math.pow(zoom_increment, -delta_y)
    return None


def _widget_background_color(app_options):
    resolved_theme = getattr(app_options, 'resolved_theme', None)
    if resolved_theme is None:
        try:
            resolved_theme = themes.resolve_theme_name(getattr(app_options, 'theme', themes.DEFAULT_THEME_NAME), False)
        except themes.ThemeError:
            resolved_theme = themes.DEFAULT_THEME_NAME
    theme = themes.load_theme(resolved_theme)
    return theme['colors']['background']


def _widget_theme_color(app_options, color_name):
    resolved_theme = getattr(app_options, 'resolved_theme', None)
    if resolved_theme is None:
        try:
            resolved_theme = themes.resolve_theme_name(getattr(app_options, 'theme', themes.DEFAULT_THEME_NAME), False)
        except themes.ThemeError:
            resolved_theme = themes.DEFAULT_THEME_NAME
    theme = themes.load_theme(resolved_theme)
    return theme['colors'][color_name]


def _minimum_zoom_ratio_for_width(viewport_width, chart_width):
    if viewport_width <= 0 or chart_width <= 0:
        return 0.0
    return float(viewport_width) / float(chart_width)


def _format_tick_duration(value):
    return "%.2fs" % (float(value) / 100.0)


def _format_ns_duration(value):
    if value >= 1000000000.0:
        return "%.3fs" % (value / 1000000000.0)
    return "%.1fms" % (value / 1000000.0)


def _format_percent(value):
    return "%.1f%%" % value


def _process_cpu_sparkline(trace, proc):
    if not proc.samples:
        return None
    if getattr(trace, 'taskstats', None):
        values = [(sample.time, sample.cpu_sample.user + sample.cpu_sample.sys) for sample in proc.samples]
        return ('CPU activity', values)
    values = [(sample.time, 100.0 * (sample.cpu_sample.user + sample.cpu_sample.sys)) for sample in proc.samples]
    return ('Sampled CPU', values)


def _process_io_delay_sparkline(trace, proc):
    if not getattr(trace, 'taskstats', None) or not proc.samples:
        return None
    values = [(sample.time, sample.cpu_sample.io) for sample in proc.samples]
    if not any(value > 0.0 for (_, value) in values):
        return None
    return ('Blk I/O delay', values)


def _process_state_timeline(proc):
    if not proc.samples:
        return None
    return [(sample.time, sample.state) for sample in proc.samples]


def _build_process_details_rows(trace, proc):
    sample_count = len(proc.samples)
    parent_desc = 'N/A'
    if proc.parent is not None:
        parent_desc = "%s [%d]" % (proc.parent.cmd, proc.parent.pid // 1000)
    state_counts = Counter(sample.state for sample in proc.samples)

    rows = [
        ('PID', str(proc.pid // 1000)),
        ('PPID', str(proc.ppid // 1000) if proc.ppid else 'N/A'),
        ('Parent', parent_desc),
        ('Children', str(len(proc.child_list))),
        ('Command', proc.cmd),
        ('Executable', proc.exe),
        ('Arguments', ' '.join(str(arg) for arg in proc.args) if proc.args else 'N/A'),
        ('Start', _format_tick_duration(proc.start_time)),
        ('Duration', _format_tick_duration(proc.duration)),
        ('Samples', str(sample_count)),
        ('Active', 'Yes' if proc.active else 'No'),
        ('Last state', proc.samples[-1].state if sample_count else 'N/A'),
    ]

    if sample_count:
        rows.extend([
            ('First sample', _format_tick_duration(proc.samples[0].time)),
            ('Last sample', _format_tick_duration(proc.samples[-1].time)),
        ])

    for flag, _state, _legend_label, sidebar_label, _color_name in draw.PROCESS_STATE_INFO:
        count = state_counts.get(flag, 0)
        ratio = (100.0 * count / sample_count) if sample_count else 0.0
        state_label = sidebar_label.replace(' samples', '')
        rows.append(("%% %s:" % state_label, _format_percent(ratio)))

    if sample_count:
        if getattr(trace, 'taskstats', None):
            total_cpu_ns = sum(sample.cpu_sample.user + sample.cpu_sample.sys for sample in proc.samples)
            total_io_ns = sum(sample.cpu_sample.io for sample in proc.samples)
            total_swap_ns = sum(sample.cpu_sample.swap for sample in proc.samples)
            rows.extend([
                ('CPU runtime', _format_ns_duration(total_cpu_ns)),
                ('Blk I/O delay', _format_ns_duration(total_io_ns)),
                ('Swap-in delay', _format_ns_duration(total_swap_ns)),
            ])
        else:
            sampled_cpu = [100.0 * (sample.cpu_sample.user + sample.cpu_sample.sys) for sample in proc.samples]
            rows.extend([
                ('Peak sampled CPU', _format_percent(max(sampled_cpu))),
                ('Avg sampled CPU', _format_percent(sum(sampled_cpu) / len(sampled_cpu))),
            ])

    return rows


class Sparkline(Gtk.DrawingArea):

    HEIGHT = 52

    def __init__(self, app_options, color_name):
        super().__init__()

        self.app_options = app_options
        self.color_name = color_name
        self.series = []
        self.set_size_request(-1, self.HEIGHT)
        self.set_hexpand(True)

    def set_series(self, series):
        self.series = series or []
        self.queue_draw()

    def do_draw(self, cr):
        alloc = self.get_allocation()
        width = max(float(alloc.width), 1.0)
        height = max(float(alloc.height), 1.0)
        bg = _widget_background_color(self.app_options)
        border = _widget_theme_color(self.app_options, 'border')
        line = _widget_theme_color(self.app_options, self.color_name)

        cr.set_source_rgba(*bg)
        cr.paint()

        cr.set_source_rgba(border[0], border[1], border[2], 0.6)
        cr.rectangle(0.5, 0.5, width - 1.0, height - 1.0)
        cr.stroke()

        if len(self.series) < 2:
            return False

        values = [value for (_, value) in self.series]
        min_value = min(values)
        max_value = max(values)
        span = max(max_value - min_value, 1e-9)
        left_pad = 4.0
        right_pad = 4.0
        top_pad = 4.0
        bottom_pad = 4.0
        usable_w = max(width - left_pad - right_pad, 1.0)
        usable_h = max(height - top_pad - bottom_pad, 1.0)

        points = []
        if len(self.series) == 1:
            x_step = 0.0
        else:
            x_step = usable_w / float(len(self.series) - 1)
        for idx, (_, value) in enumerate(self.series):
            x = left_pad + idx * x_step
            y = height - bottom_pad - ((value - min_value) / span) * usable_h
            points.append((x, y))

        first_x, first_y = points[0]
        cr.set_source_rgba(line[0], line[1], line[2], 0.18)
        cr.move_to(first_x, height - bottom_pad)
        for x, y in points:
            cr.line_to(x, y)
        last_x, _ = points[-1]
        cr.line_to(last_x, height - bottom_pad)
        cr.close_path()
        cr.fill()

        cr.set_source_rgba(*line)
        cr.set_line_width(1.5)
        cr.move_to(first_x, first_y)
        for x, y in points[1:]:
            cr.line_to(x, y)
        cr.stroke()
        return False


class StateTimeline(Gtk.DrawingArea):

    HEIGHT = 14

    def __init__(self, app_options):
        super().__init__()

        self.app_options = app_options
        self.series = []
        self.set_size_request(-1, self.HEIGHT)
        self.set_hexpand(True)

    def set_series(self, series):
        self.series = series or []
        self.queue_draw()

    def do_draw(self, cr):
        alloc = self.get_allocation()
        width = max(float(alloc.width), 1.0)
        height = max(float(alloc.height), 1.0)
        bg = _widget_background_color(self.app_options)
        border = _widget_theme_color(self.app_options, 'border')

        cr.set_source_rgba(*bg)
        cr.paint()

        cr.set_source_rgba(border[0], border[1], border[2], 0.6)
        cr.rectangle(0.5, 0.5, width - 1.0, height - 1.0)
        cr.stroke()

        if not self.series:
            return False

        left_pad = 4.0
        right_pad = 4.0
        top_pad = 4.0
        bottom_pad = 4.0
        usable_w = max(width - left_pad - right_pad, 1.0)
        usable_h = max(height - top_pad - bottom_pad, 1.0)
        bar_w = max(usable_w / float(len(self.series)), 1.0)

        for idx, (_time, state_flag) in enumerate(self.series):
            _state, _legend_label, _sidebar_label, color_name = draw.PROCESS_STATE_BY_FLAG.get(state_flag, (None, None, None, 'proc_sleeping'))
            color = _widget_theme_color(self.app_options, color_name)
            x = left_pad + idx * bar_w
            cr.set_source_rgba(*color)
            cr.rectangle(x, top_pad, max(bar_w, 1.0), usable_h)
            cr.fill()
        return False


class ProcessDetailsPane(Gtk.Frame):

    WIDTH = 320

    def __init__(self, trace, app_options):
        super().__init__(label='Process Details')

        self.trace = trace
        self.app_options = app_options
        self.set_shadow_type(Gtk.ShadowType.IN)
        self.set_size_request(self.WIDTH, -1)

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        container.set_border_width(10)
        self.add(container)

        self.title_label = Gtk.Label()
        self.title_label.set_xalign(0.0)
        self.title_label.set_selectable(True)

        self.subtitle_label = Gtk.Label()
        self.subtitle_label.set_xalign(0.0)
        self.subtitle_label.set_line_wrap(True)
        self.subtitle_label.set_max_width_chars(36)

        self.sparkline_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        self.rows_grid = Gtk.Grid(column_spacing=12, row_spacing=6)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        scrolled.add(self.rows_grid)

        container.pack_start(self.title_label, False, False, 0)
        container.pack_start(self.subtitle_label, False, False, 0)
        container.pack_start(self.sparkline_box, False, False, 0)
        container.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        container.pack_start(scrolled, True, True, 0)

        self.set_process(None)

    def _clear_rows(self):
        for child in self.rows_grid.get_children():
            self.rows_grid.remove(child)

    def _clear_sparklines(self):
        for child in self.sparkline_box.get_children():
            self.sparkline_box.remove(child)

    def _add_sparkline(self, title, color_name, series, state_series=None):
        label = Gtk.Label(label=title)
        label.set_xalign(0.0)
        sparkline = Sparkline(self.app_options, color_name)
        sparkline.set_series(series)

        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row_box.pack_start(sparkline, True, True, 0)
        if state_series is not None:
            timeline = StateTimeline(self.app_options)
            timeline.set_series(state_series)
            timeline.set_tooltip_text('Process state timeline')
            row_box.pack_start(timeline, False, False, 0)

        self.sparkline_box.pack_start(label, False, False, 0)
        self.sparkline_box.pack_start(row_box, False, False, 0)

    def _add_row(self, row, key, value):
        key_label = Gtk.Label(label=key)
        key_label.set_xalign(0.0)

        value_label = Gtk.Label(label=value)
        value_label.set_xalign(0.0)
        value_label.set_selectable(True)
        value_label.set_line_wrap(True)
        value_label.set_max_width_chars(32)

        self.rows_grid.attach(key_label, 0, row, 1, 1)
        self.rows_grid.attach(value_label, 1, row, 1, 1)

    def set_process(self, proc):
        self._clear_rows()
        self._clear_sparklines()
        if proc is None:
            self.title_label.set_text('No process selected')
            self.subtitle_label.set_text('Click a process block to inspect the data available for that process.')
            return

        self.title_label.set_text('%s [%d]' % (proc.cmd, proc.pid // 1000))
        if getattr(self.trace, 'taskstats', None):
            self.subtitle_label.set_text('Taskstats trace: runtime and delay counters are available.')
        else:
            self.subtitle_label.set_text('Minimal proc_ps trace: sampled process state and CPU-style metrics only.')

        cpu_sparkline = _process_cpu_sparkline(self.trace, proc)
        if cpu_sparkline is not None:
            self._add_sparkline(cpu_sparkline[0], 'cpu', cpu_sparkline[1], _process_state_timeline(proc))
        io_sparkline = _process_io_delay_sparkline(self.trace, proc)
        if io_sparkline is not None:
            self._add_sparkline(io_sparkline[0], 'io', io_sparkline[1])

        for row, (key, value) in enumerate(_build_process_details_rows(self.trace, proc)):
            self._add_row(row, key, value)

        self.sparkline_box.show_all()
        self.rows_grid.show_all()

class PyBootchartWidget(Gtk.DrawingArea):
    __gsignals__ = {
        'clicked': (GObject.SignalFlags.RUN_LAST, None, (str, Gdk.Event)),
        'position-changed': (GObject.SignalFlags.RUN_LAST, None, (int, int)),
        'set-scroll-adjustments': (GObject.SignalFlags.RUN_LAST, None, (Gtk.Adjustment, Gtk.Adjustment)),
    }

    def __init__(self, trace, options, xscale):
        super().__init__()

        self.trace = trace
        self.options = options

        self.set_can_focus(True)
        self.add_events(_pointer_zoom_event_mask())

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect("button-press-event", self.on_area_button_press)
        self.connect("button-release-event", self.on_area_button_release)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.POINTER_MOTION_HINT_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect("motion-notify-event", self.on_area_motion_notify)
        self.connect("scroll-event", self.on_area_scroll_event)
        self.connect('key-press-event', self.on_key_press_event)

        self.connect('set-scroll-adjustments', self.on_set_scroll_adjustments)
        self.connect("size-allocate", self.on_allocation_size_changed)
        self.connect("position-changed", self.on_position_changed)

        self.zoom_ratio = 1.0
        self.xscale = xscale
        self.x, self.y = 0.0, 0.0

        self.chart_width, self.chart_height = draw.extents(self.options, self.xscale, self.trace)
        self.hadj = None
        self.vadj = None
        self.hadj_changed_signal_id = None
        self.vadj_changed_signal_id = None
        self.prevmousex = None
        self.prevmousey = None
        self.press_start_x = None
        self.press_start_y = None
        self.pressed_button = None
        self.dragging = False
        self.process_bounds = []
        self.process_selected_handler = None

    def do_draw(self, cr):
        allocation = self.get_allocation()
        cr.set_source_rgba(*_widget_background_color(self.options.app_options))
        cr.paint()
        cr.save()
        cr.scale(self.zoom_ratio, self.zoom_ratio)
        cr.translate(-self.x, -self.y)
        render_state = {}
        draw.render(cr, self.options, self.xscale, self.trace, render_state)
        cr.restore()
        self.process_bounds = render_state.get('process_bounds', [])
        return False

    def position_changed(self):
        self.emit("position-changed", self.x, self.y)

    ZOOM_INCREMENT = 1.25
    CLICK_DRAG_THRESHOLD = 5.0

    def _default_zoom_focus(self):
        allocation = self.get_allocation()
        return allocation.width / 2.0, allocation.height / 2.0

    def _minimum_zoom_ratio(self):
        allocation = self.get_allocation()
        return _minimum_zoom_ratio_for_width(allocation.width, self.chart_width)

    def set_process_selected_handler(self, handler):
        self.process_selected_handler = handler

    def _set_grab_cursor(self):
        display = self.get_display()
        window = self.get_window()
        if window:
            cursor = Gdk.Cursor.new_from_name(display, 'grab') or Gdk.Cursor.new(Gdk.CursorType.FLEUR)
            window.set_cursor(cursor)

    def _set_default_cursor(self):
        window = self.get_window()
        if window:
            cursor = Gdk.Cursor.new_from_name(self.get_display(), 'default') or Gdk.Cursor.new(Gdk.CursorType.ARROW)
            window.set_cursor(cursor)

    def _reset_pointer_tracking(self):
        self.prevmousex = None
        self.prevmousey = None
        self.press_start_x = None
        self.press_start_y = None
        self.pressed_button = None
        self.dragging = False

    def _select_process_at(self, widget_x, widget_y):
        if self.process_selected_handler is None:
            return False
        doc_x, doc_y = _widget_to_document_coords(widget_x, widget_y, self.zoom_ratio, self.x, self.y)
        proc = _process_at_position(self.process_bounds, doc_x, doc_y)
        if proc is None:
            return False
        self.process_selected_handler(proc)
        return True

    def _clamp_view_origin(self, origin, adj):
        if adj is None:
            return max(0.0, origin)
        max_origin = max(0.0, (adj.get_upper() - adj.get_page_size()) / self.zoom_ratio)
        return min(max(origin, 0.0), max_origin)

    def zoom_image(self, zoom_ratio, focus_x=None, focus_y=None):
        old_zoom = self.zoom_ratio
        minimum_zoom = self._minimum_zoom_ratio()
        zoom_ratio = max(zoom_ratio, minimum_zoom)
        if focus_x is None or focus_y is None:
            focus_x, focus_y = self._default_zoom_focus()

        target_x = _zoom_origin_for_focus(self.x, focus_x, old_zoom, zoom_ratio)
        target_y = _zoom_origin_for_focus(self.y, focus_y, old_zoom, zoom_ratio)

        self.zoom_ratio = zoom_ratio
        self._set_scroll_adjustments(self.hadj, self.vadj)
        self.x = self._clamp_view_origin(target_x, self.hadj)
        self.y = self._clamp_view_origin(target_y, self.vadj)
        self.position_changed()
        self.queue_draw()

    def zoom_to_rect(self, rect):
        zoom_ratio = float(rect.width) / float(self.chart_width)
        self.zoom_image(zoom_ratio)
        self.x = 0
        self.position_changed()

    def set_xscale(self, xscale):
        old_mid_x = self.x + (self.hadj.get_page_size() / 2 if self.hadj else 0)
        self.xscale = xscale
        self.chart_width, self.chart_height = draw.extents(self.options, self.xscale, self.trace)
        new_x = old_mid_x
        self.zoom_image(self.zoom_ratio)

    def on_expand(self, action):
        self.set_xscale(self.xscale * 1.5)

    def on_contract(self, action):
        self.set_xscale(self.xscale / 1.5)

    def on_zoom_in(self, action):
        self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)

    def on_zoom_out(self, action):
        self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)

    def on_zoom_fit(self, action):
        self.zoom_to_rect(self.get_allocation())

    def on_zoom_100(self, action):
        self.zoom_image(1.0)
        self.set_xscale(1.0)

    def show_toggled(self, button):
        self.options.app_options.show_all = button.get_property('active')
        self.queue_draw()

    def process_label_align_toggled(self, button):
        if button.get_property('active'):
            self.options.app_options.process_label_align = 'left'
        else:
            self.options.app_options.process_label_align = 'center'
        self.queue_draw()

    POS_INCREMENT = 100

    def on_key_press_event(self, widget, event):
        keyval = event.keyval
        if keyval == Gdk.KEY_Left:
            self.x -= self.POS_INCREMENT / self.zoom_ratio
        elif keyval == Gdk.KEY_Right:
            self.x += self.POS_INCREMENT / self.zoom_ratio
        elif keyval == Gdk.KEY_Up:
            self.y -= self.POS_INCREMENT / self.zoom_ratio
        elif keyval == Gdk.KEY_Down:
            self.y += self.POS_INCREMENT / self.zoom_ratio
        else:
            return False
        self.queue_draw()
        self.position_changed()
        return True

    def on_area_button_press(self, area, event):
        if event.button == 2 or event.button == 1:
            self.prevmousex = event.x
            self.prevmousey = event.y
            self.press_start_x = event.x
            self.press_start_y = event.y
            self.pressed_button = event.button
            self.dragging = False
            if event.button == 2:
                self._set_grab_cursor()
        return False

    def on_area_button_release(self, area, event):
        if event.button == 2 or event.button == 1:
            should_select = event.button == 1 and self.pressed_button == 1 and not self.dragging
            if self.dragging or event.button == 2:
                self._set_default_cursor()
            if should_select:
                self._select_process_at(event.x, event.y)
            self._reset_pointer_tracking()
            return True
        return False

    def on_area_scroll_event(self, area, event):
        delta_y = 0.0
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            success, delta_x, delta_y = event.get_scroll_deltas()
            if not success:
                return False

        new_zoom = _zoom_ratio_for_scroll(self.zoom_ratio, event.direction, delta_y, self.ZOOM_INCREMENT)
        if new_zoom is not None:
            self.zoom_image(new_zoom, event.x, event.y)
            return True
        return False

    def on_area_motion_notify(self, area, event):
        state = event.state
        if ((state & Gdk.ModifierType.BUTTON2_MASK) or (state & Gdk.ModifierType.BUTTON1_MASK)) and \
           self.prevmousex is not None and self.prevmousey is not None:
            x, y = int(event.x), int(event.y)
            if not self.dragging:
                if self.pressed_button == 1 and not _motion_exceeds_drag_threshold(self.press_start_x, self.press_start_y, x, y, self.CLICK_DRAG_THRESHOLD):
                    return True
                self.dragging = True
                self._set_grab_cursor()
            # pan the image
            self.x += (self.prevmousex - x) / self.zoom_ratio
            self.y += (self.prevmousey - y) / self.zoom_ratio
            self.queue_draw()
            self.prevmousex = x
            self.prevmousey = y
            self.position_changed()
        return True

    def on_set_scroll_adjustments(self, area, hadj, vadj):
        self._set_scroll_adjustments(hadj, vadj)

    def on_allocation_size_changed(self, widget, allocation):
        if self.hadj:
            self.hadj.set_page_size(allocation.width)
            self.hadj.set_page_increment(allocation.width * 0.9)
        if self.vadj:
            self.vadj.set_page_size(allocation.height)
            self.vadj.set_page_increment(allocation.height * 0.9)
        minimum_zoom = self._minimum_zoom_ratio()
        if minimum_zoom > 0.0 and self.zoom_ratio < minimum_zoom:
            self.zoom_image(minimum_zoom)

    def _set_adj_upper(self, adj, upper):
        changed = False
        value_changed = False

        if adj.get_upper() != upper:
            adj.set_upper(upper)
            changed = True

        max_value = max(0.0, upper - adj.get_page_size())
        if adj.get_value() > max_value:
            adj.set_value(max_value)
            value_changed = True

        if changed:
            adj.changed()
        if value_changed:
            adj.value_changed()

    def _set_scroll_adjustments(self, hadj, vadj):
        if hadj is None:
            hadj = Gtk.Adjustment(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        if vadj is None:
            vadj = Gtk.Adjustment(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        if self.hadj_changed_signal_id is not None and \
           self.hadj is not None and hadj != self.hadj:
            self.hadj.disconnect(self.hadj_changed_signal_id)
        if self.vadj_changed_signal_id is not None and \
           self.vadj is not None and vadj != self.vadj:
            self.vadj.disconnect(self.vadj_changed_signal_id)

        if hadj is not None:
            self.hadj = hadj
            self._set_adj_upper(self.hadj, self.zoom_ratio * self.chart_width)
            self.hadj_changed_signal_id = self.hadj.connect('value-changed', self.on_adjustments_changed)

        if vadj is not None:
            self.vadj = vadj
            self._set_adj_upper(self.vadj, self.zoom_ratio * self.chart_height)
            self.vadj_changed_signal_id = self.vadj.connect('value-changed', self.on_adjustments_changed)

    def on_adjustments_changed(self, adj):
        self.x = self.hadj.get_value() / self.zoom_ratio
        self.y = self.vadj.get_value() / self.zoom_ratio
        self.queue_draw()

    def on_position_changed(self, widget, x, y):
        if self.hadj:
            self.hadj.set_value(x * self.zoom_ratio)
        if self.vadj:
            self.vadj.set_value(y * self.zoom_ratio)

class PyBootchartShell(Gtk.Box):
    ui = '''
    <ui>
            <toolbar name="ToolBar">
                    <toolitem action="Expand"/>
                    <toolitem action="Contract"/>
                    <separator/>
                    <toolitem action="ZoomIn"/>
                    <toolitem action="ZoomOut"/>
                    <toolitem action="ZoomFit"/>
                    <toolitem action="Zoom100"/>
            </toolbar>
    </ui>
    '''
    def __init__(self, window, trace, options, xscale):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self.window = window
        self.chart_widget = PyBootchartWidget(trace, options, xscale)
        self.theme_combo = None
        self.theme_combo_changed_signal_id = None
        self.process_search_entry = None
        self.details_pane = None
        self.details_toggle = None
        self.details_wrapper = None
        self.details_sidebar_width = ProcessDetailsPane.WIDTH
        self.content_paned = None

        # Create a UIManager instance
        uimanager = self.uimanager = Gtk.UIManager()

        # Add the accelerator group to the toplevel window
        accelgroup = uimanager.get_accel_group()
        window.add_accel_group(accelgroup)

        # Create an ActionGroup
        actiongroup = Gtk.ActionGroup('Actions')
        self.actiongroup = actiongroup

        # Create actions
        actiongroup.add_actions((
                ('Expand', Gtk.STOCK_ADD, None, None, None, self.chart_widget.on_expand),
                ('Contract', Gtk.STOCK_REMOVE, None, None, None, self.chart_widget.on_contract),
                ('ZoomIn', Gtk.STOCK_ZOOM_IN, None, None, None, self.chart_widget.on_zoom_in),
                ('ZoomOut', Gtk.STOCK_ZOOM_OUT, None, None, None, self.chart_widget.on_zoom_out),
                ('ZoomFit', Gtk.STOCK_ZOOM_FIT, 'Fit Width', None, None, self.chart_widget.on_zoom_fit),
                ('Zoom100', Gtk.STOCK_ZOOM_100, None, None, None, self.chart_widget.on_zoom_100),
        ))

        # Add the actiongroup to the uimanager
        uimanager.insert_action_group(actiongroup, 0)

        # Add a UI description
        uimanager.add_ui_from_string(self.ui)

        # Scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.add(self.chart_widget)

        content_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        content_paned.set_wide_handle(True)
        content_paned.pack1(scrolled, True, False)
        self.content_paned = content_paned

        # toolbar / h-box
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Create a Toolbar
        toolbar = uimanager.get_widget('/ToolBar')
        hbox.pack_start(toolbar, True, True, 0)

        theme_combo = Gtk.ComboBoxText()
        theme_combo.append(themes.AUTO_THEME_NAME, "Auto")
        theme_combo.append('light', "Light")
        theme_combo.append('dark', "Dark")
        theme_combo.set_active_id(options.app_options.theme)
        self.theme_combo_changed_signal_id = theme_combo.connect('changed', self.on_theme_changed)
        self.theme_combo = theme_combo

        hbox.pack_start(Gtk.Label(label="Theme"), False, True, 0)
        hbox.pack_start(theme_combo, False, True, 0)

        if not options.kernel_only:
            self.details_pane = ProcessDetailsPane(trace, options.app_options)
            self.chart_widget.set_process_selected_handler(self.on_process_selected)
            details_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            details_wrapper.pack_start(self.details_pane, True, True, 0)
            details_wrapper.set_size_request(self.details_sidebar_width, -1)
            self.details_wrapper = details_wrapper
            content_paned.pack2(details_wrapper, False, True)

            details_toggle = Gtk.CheckButton(label="Details")
            details_toggle.set_active(True)
            details_toggle.connect('toggled', self.on_details_toggled)
            self.details_toggle = details_toggle
            hbox.pack_start(details_toggle, False, True, 0)

            search_entry = Gtk.Entry()
            search_entry.set_width_chars(16)
            search_entry.set_placeholder_text("Highlight process")
            search_entry.set_text(getattr(options.app_options, 'process_search', ''))
            search_entry.connect('changed', self.on_process_search_changed)
            self.process_search_entry = search_entry

            hbox.pack_start(Gtk.Label(label="Search"), False, True, 0)
            hbox.pack_start(search_entry, False, True, 0)

            # Misc. options
            button = Gtk.CheckButton(label="Show more")
            button.connect('toggled', self.chart_widget.show_toggled)
            hbox.pack_start(button, False, True, 0)

            button = Gtk.CheckButton(label="Left-align labels")
            button.set_active(options.app_options.process_label_align == 'left')
            button.connect('toggled', self.chart_widget.process_label_align_toggled)
            hbox.pack_start(button, False, True, 0)

        self.pack_start(hbox, False, False, 0)
        self.pack_start(content_paned, True, True, 0)
        if hasattr(window, 'register_shell'):
            window.register_shell(self)
        self.show_all()

    def grab_focus(self, window):
        window.set_focus(self.chart_widget)

    def on_theme_changed(self, combo):
        theme_mode = combo.get_active_id()
        if theme_mode is None:
            return
        self.window.apply_theme_mode(theme_mode)

    def on_process_search_changed(self, entry):
        self.chart_widget.options.app_options.process_search = entry.get_text()
        if hasattr(self.window, 'queue_redraw_all'):
            self.window.queue_redraw_all()
        else:
            self.chart_widget.queue_draw()

    def _show_details_pane(self):
        if self.details_wrapper is None:
            return
        self.details_pane.set_size_request(self.details_sidebar_width, -1)
        self.details_wrapper.set_size_request(self.details_sidebar_width, -1)
        self.details_wrapper.show_all()

    def _hide_details_pane(self):
        if self.details_wrapper is None:
            return
        current_width = self.details_wrapper.get_allocation().width
        if current_width > 1:
            self.details_sidebar_width = current_width
        self.details_wrapper.hide()

    def on_details_toggled(self, button):
        if button.get_property('active'):
            self._show_details_pane()
        else:
            self._hide_details_pane()

    def on_process_selected(self, proc):
        if self.details_toggle is not None and not self.details_toggle.get_active():
            self.details_toggle.set_active(True)
        self.window.app_options.selected_process_pid = proc.pid
        if self.details_pane is not None:
            self.details_pane.set_process(proc)
        if hasattr(self.window, 'queue_redraw_all'):
            self.window.queue_redraw_all()
        else:
            self.chart_widget.queue_draw()

    def set_theme_mode(self, theme_mode):
        if self.theme_combo is None:
            return
        self.theme_combo.handler_block(self.theme_combo_changed_signal_id)
        self.theme_combo.set_active_id(theme_mode)
        self.theme_combo.handler_unblock(self.theme_combo_changed_signal_id)

    def queue_chart_draw(self):
        self.chart_widget.queue_draw()

class PyBootchartWindow(Gtk.Window):

    def __init__(self, trace, app_options):
        super().__init__()

        self.app_options = app_options
        if not hasattr(self.app_options, 'selected_process_pid'):
            self.app_options.selected_process_pid = None
        self.shells = []
        self.gtk_settings = Gtk.Settings.get_default()
        if not hasattr(self.app_options, 'theme'):
            self.app_options.theme = themes.AUTO_THEME_NAME
        self.original_prefer_dark_theme = False
        if self.gtk_settings is not None:
            self.original_prefer_dark_theme = self.gtk_settings.get_property('gtk-application-prefer-dark-theme')
            self.gtk_settings.connect('notify::gtk-theme-name', self.on_gtk_theme_name_changed)

        window = self
        window.set_title("Bootchart %s" % trace.filename)
        window.set_default_size(750, 550)

        tab_page = Gtk.Notebook()
        tab_page.show()
        window.add(tab_page)

        full_opts = RenderOptions(app_options)
        full_tree = PyBootchartShell(window, trace, full_opts, 1.0)
        tab_page.append_page(full_tree, Gtk.Label(label="Full tree"))

        if getattr(trace, "kernel", None) is not None and len(trace.kernel) > 2:
            kernel_opts = RenderOptions(app_options)
            kernel_opts.cumulative = False
            kernel_opts.charts = False
            kernel_opts.kernel_only = True
            kernel_tree = PyBootchartShell(window, trace, kernel_opts, 5.0)
            tab_page.append_page(kernel_tree, Gtk.Label(label="Kernel boot"))

        self.apply_theme_mode(self.app_options.theme)
        full_tree.grab_focus(self)
        self.show_all()

    def register_shell(self, shell):
        self.shells.append(shell)

    def queue_redraw_all(self):
        for shell in self.shells:
            shell.queue_chart_draw()

    def sync_theme_controls(self):
        for shell in self.shells:
            shell.set_theme_mode(self.app_options.theme)

    def resolve_auto_theme(self):
        return themes.resolve_theme_name(
            themes.AUTO_THEME_NAME,
            themes.gtk_settings_prefers_dark(self.gtk_settings))

    def apply_theme_mode(self, theme_mode):
        if theme_mode not in themes.THEME_MODES:
            theme_mode = themes.AUTO_THEME_NAME

        self.app_options.theme = theme_mode
        if theme_mode == themes.AUTO_THEME_NAME:
            if self.gtk_settings is not None:
                self.gtk_settings.set_property(
                    'gtk-application-prefer-dark-theme',
                    self.original_prefer_dark_theme)
            self.app_options.resolved_theme = self.resolve_auto_theme()
        else:
            if self.gtk_settings is not None:
                self.gtk_settings.set_property(
                    'gtk-application-prefer-dark-theme',
                    theme_mode == 'dark')
            self.app_options.resolved_theme = theme_mode

        self.sync_theme_controls()
        self.queue_redraw_all()

    def on_gtk_theme_name_changed(self, settings, pspec):
        if self.app_options.theme != themes.AUTO_THEME_NAME:
            return

        resolved_theme = self.resolve_auto_theme()
        if getattr(self.app_options, 'resolved_theme', None) == resolved_theme:
            return

        self.app_options.resolved_theme = resolved_theme
        self.queue_redraw_all()

def show(trace, options):
    win = PyBootchartWindow(trace, options)
    win.connect('destroy', Gtk.main_quit)
    Gtk.main()
