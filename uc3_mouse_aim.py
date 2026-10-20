#!/usr/bin/env python3
"""
UC3 Mouse Aim - native-feeling mouse aiming for Uncharted 3: Drake's Deception on RPCS3.

Run it from the RPCS3 folder (or anywhere - it will ask for the RPCS3 folder once). It installs the
companion game patch, waits until the patched game is running, then feeds raw mouse movement into
the game memory every frame.
"""

import os
import sys
import json
import time
import ctypes
import struct
import threading
from ctypes import wintypes
from pathlib import Path

APP_NAME = "UC3 Mouse Aim"
APP_VERSION = "1.2.0"
PATCH_VERSION = "1.0.0"         # bump only when PATCH_WRITES change

# --------------------------------------------------------------------------------------------------
# Game patch (Uncharted 3, update 1.19 executable)
# --------------------------------------------------------------------------------------------------
PATCH_HASH = "PPU-02a88c3c6cd415b0bb81f1606bc743835881a4ba"
PATCH_NAME = "UC3 Mouse Aim"
PATCH_TITLE = "Uncharted 3: Drake's Deception"
PATCH_SERIALS = [
    ("BCES01175", "01.19"), ("BCES01176", "01.19"), ("BCES01670", "01.19"), ("BCES01692", "01.19"),
    ("BCUS98233", "01.19"), ("BCJS37004", "02.17"), ("NPEA00422", "01.19"), ("NPUA80858", "01.19"),
    ("BCUS99086", "01.19"), ("BCAS25014", "01.19"), ("BCAS25009", "01.19"),
]
PATCH_NOTES = ("Raw mouse aiming for the " + APP_NAME + " tool: removes stick deadzones, response curves, "
               "turn acceleration, axis snapping, aim assist and camera smoothing, and adds a per-frame "
               "mouse counter. Use together with the " + APP_NAME + " program.")

