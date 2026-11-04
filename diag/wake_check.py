#!/usr/bin/env python3
# wake_check.py — 唤醒客机控制台并回读像素亮度（黑屏=控制台没渲染）
# 关机重启后常见：显示器休眠 / 控制台没在渲染 → screen_grab 全黑，所有像素断言失效。
import ctypes
import sys
import time

u = ctypes.WinDLL("user32", use_last_error=True)

# 真实按键（Shift/Ctrl/Alt/Win 单击）——比 mouse_event 更可靠地唤醒显示器
for vk in (0x10, 0x11, 0x12, 0x5B):
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 2, 0)
    time.sleep(0.15)

# 鼠标来回移动
for _ in range(30):
    u.SetCursorPos(900, 400)
    time.sleep(0.05)
    u.SetCursorPos(960, 430)
    time.sleep(0.05)
time.sleep(2)

sys.path.insert(0, r"C:\coil\orca-blackbox")
sys.path.insert(0, r"C:\coil\orca-blackbox\tests")
from harness import winutil  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

sw, sh, buf = winutil.screen_grab()
img = np.frombuffer(buf, np.uint8).reshape(sh, sw, 4)[:, :, :3]
print(f"[wake] screen {sw}x{sh} mean_brightness={float(img.mean()):.1f} "
      f"max={int(img.max())}")
cv2.imwrite(r"C:\coil\orca-blackbox\artifacts\m8x125_desktop.png", img)

# 顺带把显示器/会话状态打出来
print("[wake] foreground:", u.GetForegroundWindow())
