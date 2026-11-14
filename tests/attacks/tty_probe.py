"""Drive `cli.py approve` through a real Windows console.

No monkeypatching and no piped stdin: the child gets its own console
(``CREATE_NEW_CONSOLE``), so its ``sys.stdin.isatty()`` is genuinely True and
``input()`` blocks on console read.  The keystrokes are injected into that
console's input buffer with ``WriteConsoleInputW``, which is what a human's
keyboard fills.

Two trials:
  typed    type `approve promote`  -> a token must be issued
  refused  type `no`               -> exit 2, no token, no key
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
# scratch workspaces live outside the repository, so running the probe
# never leaves residue in the tree it is testing.
WORK = Path(os.environ.get("CHELATE_ATTACK_ROOT")
            or tempfile.mkdtemp(prefix="chelate-attack-"))
PY = sys.executable

CREATE_NEW_CONSOLE = 0x00000010
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
VK_RETURN = 0x0D

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                            wintypes.HANDLE]
k32.WriteConsoleInputW.argtypes = [wintypes.HANDLE,
                                   ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.DWORD,
                                   ctypes.POINTER(wintypes.DWORD)]


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [("bKeyDown", wintypes.BOOL),
                ("wRepeatCount", wintypes.WORD),
                ("wVirtualKeyCode", wintypes.WORD),
                ("wVirtualScanCode", wintypes.WORD),
                ("UnicodeChar", wintypes.WCHAR),
                ("dwControlKeyState", wintypes.DWORD)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD),
                ("Event", KEY_EVENT_RECORD)]


KEY_EVENT = 0x0001


def _records(text: str):
    out = []
    for ch in text + "\r":
        vk = VK_RETURN if ch == "\r" else (ord(ch.upper()) if ch.isalpha()
                                            else 0)
        for down in (1, 0):
            rec = INPUT_RECORD()
            rec.EventType = KEY_EVENT
            rec.Event.bKeyDown = down
            rec.Event.wRepeatCount = 1
            rec.Event.wVirtualKeyCode = vk
            rec.Event.UnicodeChar = ch if down else "\x00"
            out.append(rec)
    return out


def type_into(pid: int, text: str) -> str:
    k32.FreeConsole()
    if not k32.AttachConsole(pid):
        return f"AttachConsole failed: {ctypes.get_last_error()}"
    try:
        h = k32.CreateFileW("CONIN$", GENERIC_READ | GENERIC_WRITE,
                            FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                            OPEN_EXISTING, 0, None)
        if h in (None, wintypes.HANDLE(-1).value):
            return f"CONIN$ open failed: {ctypes.get_last_error()}"
        recs = _records(text)
        arr = (INPUT_RECORD * len(recs))(*recs)
        written = wintypes.DWORD(0)
        ok = k32.WriteConsoleInputW(
            wintypes.HANDLE(h), ctypes.cast(arr, ctypes.POINTER(ctypes.c_void_p)),
            len(recs), ctypes.byref(written))
        if not ok:
            return f"WriteConsoleInput failed: {ctypes.get_last_error()}"
        return f"wrote {written.value} input records"
    finally:
        k32.FreeConsole()


def run_trial(tag: str, answer: str, ws_name: str):
    ws = WORK / ws_name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    (ws / "data.csv").write_text("x,y\n1,2\n3,4\n", encoding="utf-8")

    cmd = [PY, "cli.py", "approve", "--root", str(ws), "--mode", "c",
           "--selected", "data-profiler", "--inputs", str(ws / "data.csv")]
    proc = subprocess.Popen(cmd, cwd=str(REPO),
                            creationflags=CREATE_NEW_CONSOLE)
    time.sleep(2.5)                       # let it reach the prompt
    detail = type_into(proc.pid, answer)
    try:
        code = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = "TIMEOUT"

    tokens = list((ws / ".chelate" / "approvals").glob("*.json")) \
        if (ws / ".chelate" / "approvals").is_dir() else []
    print(f"[{tag}] typed={answer!r} exit={code} tokens={len(tokens)} "
          f"-> {detail}")
    return code, tokens


if __name__ == "__main__":
    before = {p.name for p in (Path.home() / "AppData" / "Local" /
                               "chelate" / "keys").glob("*.key")} \
        if (Path.home() / "AppData" / "Local" / "chelate" / "keys").is_dir() \
        else set()

    run_trial("typed  ", "approve promote", "ws_tty_ok")
    run_trial("refused", "no", "ws_tty_no")

    root = Path.home() / "AppData" / "Local" / "chelate" / "keys"
    after = {p.name for p in root.glob("*.key")} if root.is_dir() else set()
    print(f"[keys] new key files created: {sorted(after - before)}")