# (address, value, comment) - big-endian 32-bit writes
PATCH_WRITES = [
    (0x00892650, 0x4E800020, 'scale_analog_deadzone: blr'),
    (0x003D5F88, 0x4E800020, 'filter_stick_direction_reversal_and_deadzone: blr'),
    (0x00894934, 0x4850BB0C, 'right stick clamp bypass hook'),
    (0x00DA0440, 0x2C070004, 'CC2: cmpwi r7, 4'),
    (0x00DA0444, 0x4182000C, 'CC2: beq +0x0c'),
    (0x00DA0448, 0xEDAD637A, 'CC2: fmadds f13, f13, f13, f12'),
    (0x00DA044C, 0x4BAF44EC, 'CC2: b 0x00894938'),
    (0x00DA0450, 0xEBC1FFF0, 'CC2: ld r30, -0x10(r1)'),
    (0x00DA0454, 0x4E800020, 'CC2: blr'),
    (0x00817D68, 0x80050000, 'Lerp8f (camera blend -> instant): lwz r0, 0(r5)'),
    (0x00817D6C, 0x90030000, 'Lerp8f (camera blend -> instant): stw r0, 0(r3)'),
    (0x00817D70, 0x80050004, 'Lerp8f (camera blend -> instant): lwz r0, 4(r5)'),
    (0x00817D74, 0x90030004, 'Lerp8f (camera blend -> instant): stw r0, 4(r3)'),
    (0x00817D78, 0x80050008, 'Lerp8f (camera blend -> instant): lwz r0, 8(r5)'),
    (0x00817D7C, 0x90030008, 'Lerp8f (camera blend -> instant): stw r0, 8(r3)'),
    (0x00817D80, 0x8005000C, 'Lerp8f (camera blend -> instant): lwz r0, 12(r5)'),
    (0x00817D84, 0x9003000C, 'Lerp8f (camera blend -> instant): stw r0, 12(r3)'),
    (0x00817D88, 0x80050010, 'Lerp8f (camera blend -> instant): lwz r0, 16(r5)'),
    (0x00817D8C, 0x90030010, 'Lerp8f (camera blend -> instant): stw r0, 16(r3)'),
    (0x00817D90, 0x80050014, 'Lerp8f (camera blend -> instant): lwz r0, 20(r5)'),
    (0x00817D94, 0x90030014, 'Lerp8f (camera blend -> instant): stw r0, 20(r3)'),
    (0x00817D98, 0x80050018, 'Lerp8f (camera blend -> instant): lwz r0, 24(r5)'),
    (0x00817D9C, 0x90030018, 'Lerp8f (camera blend -> instant): stw r0, 24(r3)'),
    (0x00817DA0, 0x8005001C, 'Lerp8f (camera blend -> instant): lwz r0, 28(r5)'),
    (0x00817DA4, 0x9003001C, 'Lerp8f (camera blend -> instant): stw r0, 28(r3)'),
    (0x00817DA8, 0x4E800020, 'Lerp8f (camera blend -> instant): blr'),
    (0x003D63C8, 0x480000B0, 'aim inputs: skip 3-zone turn acceleration curve (b 0x3d6478)'),
    (0x003D6480, 0x48000064, 'aim inputs: skip axis snap (b 0x3d64e4)'),
    (0x003D650C, 0x60000000, 'aim inputs: nop bl math_powf (yaw) -> f1 stays |yaw|'),
    (0x003D6538, 0x60000000, 'aim inputs: nop bl math_powf (pitch) -> f1 stays |pitch|'),
    (0x003D773C, 0x480000DC, 'update_camera_state: skip aim friction slowdown (f31 = 1.0)'),
    (0x003D78D8, 0x60000000, 'update_camera_state: drop pitch-dependent yaw factor (linear)'),
    (0x003D7904, 0x480001EC, 'update_camera_state: skip aim-assist spring (b 0x3d7af0)'),
    (0x003D7BD8, 0xFFE0F090, 'update_camera_state: fmr f31,f30 (drop cubic pitch-dependent yaw factor)'),
    (0x001CF040, 0xC01F6864, 'free look yaw: use min speed (this+0x6864) instead of ramped speed (this+0x6b2c)'),
    (0x00894210, 0x4850C250, 'poll_gamepads hook -> mouse counter cave 0xDA0460'),
    (0x00DA0460, 0x3D600145, 'counter cave: lis r11,0x0145'),
    (0x00DA0464, 0x396BFF00, 'counter cave: addi r11,r11,-0x100'),
    (0x00DA0468, 0x818B0018, 'counter cave: lwz r12,0x18(r11)'),
    (0x00DA046C, 0x398C0001, 'counter cave: addi r12,r12,1'),
    (0x00DA0470, 0x918B0018, 'counter cave: stw r12,0x18(r11)'),
    (0x00DA0474, 0xC06B001C, 'counter cave: lfs f3,0x1c(r11)'),
    (0x00DA0478, 0x3D800138, 'counter cave: lis r12,0x0138'),
    (0x00DA047C, 0x818CF724, 'counter cave: lwz r12,-0x8dc(r12)'),
    (0x00DA0480, 0x2C0C0000, 'counter cave: cmpwi r12,0'),
    (0x00DA0484, 0x41820024, 'counter cave: beq L_dt'),
    (0x00DA0488, 0x818C0064, 'counter cave: lwz r12,0x64(r12)'),
    (0x00DA048C, 0x2C0C0000, 'counter cave: cmpwi r12,0'),
    (0x00DA0490, 0x41820018, 'counter cave: beq L_dt'),
    (0x00DA0494, 0xC08C0014, 'counter cave: lfs f4,0x14(r12)'),
    (0x00DA0498, 0xC0AB0030, 'counter cave: lfs f5,0x30(r11)'),
    (0x00DA049C, 0xFF842800, 'counter cave: fcmpu cr7,f4,f5'),
    (0x00DA04A0, 0x419C0008, 'counter cave: blt cr7 L_dt'),
    (0x00DA04A4, 0xFC602090, 'counter cave: fmr f3,f4'),
    (0x00DA04A8, 0x812B0000, 'counter cave: lwz r9,0(r11)'),
    (0x00DA04AC, 0x814B0008, 'counter cave: lwz r10,8(r11)'),
    (0x00DA04B0, 0x912B0008, 'counter cave: stw r9,8(r11)'),
    (0x00DA04B4, 0x7D2A4850, 'counter cave: subf r9,r10,r9'),
    (0x00DA04B8, 0x7D2907B4, 'counter cave: extsw r9,r9'),
    (0x00DA04BC, 0xF92B0020, 'counter cave: std r9,0x20(r11)'),
    (0x00DA04C0, 0xC80B0020, 'counter cave: lfd f0,0x20(r11)'),
    (0x00DA04C4, 0xFC00069C, 'counter cave: fcfid f0'),
    (0x00DA04C8, 0xFC000018, 'counter cave: frsp f0'),
    (0x00DA04CC, 0xC04B0010, 'counter cave: lfs f2,16(r11)'),
    (0x00DA04D0, 0xEC0000B2, 'counter cave: fmuls f0,f0,f2'),
    (0x00DA04D4, 0xEC001824, 'counter cave: fdivs f0,f0,f3'),
    (0x00DA04D8, 0x812B0004, 'counter cave: lwz r9,4(r11)'),
    (0x00DA04DC, 0x814B000C, 'counter cave: lwz r10,12(r11)'),
    (0x00DA04E0, 0x912B000C, 'counter cave: stw r9,12(r11)'),
    (0x00DA04E4, 0x7D2A4850, 'counter cave: subf r9,r10,r9'),
    (0x00DA04E8, 0x7D2907B4, 'counter cave: extsw r9,r9'),
    (0x00DA04EC, 0xF92B0020, 'counter cave: std r9,0x20(r11)'),
    (0x00DA04F0, 0xC82B0020, 'counter cave: lfd f1,0x20(r11)'),
    (0x00DA04F4, 0xFC200E9C, 'counter cave: fcfid f1'),
    (0x00DA04F8, 0xFC200818, 'counter cave: frsp f1'),
    (0x00DA04FC, 0xC04B0014, 'counter cave: lfs f2,20(r11)'),
    (0x00DA0500, 0xEC2100B2, 'counter cave: fmuls f1,f1,f2'),
    (0x00DA0504, 0xEC211824, 'counter cave: fdivs f1,f1,f3'),
    (0x00DA0508, 0xD0130018, 'counter cave: stfs f0,0x18(r19)'),
    (0x00DA050C, 0xD033001C, 'counter cave: stfs f1,0x1c(r19)'),
    (0x00DA0510, 0xD0130008, 'counter cave: stfs f0,8(r19)'),
    (0x00DA0514, 0xD033000C, 'counter cave: stfs f1,0xc(r19)'),
    (0x00DA0518, 0x813E807C, 'counter cave: lwz r9,-0x7f84(r30)'),
    (0x00DA051C, 0x4BAF3CF8, 'counter cave: b 0x894214'),
    (0x0144FF10, 0x3A03126F, 'buffer init: scale_x'),
    (0x0144FF14, 0x3A03126F, 'buffer init: scale_y'),
    (0x0144FF1C, 0x3D088889, 'buffer init: fallback dt 1/30'),
    (0x0144FF30, 0x3B03126F, 'buffer init: min dt'),
    (0x001D34EC, 0x60000000, 'free look: camera spring omega always 550/s (snap), velocity reset -> no lag'),
    (0x001CEF84, 0x4800002C, 'free look: always manual yaw path (no axis dominance when |Y| >> |X|)'),
]

