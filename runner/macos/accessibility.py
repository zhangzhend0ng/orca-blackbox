"""Small ApplicationServices binding for the two-field Mac project-copy case."""
import ctypes as ct
import os
import time
from contextlib import ExitStack


def framework(name):
    return ct.CDLL(f"/System/Library/Frameworks/{name}.framework/{name}")


def bind(lib, name, result, *arguments):
    function = getattr(lib, name)
    function.restype = result
    function.argtypes = arguments
    return function


cf = framework("CoreFoundation")
ax = framework("ApplicationServices")
ptr = ct.c_void_p
out = ct.POINTER(ptr)
integer = ct.c_int
boolean = ct.c_bool
utf8 = 0x08000100
release = bind(cf, "CFRelease", None, ptr)
make_string = bind(cf, "CFStringCreateWithCString", ptr, ptr, ct.c_char_p, ct.c_uint32)
string_size = bind(cf, "CFStringGetLength", ct.c_long, ptr)
read_string = bind(cf, "CFStringGetCString", boolean, ptr, ptr, ct.c_long, ct.c_uint32)
type_id = bind(cf, "CFGetTypeID", ct.c_ulong, ptr)
string_type = bind(cf, "CFStringGetTypeID", ct.c_ulong)()
boolean_type = bind(cf, "CFBooleanGetTypeID", ct.c_ulong)()
bool_value = bind(cf, "CFBooleanGetValue", boolean, ptr)
array_size = bind(cf, "CFArrayGetCount", ct.c_long, ptr)
array_item = bind(cf, "CFArrayGetValueAtIndex", ptr, ptr, ct.c_long)
dict_value = bind(cf, "CFDictionaryGetValue", ptr, ptr, ptr)
number_value = bind(cf, "CFNumberGetValue", boolean, ptr, integer, ptr)
true_value = ptr.in_dll(cf, "kCFBooleanTrue")
current_session = bind(framework("CoreGraphics"), "CGSessionCopyCurrentDictionary", ptr)
trusted = bind(ax, "AXIsProcessTrusted", boolean)
application = bind(ax, "AXUIElementCreateApplication", ptr, integer)
get_attr = bind(ax, "AXUIElementCopyAttributeValue", integer, ptr, ptr, out)
set_attr = bind(ax, "AXUIElementSetAttributeValue", integer, ptr, ptr, ptr)
perform = bind(ax, "AXUIElementPerformAction", integer, ptr, ptr)
get_pid = bind(ax, "AXUIElementGetPid", integer, ptr, ct.POINTER(integer))
set_timeout = bind(ax, "AXUIElementSetMessagingTimeout", integer, ptr, ct.c_float)
read_point = bind(ax, "AXValueGetValue", boolean, ptr, integer, ptr)


class Point(ct.Structure):
    _fields_ = [("x", ct.c_double), ("y", ct.c_double)]


class Rect(ct.Structure):
    _fields_ = [("origin", Point), ("size", Point)]


cg = framework("CoreGraphics")
window_info = bind(cg, "CGWindowListCopyWindowInfo", ptr, ct.c_uint32, ct.c_uint32)
decode_bounds = bind(cg, "CGRectMakeWithDictionaryRepresentation", boolean, ptr, ct.POINTER(Rect))
post_allowed = bind(cg, "CGPreflightPostEventAccess", boolean)
set_location = bind(cg, "CGEventSetLocation", None, ptr, Point)
post_to_pid = bind(cg, "CGEventPostToPid", None, integer, ptr)
appkit = framework("AppKit")  # Register NSEvent in the signed worker process.
objc = ct.CDLL("/usr/lib/libobjc.A.dylib")
objc_class = bind(objc, "objc_getClass", ptr, ct.c_char_p)
selector = bind(objc, "sel_registerName", ptr, ct.c_char_p)
send_address = ct.cast(objc.objc_msgSend, ptr).value
mouse_event = ct.CFUNCTYPE(ptr, ptr, ptr, ct.c_ulong, Point, ct.c_ulong, ct.c_double,
                           ct.c_long, ptr, ct.c_long, ct.c_long, ct.c_float)(send_address)
event_window = ct.CFUNCTYPE(ct.c_long, ptr, ptr)(send_address)
event_cg = ct.CFUNCTYPE(ptr, ptr, ptr)(send_address)


