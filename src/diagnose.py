"""
diagnose.py - 在 Windows 上一键诊断钩子问题
运行: python src/diagnose.py
会打印: Python位数, 是否管理员, 窗口信息, hook能否安装
"""
import sys
import struct
import ctypes

print("=== Diagnose ===")
print(f"Python: {sys.version}")
print(f"Executable: {sys.executable}")
bits = struct.calcsize("P") * 8
print(f"Bits: {bits}")
print(f"Platform: {sys.platform}")

if sys.platform != "win32":
    print("非Windows, 仅mock")
    sys.exit(0)

# 管理员检查
try:
    is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    print(f"IsAdmin: {is_admin}")
except:
    print("IsAdmin: unknown")

# 前台窗口
user32 = ctypes.windll.user32
hwnd = user32.GetForegroundWindow()
print(f"Foreground HWND: {hwnd}")
if hwnd:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    print(f"  Title: {buf.value!r}")
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    print(f"  Class: {cls_buf.value!r}")

# 测试 hook 安装 (复用 hook.py 逻辑)
print("\n--- 测试 SetWindowsHookExW ---")
import queue
from config import AppConfig
from hook import HookManager

cfg = AppConfig()
q = queue.Queue()
hm = HookManager(cfg, q, logger=print)
hm.start()
import time

time.sleep(1.2)
print(f"hook_handle after start: {hm.hook_handle}")
print(f"running: {hm.running}")
if hm.hook_handle:
    print("✅ hook 安装成功! 现在按 Enter (在诊断窗口有焦点时) 应被拦截, 但诊断窗口不是钉钉所以会放行")
    print("   请切到钉钉输入框按 Enter 测试 (需保持 diagnose 运行 + 另开 Guard)")
else:
    print("❌ hook 安装失败")
    # 尝试 fallback
    print("\n--- 尝试 keyboard fallback ---")
    try:
        import keyboard

        print(f"keyboard version: {keyboard.__version__ if hasattr(keyboard,'__version__') else 'unknown'}")
        print("尝试 keyboard.hook ...")
        # 简单监听3秒
        events = []

        def on_evt(e):
            events.append(e)
            print(f"  keyboard event: {e.name} {e.event_type}")

        h = keyboard.hook(on_evt)
        print("keyboard hook installed, 请在3秒内按任意键...")
        time.sleep(3)
        keyboard.unhook(h)
        print(f"收到 {len(events)} 个事件, keyboard 可用")
    except ImportError:
        print("keyboard 未安装, pip install keyboard")
    except Exception as e:
        print(f"keyboard hook failed: {e}")

hm.stop()
print("done")