# Signature used to tell whether the patch is active in the running game
HOOK_ADDR = 0x00894210
HOOK_PATCHED = 0x4850C250      # b 0xDA0460 (counter cave)
HOOK_ORIGINAL = 0x813E807C     # lwz r9,-0x7f84(r30)

# Counter buffer written by this program, consumed by the game once per frame
BUF = 0x0144FF00               # +0 total_x i32, +4 total_y i32, +0x10/+0x14 scale f32, +0x18 frame counter

# Measured camera response of the patched game (degrees per stick-unit-second / counts)
FREE_YAW_DEG = 80.0            # free-look yaw speed
# One count must turn the same angle on both axes and in both modes; game-side differences:
AXIS_EQUALISE = {False: (1.00, 0.90), True: (1.13, 1.70)}   # key: aiming (ADS)
REFERENCE_DPI = 800

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32.OpenProcess.restype = wintypes.HANDLE


# --------------------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------------------
def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


SETTINGS_FILE = app_dir() / "uc3_mouse_aim_settings.json"
DEFAULTS = {
    "rpcs3_dir": "",
    "sensitivity": 1.0,
    "dpi": 800,
    "free_look_multiplier": 1.0,
    "ads_multiplier": 1.0,
    "invert_y": False,
    "hide_cursor": True,
}


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(s: dict):
    try:
        SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  ! Could not save settings: {e}")


def degrees_per_count(s: dict, ads: bool = False) -> float:
    mult = s["ads_multiplier"] if ads else s["free_look_multiplier"]
    return 0.0005 * FREE_YAW_DEG * s["sensitivity"] * (REFERENCE_DPI / max(1, s["dpi"])) * mult


def cm_per_360(s: dict, ads: bool = False) -> float:
    return 360.0 / degrees_per_count(s, ads) / max(1, s["dpi"]) * 2.54