class Desktop(ExitStack):
    """Keep copied CF objects alive while using borrowed AX children."""

    def __init__(self, console_uid):
        super().__init__()
        self.console_uid = console_uid
        self.strings = {}

    def own(self, value):
        if value:
            self.callback(release, value)
        return value

    def string(self, text):
        if text not in self.strings:
            self.strings[text] = self.own(make_string(None, text.encode(), utf8))
        return self.strings[text]

    def check_session(self):
        session = current_session()
        if not session:
            raise RuntimeError("Missing Aqua session")
        try:
            def field(key):
                return dict_value(session, self.string(key))

            uid = integer()
            user = field("kCGSSessionUserIDKey")
            logged_in = field("kCGSessionLoginDoneKey")
            on_console = field("kCGSSessionOnConsoleKey")
            if (not user or not number_value(user, 3, ct.byref(uid)) or uid.value != os.getuid()
                    or not logged_in or not bool_value(logged_in) or not on_console or bool_value(on_console)
                    or self.console_uid in (0, uid.value) or os.stat("/dev/console").st_uid != self.console_uid):
                raise RuntimeError("Expected the test login in a separate, inactive Aqua session")
        finally:
            release(session)

    def attr(self, element, key):
        value = ptr()
        if element and get_attr(element, self.string(key), ct.byref(value)) == 0:
            return self.own(value.value)

    def text(self, element, key):
        return self.cf_text(self.attr(element, key))

    @staticmethod
    def cf_text(value):
        if not value or type_id(value) != string_type:
            return ""
        buffer = ct.create_string_buffer(4 * string_size(value) + 1)
        if not read_string(value, buffer, len(buffer), utf8):
            raise ValueError(f"Cannot read {key}")
        return buffer.value.decode()

    def enabled(self, element):
        value = self.attr(element, "AXEnabled")
        return bool(value and type_id(value) == boolean_type and bool_value(value))

    def children(self, element, key="AXChildren"):
        array = self.attr(element, key)
        return [array_item(array, i) for i in range(array_size(array))] if array else []

    def descendants(self, root):
        pending = [root]
        for _ in range(2000):
            if not pending:
                return
            child = pending.pop()
            yield child
            pending.extend(reversed(self.children(child)))
        raise RuntimeError("Unexpectedly large AX tree")

    def position(self, element):
        value = self.attr(element, "AXPosition")
        point = Point()
        if not value or not read_point(value, 1, ct.byref(point)):
            raise RuntimeError("Missing field position")
        return point

    def check_owned(self, pid, element):
        self.check_session()
        owner = integer()
        if not element or get_pid(element, ct.byref(owner)) or owner.value != pid:
            raise RuntimeError("AX control is outside the test process")

    def act(self, pid, element, action, value=None):
        self.check_owned(pid, element)
        name = self.string(action)
        error = perform(element, name) if value is None else set_attr(element, name, value)
        if error:
            raise RuntimeError(f"{action} failed with AX error {error}")

    def slice_window(self, pid, root, window, title):
        self.check_owned(pid, window)
        if self.text(window, "AXTitle") != title:
            raise RuntimeError("Project title changed before Slice plate")
        for candidate in self.children(root, "AXWindows"):
            if (self.text(candidate, "AXSubrole") in {"AXDialog", "AXSystemDialog"}
                    or self.text(candidate, "AXIdentifier") == "save-panel" or self.children(candidate, "AXSheets")):
                raise RuntimeError("A modal dialog is covering the project")
        position = self.position(window)
        size = Point()
        value = self.attr(window, "AXSize")
        if not value or not read_point(value, 2, ct.byref(size)) or (size.x, size.y) != (1200, 800):
            raise RuntimeError("Unrecognized Orca slice toolbar layout (expected 1200 x 800)")
        windows = self.own(window_info(0, 0))
        if not windows:
            raise RuntimeError("Cannot enumerate test session windows")

        def number(info, key):
            obj = dict_value(info, self.string(key))
            result = ct.c_int64()
            return result.value if obj and number_value(obj, 4, ct.byref(result)) else None

        matches = []
        for i in range(array_size(windows)):
            info = array_item(windows, i)
            if number(info, "kCGWindowOwnerPID") != pid or number(info, "kCGWindowLayer") != 0:
                continue
            if self.cf_text(dict_value(info, self.string("kCGWindowName"))) != title:
                continue
            bounds = Rect()
            obj = dict_value(info, self.string("kCGWindowBounds"))
            if (obj and decode_bounds(obj, ct.byref(bounds))
                    and (position.x, position.y, size.x, size.y)
                    == (bounds.origin.x, bounds.origin.y, bounds.size.x, bounds.size.y)):
                matches.append(number(info, "kCGWindowNumber"))
        if len(matches) != 1 or not matches[0]:
            raise RuntimeError("Cannot match a unique Orca window by title, PID and bounds")
        return matches[0], position

    def click_slice(self, pid, root, window, title):
        # The wx toolbar is custom drawn. These window-local coordinates were measured
        # on the 1200 x 800 Prepare screen with the two Quality controls visible.
        wid, origin = self.slice_window(pid, root, window, title)
        if not post_allowed():
            raise RuntimeError("Targeted input requires event posting permission")
        make_mouse = selector(b"mouseEventWithType:location:modifierFlags:timestamp:windowNumber:context:eventNumber:clickCount:pressure:")
        for kind in (1, 2):
            self.check_owned(pid, window)
            event = mouse_event(objc_class(b"NSEvent"), make_mouse, kind, Point(1000, 800 - 45), 0,
                                time.monotonic(), wid, None, 1, 1, 1.0 if kind == 1 else 0.0)
            if not event or event_window(event, selector(b"windowNumber")) != wid:
                raise RuntimeError("Slice event has no matching target window")
            native = event_cg(event, selector(b"CGEvent"))
            if not native:
                raise RuntimeError("Slice event is unavailable")
            set_location(native, Point(origin.x + 1000, origin.y + 45))
            post_to_pid(pid, native)
            time.sleep(0.16)
        return wid
