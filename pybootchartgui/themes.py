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

import copy
import json
import os

DEFAULT_THEME_NAME = 'light'
AUTO_THEME_NAME = 'auto'
BUILTIN_THEMES = ('light', 'dark')
THEME_MODES = (AUTO_THEME_NAME,) + BUILTIN_THEMES

FALLBACK_THEME = {
    'name': DEFAULT_THEME_NAME,
    'colors': {
        'annotation': (0.63, 0.0, 0.0, 0.5),
        'background': (1.0, 1.0, 1.0, 1.0),
        'border': (0.63, 0.63, 0.63, 1.0),
        'canvas': (1.0, 1.0, 1.0, 1.0),
        'cpu': (0.40, 0.55, 0.70, 1.0),
        'dependency': (0.50, 0.50, 0.50, 1.0),
        'disk_tput': (0.20, 0.71, 0.20, 1.0),
        'file_open': (0.20, 0.71, 0.71, 1.0),
        'io': (0.76, 0.48, 0.48, 0.5),
        'mem_buffers': (0.4, 0.4, 0.4, 0.3),
        'mem_cached': (0.40, 0.55, 0.70, 1.0),
        'mem_swap': (0.20, 0.71, 0.20, 1.0),
        'mem_used': (0.76, 0.48, 0.48, 0.5),
        'proc_border': (0.71, 0.71, 0.71, 1.0),
        'proc_dead': (0.71, 0.71, 0.71, 0.125),
        'proc_idle': (0.83, 0.89, 0.93, 1.0),
        'proc_paging': (0.71, 0.71, 0.71, 0.125),
        'proc_running': (0.40, 0.55, 0.70, 1.0),
        'proc_sleeping': (0.94, 0.94, 0.94, 1.0),
        'proc_stopped': (0.94, 0.50, 0.50, 1.0),
        'proc_text': (0.19, 0.19, 0.19, 1.0),
        'proc_waiting': (0.76, 0.48, 0.48, 0.5),
        'proc_zombie': (0.71, 0.71, 0.71, 1.0),
        'signature': (0.0, 0.0, 0.0, 0.3125),
        'text': (0.0, 0.0, 0.0, 1.0),
        'tick': (0.92, 0.92, 0.92, 1.0),
        'tick_bold': (0.86, 0.86, 0.86, 1.0),
    },
    'core_palette': {
        'alpha': 0.85,
        'io_alpha': 0.35,
        'saturation': 0.45,
        'value': 0.90,
    },
    'cumulative_palette': {
        'saturation': 0.5,
        'value': 1.0,
    },
}

REQUIRED_COLOR_KEYS = tuple(sorted(FALLBACK_THEME['colors'].keys()))
REQUIRED_CORE_KEYS = tuple(sorted(FALLBACK_THEME['core_palette'].keys()))
REQUIRED_CUMULATIVE_KEYS = tuple(sorted(FALLBACK_THEME['cumulative_palette'].keys()))
_THEME_CACHE = {}

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)


class ThemeError(ValueError):
    pass


def resolve_theme_name(theme_mode, prefer_dark):
    mode = (theme_mode or AUTO_THEME_NAME).lower()
    if mode == AUTO_THEME_NAME:
        return 'dark' if prefer_dark else DEFAULT_THEME_NAME
    if mode in BUILTIN_THEMES:
        return mode
    raise ThemeError("Unknown theme mode '%s'" % theme_mode)


def gtk_theme_name_is_dark(theme_name):
    if not isinstance(theme_name, string_types):
        return False
    return 'dark' in theme_name.lower()


def gtk_settings_prefers_dark(settings):
    if settings is None or not hasattr(settings, 'get_property'):
        return False
    return gtk_theme_name_is_dark(settings.get_property('gtk-theme-name'))


def builtin_theme_path(theme_name):
    return os.path.join(os.path.dirname(__file__), 'themes', '%s.json' % theme_name)