# --------------------------------------------------------------------------------------------------
# RPCS3 discovery and patch installation
# --------------------------------------------------------------------------------------------------
def find_process(name: str = "rpcs3.exe"):
    """Return (pid, exe_path) of a running process, or (None, None)."""
    TH32CS_SNAPPROCESS = 0x2

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    pid = None
    try:
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == name:
                pid = entry.th32ProcessID
                break
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    if pid is None:
        return None, None
    path = None
    h = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            path = buf.value
        kernel32.CloseHandle(h)
    return pid, path


def is_rpcs3_dir(p: Path) -> bool:
    return (p / "rpcs3.exe").is_file()


def locate_rpcs3(settings: dict) -> Path:
    candidates = [app_dir(), Path.cwd()]
    if settings.get("rpcs3_dir"):
        candidates.insert(0, Path(settings["rpcs3_dir"]))
    _, exe = find_process()
    if exe:
        candidates.insert(0, Path(exe).parent)
    for c in candidates:
        if is_rpcs3_dir(c):
            return c
    print("\n  RPCS3 was not found next to this program.")
    while True:
        raw = input("  Enter the RPCS3 folder (the one that contains rpcs3.exe): ").strip().strip('"')
        p = Path(raw)
        if is_rpcs3_dir(p):
            settings["rpcs3_dir"] = str(p)
            save_settings(settings)
            return p
        print("  rpcs3.exe is not in that folder, try again.")


def patch_yaml_block() -> str:
    lines = [f"  {PATCH_NAME}:", "    Games:", f'      "{PATCH_TITLE}":']
    lines += [f"        {serial}: [ {ver} ]" for serial, ver in PATCH_SERIALS]
    lines += [f"    Author: olaftnt", f'    Notes: "{PATCH_NOTES}"', f"    Patch Version: {PATCH_VERSION}", "    Patch:"]
    lines += [f"      - [ be32, 0x{a:08x}, 0x{v:08x} ] # {c}" for a, v, c in PATCH_WRITES]
    return "\n".join(lines) + "\n"


def _upsert_entry(text: str, block: str) -> str:
    """Put `block` (a 2-space indented entry) under the game hash key, replacing any previous copy."""
    lines = text.splitlines()
    marker = f"  {PATCH_NAME}:"
    if marker in lines:
        i = lines.index(marker)
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].startswith("   ")):
            j += 1
        del lines[i:j]
    new = block.rstrip("\n").split("\n")
    key = f"{PATCH_HASH}:"
    if key in lines:
        k = lines.index(key) + 1
        lines[k:k] = new
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [key] + new
    return "\n".join(lines) + "\n"


def install_patch(rpcs3: Path) -> bool:
    """Make sure the current patch is in patches/imported_patch.yml (RPCS3's patch updater never
    overwrites that file). Returns True if the file was changed."""
    target = rpcs3 / "patches" / "imported_patch.yml"
    target.parent.mkdir(exist_ok=True)
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    block = patch_yaml_block()
    if block in text:
        return False
    if not text.strip():
        text = "Version: 1.2\n"
    new_text = _upsert_entry(text, block)
    if target.exists():
        backup = target.with_suffix(".yml.bak")
        if not backup.exists():
            backup.write_text(text, encoding="utf-8", newline="\n")
    target.write_text(new_text, encoding="utf-8", newline="\n")
    return True


def enable_patch(rpcs3: Path) -> bool:
    """Tick the patch in RPCS3's patch manager (config/patch_config.yml). Returns True if changed."""
    cfg = rpcs3 / "config" / "patch_config.yml"
    cfg.parent.mkdir(exist_ok=True)
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    block = [f"  {PATCH_NAME}:", f'    "{PATCH_TITLE}":']
    for serial, ver in PATCH_SERIALS:
        block += [f"      {serial}:", f"        {ver}:", "          Enabled: true"]
    block = "\n".join(block) + "\n"
    if block in text:
        return False
    cfg.write_text(_upsert_entry(text, block), encoding="utf-8", newline="\n")
    return True


def ensure_patch(rpcs3: Path) -> str:
    """Install and enable the patch. Returns "changed", "ok" or "error: <reason>"."""
    try:
        changed = install_patch(rpcs3) | enable_patch(rpcs3)    # both always run
        return "changed" if changed else "ok"
    except Exception as e:
        return f"error: {e}"


