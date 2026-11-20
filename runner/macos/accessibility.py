"""Small ApplicationServices binding for the two-field Mac project-copy case."""
import ctypes as ct
import os
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
        value = self.attr(element, key)
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

    def act(self, pid, element, action, value=None):
        self.check_session()
        owner = integer()
        if not element or get_pid(element, ct.byref(owner)) or owner.value != pid:
            raise RuntimeError("AX control is outside the test process")
        name = self.string(action)
        error = perform(element, name) if value is None else set_attr(element, name, value)
        if error:
            raise RuntimeError(f"{action} failed with AX error {error}")
