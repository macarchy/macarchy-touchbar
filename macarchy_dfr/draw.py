"""The macOS Touch Bar look, and the primitives every widget draws with.

Icons come from Material Symbols Rounded (a variable font: FILL and wght are
axes, so an active button goes from outline to filled without a second glyph).
App icons come from the Papirus theme. Text is Inter.
"""
import math
import os

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Pango, PangoCairo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODEPOINTS = os.path.join(ROOT, "fonts", "MaterialSymbolsRounded.codepoints")


class Theme:
    BG = (0, 0, 0)
    PILL = (0.2, 0.2, 0.2)
    PILL_PRESSED = (0.4, 0.4, 0.4)
    FG = (1, 1, 1)
    FG_DIM = (0.6, 0.6, 0.6)
    RAIL = (0.33, 0.33, 0.33)
    ACCENT_GREEN = (0.30, 0.85, 0.39)
    ACCENT_RED = (1.0, 0.27, 0.23)
    ACCENT_ORANGE = (1.0, 0.62, 0.04)
    ACCENT_PURPLE = (0.75, 0.35, 0.95)
    ACCENT_AMBER = (1.0, 0.8, 0.0)
    ACCENT_BLUE = (0.04, 0.52, 1.0)
    RADIUS = 6
    ICON = 24
    TEXT_PT = 22
    FONT = "Inter Medium"
    ICON_FONT = "Material Symbols Rounded"


_codepoints = None


def icon_codepoint(name):
    global _codepoints
    if _codepoints is None:
        _codepoints = {}
        try:
            with open(CODEPOINTS) as f:
                for line in f:
                    n, _, hexcode = line.strip().partition(" ")
                    if hexcode:
                        _codepoints[n] = chr(int(hexcode, 16))
        except OSError:
            pass
    return _codepoints[name]


_font_ok = None


def icon_font_available():
    global _font_ok
    if _font_ok is None:
        fams = {f.get_name() for f in PangoCairo.FontMap.get_default().list_families()}
        _font_ok = Theme.ICON_FONT in fams
    return _font_ok


def rounded_rect(cr, rect, radius):
    x, y, w, h, r = rect.x, rect.y, rect.w, rect.h, min(radius, rect.w / 2, rect.h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class Painter:
    def __init__(self, surface):
        self.surface = surface
        self._images = {}
        self._app_icons = {}

    def pill(self, cr, rect, color, radius=Theme.RADIUS):
        rounded_rect(cr, rect, radius)
        cr.set_source_rgb(*color)
        cr.fill()

    def _layout(self, cr, s, font, size, variations=None, markup=False):
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription(f"{font} {size}px")
        if variations:
            desc.set_variations(variations)
        layout.set_font_description(desc)
        (layout.set_markup if markup else layout.set_text)(s, -1)
        return layout

    def icon(self, cr, name, cx, cy, size=Theme.ICON, tint=Theme.FG, fill=0.0, weight=500):
        try:
            glyph = icon_codepoint(name)
        except KeyError:
            glyph = icon_codepoint("warning") if name != "warning" else "!"
        if not icon_font_available():
            layout = self._layout(cr, name, Theme.FONT, 12)
        else:
            layout = self._layout(cr, glyph, Theme.ICON_FONT, size,
                                   f"FILL={fill:.2f},wght={int(weight)},opsz={min(48, max(20, size))}")
        _ink, logical = layout.get_pixel_extents()
        cr.save()
        cr.set_source_rgb(*tint)
        cr.move_to(cx - logical.width / 2, cy - logical.height / 2)
        PangoCairo.show_layout(cr, layout)
        cr.restore()

    def measure_text(self, s, size=Theme.TEXT_PT):
        cr = cairo.Context(self.surface)
        return self._layout(cr, s, Theme.FONT, size).get_pixel_extents()[1].width

    def text(self, cr, s, rect, align="center", color=Theme.FG, size=Theme.TEXT_PT,
             ellipsize=True, markup=False):
        layout = self._layout(cr, s, Theme.FONT, size, markup=markup)
        if ellipsize:
            layout.set_width(rect.w * Pango.SCALE)
            layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_alignment({"left": Pango.Alignment.LEFT, "center": Pango.Alignment.CENTER,
                               "right": Pango.Alignment.RIGHT}[align])
        _ink, logical = layout.get_pixel_extents()
        cr.save()
        cr.rectangle(rect.x, rect.y, rect.w, rect.h)
        cr.clip()
        cr.set_source_rgb(*color)
        x = rect.x if ellipsize else {"left": rect.x, "center": rect.x + (rect.w - logical.width) / 2,
                                       "right": rect.right - logical.width}[align]
        cr.move_to(x, rect.y + (rect.h - logical.height) / 2)
        PangoCairo.show_layout(cr, layout)
        cr.restore()
        return min(logical.width, rect.w)

    def _pixbuf(self, path, w, h):
        key = (path, w, h)
        if key not in self._images:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, True)
            except Exception:
                pb = None
            self._images[key] = pb
        return self._images[key]

    def image(self, cr, path, rect, radius=Theme.RADIUS):
        pb = self._pixbuf(path, rect.w, rect.h)
        if pb is None:
            return False
        cr.save()
        rounded_rect(cr, rect, radius)
        cr.clip()
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk
        Gdk.cairo_set_source_pixbuf(cr, pb, rect.x + (rect.w - pb.get_width()) / 2,
                                     rect.y + (rect.h - pb.get_height()) / 2)
        cr.paint()
        cr.restore()
        return True

    def app_icon_path(self, cls, size=32):
        """Papirus (then hicolor) icon for a window class, or None."""
        key = (cls.lower(), size)
        if key in self._app_icons:
            return self._app_icons[key]
        found = None
        for theme in ("Papirus", "hicolor"):
            for sub in (f"{size}x{size}/apps", f"{size}x{size}@2x/apps", "scalable/apps"):
                for ext in ("svg", "png"):
                    p = f"/usr/share/icons/{theme}/{sub}/{cls.lower()}.{ext}"
                    if os.path.exists(p):
                        found = p
                        break
                if found:
                    break
            if found:
                break
        self._app_icons[key] = found
        return found