# --------------------------------------------------------------------------------------------------
# Game memory
# --------------------------------------------------------------------------------------------------
class GameMemory:
    BASE_CANDIDATES = (0x300000000, 0x100000000, 0x200000000, 0x800000000, 0x1000000000)

    def __init__(self, pid: int):
        self.pid = pid
        self.h = kernel32.OpenProcess(0x0438, False, pid)   # VM_READ | VM_WRITE | VM_OPERATION | QUERY_INFO
        self.base = None
        if self.h:
            for b in self.BASE_CANDIDATES:
                hook = self._read(b + HOOK_ADDR, 4)
                if self._read(b + 0x10000, 4) == b"\x7fELF" or \
                        (hook and struct.unpack(">I", hook)[0] in (HOOK_PATCHED, HOOK_ORIGINAL)):
                    self.base = b
                    break

    def _read(self, addr: int, n: int):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if kernel32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) and got.value == n:
            return buf.raw
        return None

    def read(self, ps3_addr: int, n: int):
        return self._read(self.base + ps3_addr, n) if self.base is not None else None

    def write(self, ps3_addr: int, data: bytes) -> bool:
        got = ctypes.c_size_t()
        return bool(kernel32.WriteProcessMemory(self.h, ctypes.c_void_p(self.base + ps3_addr), data, len(data),
                                                ctypes.byref(got)))

    def u32(self, ps3_addr: int):
        d = self.read(ps3_addr, 4)
        return struct.unpack(">I", d)[0] if d else None

    def patch_state(self) -> str:
        v = self.u32(HOOK_ADDR)
        if v is None:
            return "no-game"
        if v == HOOK_PATCHED and self.u32(0x001D34EC) == 0x60000000:
            return "active"
        if v == HOOK_ORIGINAL:
            return "not-loaded"
        return "other"

    def totals(self):
        d = self.read(BUF, 8)
        return struct.unpack(">ii", d) if d else (0, 0)

    def frames(self):
        return self.u32(BUF + 0x18) or 0

    def write_totals(self, tx: int, ty: int):
        wrap = lambda v: ((int(v) + 0x80000000) & 0xFFFFFFFF) - 0x80000000
        self.write(BUF, struct.pack(">ii", wrap(tx), wrap(ty)))

    def alive(self) -> bool:
        code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(self.h, ctypes.byref(code))) and code.value == 259

    def close(self):
        if self.h:
            kernel32.CloseHandle(self.h)
            self.h = None


# --------------------------------------------------------------------------------------------------
# Raw mouse input
# --------------------------------------------------------------------------------------------------
WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100
RI_RIGHT_DOWN, RI_RIGHT_UP = 0x0004, 0x0008


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wintypes.USHORT), ("usButtonFlags", wintypes.USHORT),
                ("usButtonData", wintypes.USHORT), ("ulRawButtons", wintypes.ULONG),
                ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID, ctypes.POINTER(wintypes.UINT),
                                   wintypes.UINT]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.CreateCursor.argtypes = [wintypes.HINSTANCE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(ctypes.c_ubyte)]
user32.CreateCursor.restype = wintypes.HANDLE
user32.CopyImage.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.CopyImage.restype = wintypes.HANDLE
user32.SetSystemCursor.argtypes = [wintypes.HANDLE, wintypes.DWORD]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class CursorHider:
    """Swaps the system cursors for a blank one while the game has focus; always restored on exit."""
    OCR_IDS = (32512, 32513, 32514, 32515, 32516, 32642, 32643, 32644, 32645, 32646, 32648, 32649, 32650)

    def __init__(self):
        import atexit
        self.hidden = False
        and_mask = (ctypes.c_ubyte * 128)(*([0xFF] * 128))
        xor_mask = (ctypes.c_ubyte * 128)()
        self.blank = user32.CreateCursor(kernel32.GetModuleHandleW(None), 0, 0, 32, 32, and_mask, xor_mask)
        atexit.register(self.show)
        handler = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
        self._ctrl = handler(lambda ev: (self.show(), False)[1])
        kernel32.SetConsoleCtrlHandler(self._ctrl, True)

    def hide(self):
        if not self.hidden and self.blank:
            for ocr in self.OCR_IDS:
                user32.SetSystemCursor(user32.CopyImage(self.blank, 2, 0, 0, 0), ocr)
            self.hidden = True

    def show(self):
        if self.hidden:
            user32.SystemParametersInfoW(0x0057, 0, None, 0)   # SPI_SETCURSORS
            self.hidden = False


def game_window():
    """The RPCS3 game render window (title starts with 'FPS:'), not the RPCS3 main window."""
    found = []

    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            if buf.value.startswith("FPS:") and ("BCES" in buf.value or "BCUS" in buf.value
                                                 or "Uncharted" in buf.value or "NP" in buf.value):
                found.append(h)
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found[0] if found else None


