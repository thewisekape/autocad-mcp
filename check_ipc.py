"""
check_ipc.py — Quick File IPC readiness check for AutoCAD MCP Server

Run with:  python check_ipc.py

Checks three things:
  1. Is the LISP dispatcher registered in AutoCAD's Startup Suite (setup.bat was run)?
  2. Is the IPC temp directory accessible?
  3. Is an AutoCAD window visible on screen right now?
"""

import os
import sys
from pathlib import Path

# ── ANSI colours ──────────────────────────────────────────────────────────────
OK   = "\033[92m[OK]   \033[0m"
WARN = "\033[93m[WARN] \033[0m"
FAIL = "\033[91m[FAIL] \033[0m"
INFO = "\033[94m[INFO] \033[0m"

LISP_FILE = Path(__file__).parent / "lisp-code" / "mcp_dispatch.lsp"
IPC_DIR   = Path(os.environ.get("AUTOCAD_MCP_IPC_DIR", "C:/temp"))

print()
print("=" * 60)
print("  AutoCAD MCP — File IPC Readiness Check")
print("=" * 60)

# ── 1. LISP file exists on disk ───────────────────────────────────────────────
print(f"\n{INFO}LISP dispatcher path: {LISP_FILE}")
if LISP_FILE.exists():
    print(f"{OK}mcp_dispatch.lsp exists on disk")
else:
    print(f"{FAIL}mcp_dispatch.lsp NOT found at expected location")
    print(f"      Expected: {LISP_FILE}")

# ── 2. Registry check (Windows only) ─────────────────────────────────────────
if sys.platform == "win32":
    try:
        import winreg

        # Registry path used by autoload_lisp.ps1:
        # HKCU\SOFTWARE\Autodesk\AutoCAD\{ver}\{ACAD-xxxx:xxxx}\Profiles\{profile}\Dialogs\Appload\Startup
        # Values: NumStartup (int), 1Startup, 2Startup, ... (strings with file paths)
        autocad_reg = r"SOFTWARE\Autodesk\AutoCAD"
        found_in_registry = False
        registered_profiles = []

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autocad_reg) as acad_key:
                i = 0
                while True:
                    try:
                        version = winreg.EnumKey(acad_key, i)
                        ver_path = f"{autocad_reg}\\{version}"
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ver_path) as ver_key:
                            j = 0
                            while True:
                                try:
                                    prod = winreg.EnumKey(ver_key, j)
                                    if not prod.upper().startswith("ACAD-"):
                                        j += 1
                                        continue
                                    prof_root_path = f"{ver_path}\\{prod}\\Profiles"
                                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, prof_root_path) as prof_root:
                                        k = 0
                                        while True:
                                            try:
                                                profile = winreg.EnumKey(prof_root, k)
                                                startup_path = f"{prof_root_path}\\{profile}\\Dialogs\\Appload\\Startup"
                                                try:
                                                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, startup_path) as startup_key:
                                                        num, _ = winreg.QueryValueEx(startup_key, "NumStartup")
                                                        for n in range(1, int(num) + 1):
                                                            try:
                                                                val, _ = winreg.QueryValueEx(startup_key, f"{n}Startup")
                                                                if "mcp_dispatch" in val.lower():
                                                                    found_in_registry = True
                                                                    registered_profiles.append(profile)
                                                            except FileNotFoundError:
                                                                pass
                                                except FileNotFoundError:
                                                    pass
                                                k += 1
                                            except OSError:
                                                break
                                    j += 1
                                except OSError:
                                    break
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            pass

        if found_in_registry:
            print(f"{OK}mcp_dispatch.lsp is registered in AutoCAD's Startup Suite")
            for p in registered_profiles:
                print(f"      Profile: {p}")
            print(f"      LISP will auto-load every time AutoCAD starts")
        else:
            print(f"{WARN}mcp_dispatch.lsp is NOT in AutoCAD's Startup Suite")
            print(f"      Run setup.bat, or in AutoCAD type:")
            lisp_path = str(LISP_FILE).replace("\\", "/")
            print(f'      (load "{lisp_path}")')

    except ImportError:
        print(f"{WARN}winreg not available — skipping registry check")

# ── 3. IPC temp directory ─────────────────────────────────────────────────────
print(f"\n{INFO}IPC directory: {IPC_DIR}")
if IPC_DIR.exists():
    # Check writability
    test_file = IPC_DIR / ".mcp_write_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
        print(f"{OK}IPC directory exists and is writable")
    except OSError as e:
        print(f"{FAIL}IPC directory exists but is NOT writable: {e}")
else:
    try:
        IPC_DIR.mkdir(parents=True, exist_ok=True)
        print(f"{OK}IPC directory created: {IPC_DIR}")
    except OSError as e:
        print(f"{FAIL}Cannot create IPC directory: {e}")
        print(f"      Set AUTOCAD_MCP_IPC_DIR to a writable path")

# Stale file check
stale = list(IPC_DIR.glob("autocad_mcp_*.json")) if IPC_DIR.exists() else []
if stale:
    print(f"{WARN}{len(stale)} stale IPC file(s) found in {IPC_DIR} — may be from a crashed session")
    for f in stale:
        print(f"      {f.name}")

# ── 4. AutoCAD window detection ───────────────────────────────────────────────
print()
if sys.platform == "win32":
    try:
        import win32gui

        def _find_window(hwnd, results):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).lower()
            if "autocad" in title and ("drawing" in title or ".dwg" in title):
                results.append((hwnd, win32gui.GetWindowText(hwnd)))

        windows = []
        win32gui.EnumWindows(_find_window, windows)

        if windows:
            print(f"{OK}AutoCAD window detected:")
            for hwnd, title in windows:
                print(f"      HWND={hwnd}  Title: \"{title}\"")
            print(f"\n{OK}File IPC can connect to this window")
        else:
            print(f"{WARN}No AutoCAD window found on screen")
            print(f"      File IPC requires AutoCAD to be open with a drawing loaded")
            print(f"      COM backend or ezdxf backend will be used instead")

    except ImportError:
        print(f"{WARN}win32gui not available — install pywin32 to enable window detection")
        print(f"      pip install pywin32")

# ── 5. Summary ────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  Summary")
print("=" * 60)
print(f"""
  To use File IPC:
    1. Ensure AutoCAD is open with a .dwg file loaded
    2. Run setup.bat (once) to register the LISP auto-loader
       OR manually load in AutoCAD command line:
       (load "{str(LISP_FILE).replace(chr(92), '/')}")
    3. Set env var:  AUTOCAD_MCP_BACKEND=file_ipc
       OR leave as 'auto' (File IPC takes priority over COM)

  Current AUTOCAD_MCP_BACKEND = {os.environ.get('AUTOCAD_MCP_BACKEND', 'auto (default)')}
  Current AUTOCAD_MCP_IPC_DIR = {os.environ.get('AUTOCAD_MCP_IPC_DIR', 'C:/temp (default)')}
""")
