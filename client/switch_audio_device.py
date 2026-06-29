#!/usr/bin/env python3
"""
HAJIMI — Windows 音频输出设备列表
====================================
直接列出 Windows 声音设置中可见的音频输出设备（含蓝牙设备）。

用法::

    python client/switch_audio_device.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def list_endpoints():
    """通过 Windows Audio Session API 列出输出设备（含蓝牙）"""
    import subprocess
    ps = (
        # 通过 WinRT 获取 AudioDevice 信息，覆盖蓝牙设备
        'Add-Type -AssemblyName System.Runtime.WindowsRuntime; '
        '$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions]'
        '.GetMethods() | ? { $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 '
        '-and $_.GetParameters()[0].ParameterType.Name -eq "IAsyncOperation`1" })[0]; '
        'Function Await($WinRtTask, $ResultType) { '
        '  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType); '
        '  $netTask = $asTask.Invoke($null, @($WinRtTask)); '
        '  $netTask.Wait(-1) | Out-Null; $netTask.Result '
        '}; '
        '[Windows.Media.Devices.MediaDevice, Windows.Media.Devices, '
        '  ContentType=WindowsRuntime] > $null; '
        '$op = [Windows.Media.Devices.MediaDevice]::GetAudioRenderSelector(); '
        '$devices = Await ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync($op)) '
        '  ([Windows.Devices.Enumeration.DeviceInformationCollection]); '
        '$default = Await ([Windows.Devices.Enumeration.DeviceInformation]::CreateFromIdAsync('
        '  [Windows.Media.Devices.MediaDevice]::GetDefaultAudioRenderId('
        '  [Windows.Media.Devices.AudioDeviceRole]::Default))) '
        '  ([Windows.Devices.Enumeration.DeviceInformation]); '
        '$defaultId = $default.Id; '
        '$i = 0; '
        'foreach ($d in $devices) { '
        '  $mark = if ($d.Id -eq $defaultId) { " <<< 默认" } else { "" }; '
        '  Write-Host ("  [{0}] {1}{2}" -f $i, $d.Name, $mark); '
        '  $i++ '
        '}'
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            timeout=15,
        )
    except Exception as e:
        # 降级：WMI 方式（不含蓝牙）
        print("  (WinRT 查询失败，降级到 WMI — 可能不显示蓝牙设备)")
        ps2 = (
            'Get-CimInstance Win32_SoundDevice | '
            'Where-Object { $_.StatusInfo -eq 3 } | '
            'ForEach-Object { Write-Host ("    " + $_.Name) }'
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps2],
                timeout=10,
            )
        except Exception:
            print("  查询失败")


if __name__ == "__main__":
    print()
    print("  Windows 音频输出设备 (含蓝牙)")
    print("─" * 50)
    list_endpoints()
    print("─" * 50)
    print()
    print("  pyttsx3 通过系统默认设备播放。")
    print("  右键任务栏喇叭图标 → 选择目标耳机即可切换。")