class MouseFeeder:
    """Receives raw mouse input on a hidden window and writes the accumulated counts into the game.
    Created once per program run (one window class, one input thread)."""
    _instance = None

    @classmethod
    def get(cls, settings: dict) -> "MouseFeeder":
        if cls._instance is None:
            cls._instance = cls(settings)
        cls._instance.s = settings
        return cls._instance

    def __init__(self, settings: dict):
        self.s = settings
        self.lock = threading.Lock()
        self.mem = None
        self.acc_x = self.acc_y = 0.0
        self.focused = False
        self.ads = False
        self.cursor = CursorHider()
        self._proc = WNDPROC(self._wndproc)
        threading.Thread(target=self._loop, daemon=True).start()

    def attach(self, mem: GameMemory):
        with self.lock:
            self.mem = mem
            self.acc_x, self.acc_y = map(float, mem.totals())

    def detach(self):
        with self.lock:
            self.mem = None

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            size = wintypes.UINT(ctypes.sizeof(RAWINPUT))
            ri = RAWINPUT()
            if user32.GetRawInputData(ctypes.c_void_p(lparam), RID_INPUT, ctypes.byref(ri), ctypes.byref(size),
                                      ctypes.sizeof(RAWINPUTHEADER)) > 0 and ri.header.dwType == 0 \
                    and not (ri.mouse.usFlags & 0x01):
                bf = ri.mouse.usButtonFlags
                if bf & RI_RIGHT_DOWN:
                    self.ads = True
                elif bf & RI_RIGHT_UP:
                    self.ads = False
                dx, dy = ri.mouse.lLastX, ri.mouse.lLastY
                if (dx or dy) and self.focused:
                    s = self.s
                    ex, ey = AXIS_EQUALISE[self.ads]
                    k = s["sensitivity"] * (REFERENCE_DPI / max(1, s["dpi"])) * \
                        (s["ads_multiplier"] if self.ads else s["free_look_multiplier"])
                    with self.lock:
                        if self.mem is not None:
                            self.acc_x += dx * k * ex
                            self.acc_y += (-dy if s["invert_y"] else dy) * k * ey
                            self.mem.write_totals(round(self.acc_x), round(self.acc_y))
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _loop(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName="UC3MouseAimRawInput")
        user32.RegisterClassW(ctypes.byref(wc))
        hwnd = user32.CreateWindowExW(0, "UC3MouseAimRawInput", "UC3MouseAimRawInput", 0, 0, 0, 0, 0,
                                      None, None, hinst, None)
        rid = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd)
        user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def update_focus(self, active: bool):
        """Only while the patched game's window is in the foreground: keep the cursor in a small box at
        its centre (so clicks never land outside the game) and hide it."""
        hwnd = game_window() if active else None
        was = self.focused
        self.focused = bool(hwnd) and user32.GetForegroundWindow() == hwnd
        if self.focused:
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
            user32.ClipCursor(ctypes.byref(wintypes.RECT(cx - 40, cy - 40, cx + 40, cy + 40)))
            if self.s["hide_cursor"]:
                self.cursor.hide()
        elif was:
            self.release()

    def release(self):
        self.focused = False
        user32.ClipCursor(None)
        self.cursor.show()


# --------------------------------------------------------------------------------------------------
# Console UI
# --------------------------------------------------------------------------------------------------
class C:
    """ANSI colours; left empty when the console has no VT support (output stays plain)."""
    RESET = BOLD = DIM = GREEN = YELLOW = RED = CYAN = ""


def init_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    h = kernel32.GetStdHandle(-11)
    mode = wintypes.DWORD()
    if kernel32.GetConsoleMode(h, ctypes.byref(mode)) and kernel32.SetConsoleMode(h, mode.value | 0x0004):
        C.RESET, C.BOLD, C.DIM = "\033[0m", "\033[1m", "\033[2m"
        C.GREEN, C.YELLOW, C.RED, C.CYAN = "\033[92m", "\033[93m", "\033[91m", "\033[96m"
    os.system(f"title {APP_NAME} {APP_VERSION}")


def clear():
    os.system("cls")


def header():
    print()
    print(f"  {C.BOLD}{C.CYAN}UC3 MOUSE AIM{C.RESET}  {C.DIM}v{APP_VERSION}{C.RESET}")
    print(f"  {C.DIM}Raw mouse aiming for Uncharted 3 on RPCS3{C.RESET}")
    print(f"  {C.DIM}{'─' * 60}{C.RESET}")


def pause(text="Press Enter to go back"):
    input(f"\n  {C.DIM}{text}{C.RESET}")