def load_theme(theme_name, writer=None):
    name = theme_name or DEFAULT_THEME_NAME
    if name in _THEME_CACHE:
        return copy.deepcopy(_THEME_CACHE[name])

    try:
        theme = _load_theme_file(name)
    except ThemeError as exc:
        _warn(writer, str(exc))
        if name == DEFAULT_THEME_NAME:
            theme = copy.deepcopy(FALLBACK_THEME)
        else:
            theme = copy.deepcopy(FALLBACK_THEME)
            theme['name'] = DEFAULT_THEME_NAME

    _THEME_CACHE[name] = theme
    return copy.deepcopy(theme)


def _load_theme_file(theme_name):
    if theme_name not in BUILTIN_THEMES:
        raise ThemeError("Unknown built-in theme '%s'" % theme_name)

    path = builtin_theme_path(theme_name)
    try:
        handle = open(path)
    except IOError as exc:
        raise ThemeError("Failed to load theme '%s' from %s: %s" % (theme_name, path, exc))

    try:
        data = json.load(handle)
    except ValueError as exc:
        raise ThemeError("Failed to parse theme '%s' from %s: %s" % (theme_name, path, exc))
    finally:
        handle.close()

    return validate_theme(data, path)


def validate_theme(theme, source):
    if not isinstance(theme, dict):
        raise ThemeError("Theme in %s must be a JSON object" % source)

    colors = theme.get('colors')
    core_palette = theme.get('core_palette')
    cumulative_palette = theme.get('cumulative_palette')

    if not isinstance(colors, dict):
        raise ThemeError("Theme in %s is missing a colors object" % source)
    if not isinstance(core_palette, dict):
        raise ThemeError("Theme in %s is missing a core_palette object" % source)
    if not isinstance(cumulative_palette, dict):
        raise ThemeError("Theme in %s is missing a cumulative_palette object" % source)

    normalized = {
        'name': _validate_name(theme.get('name'), source),
        'colors': {},
        'core_palette': {},
        'cumulative_palette': {},
    }

    for key in REQUIRED_COLOR_KEYS:
        if key not in colors:
            raise ThemeError("Theme in %s is missing colors.%s" % (source, key))
        normalized['colors'][key] = _validate_rgba('colors.%s' % key, colors[key], source)

    for key in REQUIRED_CORE_KEYS:
        if key not in core_palette:
            raise ThemeError("Theme in %s is missing core_palette.%s" % (source, key))
        normalized['core_palette'][key] = _validate_unit_float('core_palette.%s' % key, core_palette[key], source)

    for key in REQUIRED_CUMULATIVE_KEYS:
        if key not in cumulative_palette:
            raise ThemeError("Theme in %s is missing cumulative_palette.%s" % (source, key))
        normalized['cumulative_palette'][key] = _validate_unit_float('cumulative_palette.%s' % key, cumulative_palette[key], source)

    return normalized


def _validate_name(value, source):
    if value is None:
        return DEFAULT_THEME_NAME
    if not isinstance(value, string_types):
        raise ThemeError("Theme name in %s must be a string" % source)
    return value


def _validate_rgba(key, value, source):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ThemeError("%s in %s must be an array of 4 channel values" % (key, source))

    rgba = []
    for channel in value:
        if not isinstance(channel, (int, float)):
            raise ThemeError("%s in %s must contain numbers" % (key, source))
        if channel < 0.0 or channel > 1.0:
            raise ThemeError("%s in %s must contain values between 0.0 and 1.0" % (key, source))
        rgba.append(float(channel))
    return tuple(rgba)


def _validate_unit_float(key, value, source):
    if not isinstance(value, (int, float)):
        raise ThemeError("%s in %s must be numeric" % (key, source))
    if value < 0.0 or value > 1.0:
        raise ThemeError("%s in %s must be between 0.0 and 1.0" % (key, source))
    return float(value)


def _warn(writer, message):
    if writer is not None and hasattr(writer, 'warn'):
        writer.warn(message)
