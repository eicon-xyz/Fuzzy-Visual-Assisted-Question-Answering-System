"""
Windows window enumeration via PowerShell / Win32 API.

Matches OpenGuider's src/perception/window-enum.js.
Returns visible window titles, class names, rectangles, and cursor position.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# PowerShell script — mirrors OpenGuider's PS logic
_ENUM_WINDOWS_PS = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Generic;

public class Win32Window {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT lpPoint);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT Point);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X, Y; }
}

public class WindowInfo {
    public string Title;
    public string ClassName;
    public int Pid;
    public int X, Y, Width, Height;
}
"@

$windows = @()
$foregroundHwnd = [Win32Window]::GetForegroundWindow()
$foregroundTitle = ""

$callback = {
    param($hwnd, $lParam)
    if (-not [Win32Window]::IsWindowVisible($hwnd)) { return $true }
    $length = [Win32Window]::GetWindowTextLength($hwnd)
    if ($length -eq 0) { return $true }
    $sb = New-Object System.Text.StringBuilder($length + 1)
    [Win32Window]::GetWindowText($hwnd, $sb, $sb.Capacity) | Out-Null
    $title = $sb.ToString()
    if ([string]::IsNullOrWhiteSpace($title)) { return $true }

    $rect = New-Object Win32Window+RECT
    [Win32Window]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
    $w = $rect.Right - $rect.Left
    $h = $rect.Bottom - $rect.Top
    if ($w -lt 50 -or $h -lt 50) { return $true }

    $pid = 0
    [Win32Window]::GetWindowThreadProcessId($hwnd, [ref]$pid) | Out-Null

    $sb2 = New-Object System.Text.StringBuilder(256)
    $windows += @{
        title = $title
        className = ""
        pid = $pid
        rect = @{ x = $rect.Left; y = $rect.Top; width = $w; height = $h }
    }

    if ($hwnd -eq $foregroundHwnd) {
        $script:foregroundTitle = $title
    }
    return $true
}

[Win32Window]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null

$cursor = New-Object Win32Window+POINT
[Win32Window]::GetCursorPos([ref]$cursor) | Out-Null

$maxWindows = 30
$result = @{
    focusedWindow = @{ title = $foregroundTitle; className = ""; pid = 0; rect = @{ x=0;y=0;width=0;height=0 } }
    windows = @($windows | Select-Object -First $maxWindows)
    cursorPosition = @{ x = $cursor.X; y = $cursor.Y }
    totalWindows = $windows.Count
}

ConvertTo-Json -Depth 3 -Compress $result
"""


def enumerate_windows(timeout: int = 8) -> Optional[dict]:
    """Enumerate visible windows and cursor position via PowerShell.

    Args:
        timeout: PowerShell execution timeout in seconds

    Returns:
        {
            "focusedWindow": {title, className, pid, rect},
            "windows": [{title, className, pid, rect}, ...],
            "cursorPosition": {x, y},
            "totalWindows": int
        }
        or None on failure
    """
    try:
        # Write script to temp file (cached — only rewritten if content changes)
        import hashlib

        script_hash = hashlib.md5(_ENUM_WINDOWS_PS.encode()).hexdigest()[:8]
        tmp_dir = os.path.join(tempfile.gettempdir(), "hajimi-ps")
        os.makedirs(tmp_dir, exist_ok=True)
        script_path = os.path.join(tmp_dir, f"window_enum_{script_hash}.ps1")

        if not os.path.exists(script_path):
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(_ENUM_WINDOWS_PS)

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.warning(f"Window enum failed: {result.stderr[:200]}")
            return None

        return json.loads(result.stdout.strip())
    except subprocess.TimeoutExpired:
        logger.warning("Window enum timed out")
        return None
    except Exception as e:
        logger.error(f"Window enum error: {e}")
        return None


def get_focused_window_title() -> str:
    """Quick helper: get the title of the currently focused window."""
    data = enumerate_windows(timeout=5)
    if data and data.get("focusedWindow"):
        return data["focusedWindow"].get("title", "")
    return ""
