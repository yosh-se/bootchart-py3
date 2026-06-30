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

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GObject', '2.0')
from gi.repository import Gtk, Gdk, GObject
from . import draw
from .draw import RenderOptions

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

    def do_draw(self, cr):
        allocation = self.get_allocation()
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.paint()
        cr.save()
        cr.scale(self.zoom_ratio, self.zoom_ratio)
        cr.translate(-self.x, -self.y)
        draw.render(cr, self.options, self.xscale, self.trace)
        cr.restore()
        return False

    def position_changed(self):
        self.emit("position-changed", self.x, self.y)

    ZOOM_INCREMENT = 1.25

    def zoom_image(self, zoom_ratio):
        self.zoom_ratio = zoom_ratio
        self._set_scroll_adjustments(self.hadj, self.vadj)
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
            display = self.get_display()
            window = self.get_window()
            if window:
                cursor = Gdk.Cursor.new_from_name(display, "grab") or Gdk.Cursor.new(Gdk.CursorType.FLEUR)
                window.set_cursor(cursor)
            self.prevmousex = event.x
            self.prevmousey = event.y
        return False

    def on_area_button_release(self, area, event):
        if event.button == 2 or event.button == 1:
            window = self.get_window()
            if window:
                cursor = Gdk.Cursor.new_from_name(self.get_display(), "default") or Gdk.Cursor.new(Gdk.CursorType.ARROW)
                window.set_cursor(cursor)
            self.prevmousex = None
            self.prevmousey = None
            return True
        return False

    def on_area_scroll_event(self, area, event):
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            if event.direction == Gdk.ScrollDirection.UP:
                self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)
                return True
            if event.direction == Gdk.ScrollDirection.DOWN:
                self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)
                return True
        return False

    def on_area_motion_notify(self, area, event):
        state = event.state
        if (state & Gdk.ModifierType.BUTTON2_MASK) or (state & Gdk.ModifierType.BUTTON1_MASK):
            x, y = int(event.x), int(event.y)
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

        self.chart_widget = PyBootchartWidget(trace, options, xscale)

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

        # toolbar / h-box
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Create a Toolbar
        toolbar = uimanager.get_widget('/ToolBar')
        hbox.pack_start(toolbar, True, True, 0)

        if not options.kernel_only:
            # Misc. options
            button = Gtk.CheckButton(label="Show more")
            button.connect('toggled', self.chart_widget.show_toggled)
            hbox.pack_start(button, False, True, 0)

            button = Gtk.CheckButton(label="Left-align labels")
            button.set_active(options.app_options.process_label_align == 'left')
            button.connect('toggled', self.chart_widget.process_label_align_toggled)
            hbox.pack_start(button, False, True, 0)

        self.pack_start(hbox, False, False, 0)
        self.pack_start(scrolled, True, True, 0)
        self.show_all()

    def grab_focus(self, window):
        window.set_focus(self.chart_widget)

class PyBootchartWindow(Gtk.Window):

    def __init__(self, trace, app_options):
        super().__init__()

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

        full_tree.grab_focus(self)
        self.show_all()

def show(trace, options):
    win = PyBootchartWindow(trace, options)
    win.connect('destroy', Gtk.main_quit)
    Gtk.main()