def game_status() -> str:
    """no-rpcs3 | no-access | no-game | not-loaded | other | active"""
    pid, _ = find_process()
    if not pid:
        return "no-rpcs3"
    mem = GameMemory(pid)
    try:
        if not mem.h:
            return "no-access"
        return "no-game" if mem.base is None else mem.patch_state()
    finally:
        mem.close()


def print_status(rpcs3: Path, patch: str, s: dict):
    if patch.startswith("error"):
        patch_text = f"{C.RED}! Could not write the patch files ({patch[7:]}){C.RESET}"
    else:
        patch_text = f"{C.GREEN}✓ Installed and enabled{C.RESET}"
    state = game_status()
    colour, mark, text = {
        "no-rpcs3": (C.DIM, "○", "RPCS3 is not running"),
        "no-game": (C.DIM, "○", "RPCS3 is open, game not started"),
        "active": (C.GREEN, "●", "Running with the patch"),
        "not-loaded": (C.YELLOW, "●", "Running without the patch - restart RPCS3 and load the game"),
        "other": (C.RED, "●", "Another mouse patch is active - disable it and restart"),
        "no-access": (C.RED, "!", "Cannot read RPCS3 - run this program as administrator"),
    }[state]
    print()
    print(f"  {C.DIM}RPCS3{C.RESET}     {rpcs3}")
    print(f"  {C.DIM}Patch{C.RESET}     {patch_text}")
    print(f"  {C.DIM}Game{C.RESET}      {colour}{mark} {text}{C.RESET}")
    print(f"  {C.DIM}Mouse{C.RESET}     sensitivity {s['sensitivity']:g} · {s['dpi']} DPI · {cm_per_360(s):.1f} cm/360")


HELP = """
  {b}HELP{r}

  • Keep this window open while you play, with "Start mouse aim" running.

  • The "{patch}" patch must be enabled in RPCS3 (Manage > Game Patches).
    This program installs and enables it for you.

  • RPCS3 applies patches when the game starts. If the status says the game
    runs without the patch, close RPCS3, start it again and load the game.

  • Map L1 (aim) to the right mouse button in RPCS3's pad settings. The program
    uses that button to switch to the aiming sensitivity.

  • Mouse aim works while the game window is focused. The cursor is hidden
    there. Press Ctrl+C in this window to stop.
"""


def show_help():
    clear(); header()
    print(HELP.format(b=C.BOLD, r=C.RESET, patch=PATCH_NAME))
    pause()


def ask_float(prompt: str, current: float, lo: float, hi: float) -> float:
    raw = input(f"\n  {prompt} ({lo:g} - {hi:g}) [{current:g}]: ").strip().replace(",", ".")
    if not raw:
        return current
    try:
        v = float(raw)
        if lo <= v <= hi:
            return v
    except ValueError:
        pass
    print(f"  {C.RED}Enter a number between {lo:g} and {hi:g}.{C.RESET}")
    time.sleep(1.2)
    return current


def settings_menu(s: dict):
    onoff = lambda v: f"{C.GREEN}on{C.RESET}" if v else f"{C.DIM}off{C.RESET}"
    while True:
        clear(); header()
        print(f"""
  {C.BOLD}SETTINGS{C.RESET}

  {C.CYAN}1{C.RESET}  Sensitivity            {s['sensitivity']:g}
  {C.CYAN}2{C.RESET}  Mouse DPI              {s['dpi']}
  {C.CYAN}3{C.RESET}  Free-look multiplier   {s['free_look_multiplier']:g}
  {C.CYAN}4{C.RESET}  Aiming multiplier      {s['ads_multiplier']:g}
  {C.CYAN}5{C.RESET}  Invert Y               {onoff(s['invert_y'])}
  {C.CYAN}6{C.RESET}  Hide cursor in game    {onoff(s['hide_cursor'])}
  {C.CYAN}0{C.RESET}  Back

  Free look {C.BOLD}{cm_per_360(s):.1f} cm/360{C.RESET}  ·  Aiming {C.BOLD}{cm_per_360(s, True):.1f} cm/360{C.RESET}
  {C.DIM}Set DPI to your mouse's DPI: the same sensitivity then feels the same at any DPI.{C.RESET}""")
        c = input(f"\n  Select: ").strip()
        if c == "1":
            s["sensitivity"] = ask_float("Sensitivity", s["sensitivity"], 0.05, 20)
        elif c == "2":
            s["dpi"] = int(ask_float("Mouse DPI", s["dpi"], 100, 32000))
        elif c == "3":
            s["free_look_multiplier"] = ask_float("Free-look multiplier", s["free_look_multiplier"], 0.1, 5)
        elif c == "4":
            s["ads_multiplier"] = ask_float("Aiming multiplier", s["ads_multiplier"], 0.1, 5)
        elif c == "5":
            s["invert_y"] = not s["invert_y"]
        elif c == "6":
            s["hide_cursor"] = not s["hide_cursor"]
        elif c in ("0", ""):
            save_settings(s)
            return
        save_settings(s)


