"""Where pixels go: a cairo surface in memory, or the Touch Bar over DRM.

The panel is 60 wide by 2008 tall (portrait); everyone else thinks in a
2008x60 landscape scene. The rotation happens once, here. The dumb buffer
must be 64 px wide (pitch 256): at 60 the panel shows hatching.
"""
import ctypes as C
import math
import mmap
import os

import cairo

from .log import log

BUFFER_WIDTH = 64


class Output:
    width = 2008
    height = 60

    def __init__(self, width=2008, height=60):
        self.width, self.height = width, height
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        self._portrait = cairo.ImageSurface(cairo.FORMAT_ARGB32, BUFFER_WIDTH, width)

    def rotated(self, rect=None):
        """Paint the landscape scene (or one rect of it) into the portrait surface."""
        cr = cairo.Context(self._portrait)
        if rect:
            cr.rectangle(self.height - rect.bottom, rect.x, rect.h, rect.w)
            cr.clip()
        cr.translate(self.height, 0)
        cr.rotate(math.pi / 2)
        cr.set_source_surface(self.surface, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        self._portrait.flush()
        return self._portrait

    def flush(self, rect=None):
        raise NotImplementedError

    def save_png(self, path):
        self.surface.flush()
        self.surface.write_to_png(path)

    def blank(self):
        cr = cairo.Context(self.surface)
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        self.flush(None)

    def close(self):
        pass


class HeadlessOutput(Output):
    def __init__(self, width=2008, height=60):
        super().__init__(width, height)
        self.flushes = 0
        self.last_rect = None

    def flush(self, rect=None):
        self.rotated(rect)
        self.flushes += 1
        self.last_rect = rect


# --- libdrm through ctypes ---------------------------------------------------

class _ModeInfo(C.Structure):
    _fields_ = [("clock", C.c_uint32),
                ("hdisplay", C.c_uint16), ("hsync_start", C.c_uint16), ("hsync_end", C.c_uint16),
                ("htotal", C.c_uint16), ("hskew", C.c_uint16),
                ("vdisplay", C.c_uint16), ("vsync_start", C.c_uint16), ("vsync_end", C.c_uint16),
                ("vtotal", C.c_uint16), ("vscan", C.c_uint16),
                ("vrefresh", C.c_uint32), ("flags", C.c_uint32), ("type", C.c_uint32),
                ("name", C.c_char * 32)]


class _Res(C.Structure):
    _fields_ = [("count_fbs", C.c_int), ("fbs", C.POINTER(C.c_uint32)),
                ("count_crtcs", C.c_int), ("crtcs", C.POINTER(C.c_uint32)),
                ("count_connectors", C.c_int), ("connectors", C.POINTER(C.c_uint32)),
                ("count_encoders", C.c_int), ("encoders", C.POINTER(C.c_uint32)),
                ("min_width", C.c_uint32), ("max_width", C.c_uint32),
                ("min_height", C.c_uint32), ("max_height", C.c_uint32)]


class _Connector(C.Structure):
    _fields_ = [("connector_id", C.c_uint32), ("encoder_id", C.c_uint32),
                ("connector_type", C.c_uint32), ("connector_type_id", C.c_uint32),
                ("connection", C.c_int), ("mmWidth", C.c_uint32), ("mmHeight", C.c_uint32),
                ("subpixel", C.c_int),
                ("count_modes", C.c_int), ("modes", C.POINTER(_ModeInfo)),
                ("count_props", C.c_int), ("props", C.POINTER(C.c_uint32)),
                ("prop_values", C.POINTER(C.c_uint64)),
                ("count_encoders", C.c_int), ("encoders", C.POINTER(C.c_uint32))]


class _Encoder(C.Structure):
    _fields_ = [("encoder_id", C.c_uint32), ("encoder_type", C.c_uint32),
                ("crtc_id", C.c_uint32), ("possible_crtcs", C.c_uint32),
                ("possible_clones", C.c_uint32)]


class _Clip(C.Structure):
    _fields_ = [("x1", C.c_uint16), ("y1", C.c_uint16), ("x2", C.c_uint16), ("y2", C.c_uint16)]


def _libdrm():
    lib = C.CDLL("libdrm.so.2", use_errno=True)
    lib.drmModeGetResources.restype = C.POINTER(_Res)
    lib.drmModeGetConnector.restype = C.POINTER(_Connector)
    lib.drmModeGetEncoder.restype = C.POINTER(_Encoder)
    lib.drmModeSetCrtc.argtypes = [C.c_int, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32,
                                   C.POINTER(C.c_uint32), C.c_int, C.POINTER(_ModeInfo)]
    lib.drmModeAddFB.argtypes = [C.c_int, C.c_uint32, C.c_uint32, C.c_uint8, C.c_uint8,
                                 C.c_uint32, C.c_uint32, C.POINTER(C.c_uint32)]
    lib.drmModeCreateDumbBuffer.argtypes = [C.c_int, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32,
                                            C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.POINTER(C.c_uint64)]
    lib.drmModeMapDumbBuffer.argtypes = [C.c_int, C.c_uint32, C.POINTER(C.c_uint64)]
    lib.drmModeDirtyFB.argtypes = [C.c_int, C.c_uint32, C.POINTER(_Clip), C.c_uint32]
    lib.drmModeRmFB.argtypes = [C.c_int, C.c_uint32]
    lib.drmDropMaster.argtypes = [C.c_int]
    return lib


class DrmOutput(Output):
    def __init__(self, fd, lib, crtc, conn_id, mode, fb, mm, pitch):
        super().__init__(mode.vdisplay, mode.hdisplay)      # landscape = (2008, 60)
        self.fd, self.lib, self.crtc, self.conn_id, self.mode = fd, lib, crtc, conn_id, mode
        self.fb, self.mm, self.pitch = fb, mm, pitch
        # draw straight into the mapped buffer: no row copy on flush
        self._portrait = cairo.ImageSurface.create_for_data(
            mm, cairo.FORMAT_ARGB32, BUFFER_WIDTH, self.width, pitch)

    @classmethod
    def open(cls, path="/dev/dri/card3"):
        lib = _libdrm()
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        res = lib.drmModeGetResources(fd)
        if not res:
            raise OSError(f"{path}: no DRM resources")
        r = res.contents
        conn = None
        for i in range(r.count_connectors):
            c = lib.drmModeGetConnector(fd, r.connectors[i]).contents
            if c.connection == 1 and c.count_modes:
                conn = c
                break
        if conn is None:
            raise OSError(f"{path}: no connected connector")
        mode = conn.modes[0]
        if mode.vdisplay < 30 * mode.hdisplay:
            raise OSError(f"{path}: {mode.hdisplay}x{mode.vdisplay} does not look like a Touch Bar")
        enc = lib.drmModeGetEncoder(fd, conn.encoder_id)
        crtc = enc.contents.crtc_id if enc and enc.contents.crtc_id else r.crtcs[0]
        handle, pitch, size = C.c_uint32(), C.c_uint32(), C.c_uint64()
        if lib.drmModeCreateDumbBuffer(fd, BUFFER_WIDTH, mode.vdisplay, 32, 0,
                                       C.byref(handle), C.byref(pitch), C.byref(size)):
            raise OSError("CreateDumbBuffer failed")
        fb = C.c_uint32()
        if lib.drmModeAddFB(fd, BUFFER_WIDTH, mode.vdisplay, 24, 32, pitch.value, handle.value, C.byref(fb)):
            raise OSError("AddFB failed")
        off = C.c_uint64()
        if lib.drmModeMapDumbBuffer(fd, handle.value, C.byref(off)):
            raise OSError("MapDumbBuffer failed")
        mm = mmap.mmap(fd, size.value, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=off.value)
        out = cls(fd, lib, crtc, conn.connector_id, mode, fb.value, mm, pitch.value)
        conns = (C.c_uint32 * 1)(conn.connector_id)
        out.blank()
        if lib.drmModeSetCrtc(fd, crtc, fb.value, 0, 0, conns, 1, C.byref(mode)):
            raise OSError("SetCrtc failed (is tiny-dfr still running?)")
        log(f"DRM output {path}: mode {mode.hdisplay}x{mode.vdisplay}, pitch {pitch.value}")
        return out

    def flush(self, rect=None):
        self.rotated(rect)
        if rect:
            clip = _Clip(self.height - rect.bottom, rect.x, self.height - rect.y, rect.right)
        else:
            clip = _Clip(0, 0, self.height, self.width)
        self.lib.drmModeDirtyFB(self.fd, self.fb, C.byref(clip), 1)

    def close(self):
        try:
            self.blank()
            self.lib.drmModeRmFB(self.fd, self.fb)
            self.lib.drmDropMaster(self.fd)
        finally:
            os.close(self.fd)
