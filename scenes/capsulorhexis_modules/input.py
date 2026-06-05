import ctypes
import os

KEY_LEFT = 18
KEY_UP = 19
KEY_RIGHT = 20
KEY_DOWN = 21
CTRL_KEY_ALIASES = {
    1: "a",
    3: "c",
    4: "d",
    5: "e",
    16: "p",
    17: "q",
    22: "v",
    23: "w",
    24: "x",
}
KEY_NAME_ALIASES = {
    "left": (chr(KEY_LEFT), KEY_LEFT),
    "leftarrow": (chr(KEY_LEFT), KEY_LEFT),
    "arrowleft": (chr(KEY_LEFT), KEY_LEFT),
    "key_left": (chr(KEY_LEFT), KEY_LEFT),
    "up": (chr(KEY_UP), KEY_UP),
    "uparrow": (chr(KEY_UP), KEY_UP),
    "arrowup": (chr(KEY_UP), KEY_UP),
    "key_up": (chr(KEY_UP), KEY_UP),
    "right": (chr(KEY_RIGHT), KEY_RIGHT),
    "rightarrow": (chr(KEY_RIGHT), KEY_RIGHT),
    "arrowright": (chr(KEY_RIGHT), KEY_RIGHT),
    "key_right": (chr(KEY_RIGHT), KEY_RIGHT),
    "down": (chr(KEY_DOWN), KEY_DOWN),
    "downarrow": (chr(KEY_DOWN), KEY_DOWN),
    "arrowdown": (chr(KEY_DOWN), KEY_DOWN),
    "key_down": (chr(KEY_DOWN), KEY_DOWN),
    "space": (" ", ord(" ")),
    "key_space": (" ", ord(" ")),
    "plus": ("+", ord("+")),
    "minus": ("-", ord("-")),
}
EVENT_KEY_FIELDS = ("key", "keyCode", "keycode", "code", "unicode", "text", "char")

WINDOWS_KEY_BINDINGS = {
    "w": 0x57,
    "a": 0x41,
    "s": 0x53,
    "d": 0x44,
    "m": 0x4D,
    "1": 0x31,
    "2": 0x32,
    "i": 0x49,
    "j": 0x4A,
    "k": 0x4B,
    "l": 0x4C,
    "x": 0x58,
    "e": 0x45,
    "q": 0x51,
    "c": 0x43,
    "v": 0x56,
    "p": 0x50,
    "r": 0x52,
    "t": 0x54,
    "space": 0x20,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "plus": 0xBB,
    "numpad_plus": 0x6B,
    "minus": 0xBD,
    "numpad_minus": 0x6D,
    "left_bracket": 0xDB,
    "right_bracket": 0xDD,
}


class WindowsKeyboardPoller:
    def __init__(self):
        self._get_async_key_state = ctypes.windll.user32.GetAsyncKeyState if os.name == "nt" else None

    @property
    def available(self):
        return self._get_async_key_state is not None

    def pressed(self, key_name):
        if not self._get_async_key_state:
            return False
        return bool(self._get_async_key_state(WINDOWS_KEY_BINDINGS[key_name]) & 0x8000)