def status_line(text: str):
    """Rewrite the single status line in place."""
    if C.RESET:
        sys.stdout.write("\r\033[K  " + text)
    else:
        sys.stdout.write("\r  " + text.ljust(76))
    sys.stdout.flush()


def run_aim(s: dict, rpcs3: Path):
    clear(); header()
    print(f"\n  {C.BOLD}MOUSE AIM{C.RESET}   {C.DIM}Press Ctrl+C to stop{C.RESET}\n")
    if C.RESET:
        sys.stdout.write("\033[?25l")          # hide the console caret while the status line updates
    feeder = MouseFeeder.get(s)
    mem, last_state = None, None
    fps, fps_frames, fps_time = 0, 0, time.time()
    try:
        while True:
            pid, _ = find_process()
            if mem and (not pid or pid != mem.pid or not mem.alive()):
                feeder.detach(); mem.close(); mem = None
            no_access = False
            if pid and mem is None:
                mem = GameMemory(pid)
                no_access = not mem.h
                if mem.base is None:
                    mem.close(); mem = None
            if not pid:
                state = "no-rpcs3"
            elif mem is None:
                state = "no-access" if no_access else "no-game"
            else:
                state = mem.patch_state()

            if state != last_state:
                if state == "active":
                    feeder.attach(mem)
                    fps, fps_frames, fps_time = 0, mem.frames(), time.time()
                else:
                    feeder.detach()
                    if state == "not-loaded":
                        ensure_patch(rpcs3)      # make sure it is enabled for the next boot
                last_state = state
            feeder.update_focus(state == "active")

            if state == "active":
                now = time.time()
                if now - fps_time >= 1.0:
                    f = mem.frames()
                    fps = round((f - fps_frames) / (now - fps_time))
                    fps_frames, fps_time = f, now
                fps_text = f"  {C.DIM}·  {fps} FPS{C.RESET}" if fps > 0 else ""
                if feeder.focused:
                    mode = "aiming" if feeder.ads else "free look"
                    status_line(f"{C.GREEN}● Active{C.RESET}  {C.DIM}·{C.RESET}  {mode}{fps_text}")
                else:
                    status_line(f"{C.YELLOW}○ Paused{C.RESET}  {C.DIM}·  click into the game window{C.RESET}{fps_text}")
            else:
                colour, mark, text = {
                    "no-rpcs3": (C.DIM, "○", "Waiting for RPCS3..."),
                    "no-game": (C.DIM, "○", "RPCS3 is open - load Uncharted 3"),
                    "not-loaded": (C.YELLOW, "●", "Game runs without the patch - restart RPCS3 and load the game"),
                    "other": (C.RED, "●", "Another mouse patch is active - disable it and restart"),
                    "no-access": (C.RED, "!", "Cannot read RPCS3 - run this program as administrator"),
                }[state]
                status_line(f"{colour}{mark} {text}{C.RESET}")
            time.sleep(0.1 if state == "active" else 0.5)
    except KeyboardInterrupt:
        pass
    finally:
        feeder.release()
        if mem:
            mem.close()
        if C.RESET:
            sys.stdout.write("\033[?25h")
        status_line(f"{C.DIM}Stopped.{C.RESET}\n")
        time.sleep(0.6)


def main():
    if os.name != "nt":
        sys.exit("This program runs on Windows only.")
    init_console()
    s = load_settings()
    clear(); header()
    rpcs3 = locate_rpcs3(s)
    patch = ensure_patch(rpcs3)
    if "--start" in sys.argv:
        run_aim(s, rpcs3)
        return
    while True:
        clear(); header()
        print_status(rpcs3, patch, s)
        print(f"""
  {C.CYAN}1{C.RESET}  Help
  {C.CYAN}2{C.RESET}  Settings
  {C.CYAN}3{C.RESET}  Start mouse aim
  {C.CYAN}4{C.RESET}  Exit""")
        c = input(f"\n  Select: ").strip()
        if c == "1":
            show_help()
        elif c == "2":
            settings_menu(s)
        elif c == "3":
            run_aim(s, rpcs3)
        elif c == "4":
            return


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
