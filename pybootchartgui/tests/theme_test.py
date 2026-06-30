import sys
import os
import unittest

sys.path.insert(0, os.getcwd())

import pybootchartgui.main as main
from pybootchartgui import themes


class FakeSettings:
    def __init__(self, theme_name):
        self.theme_name = theme_name

    def get_property(self, name):
        if name == 'gtk-theme-name':
            return self.theme_name
        raise KeyError(name)


class TestThemes(unittest.TestCase):

    def test_parser_accepts_theme_option(self):
        parser = main._mk_options_parser()
        options, args = parser.parse_args(['--theme', 'dark'])
        self.assertEqual('dark', options.theme)
        self.assertEqual([], args)

    def test_builtin_themes_load(self):
        light = themes.load_theme('light')
        dark = themes.load_theme('dark')
        self.assertEqual('light', light['name'])
        self.assertEqual('dark', dark['name'])
        self.assertNotEqual(light['colors']['canvas'], dark['colors']['canvas'])

    def test_auto_resolves_from_gtk_theme_name(self):
        self.assertEqual(
            'dark',
            themes.resolve_theme_name('auto', themes.gtk_settings_prefers_dark(FakeSettings('Adwaita-dark'))))
        self.assertEqual(
            'light',
            themes.resolve_theme_name('auto', themes.gtk_settings_prefers_dark(FakeSettings('Adwaita'))))

    def test_auto_falls_back_to_light_without_settings(self):
        self.assertEqual('light', themes.resolve_theme_name('auto', themes.gtk_settings_prefers_dark(None)))


if __name__ == '__main__':
    unittest.main()
