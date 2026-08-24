"""
hook.py - 全局低级键盘钩子 WH_KEYBOARD_LL
只拦截 Enter, 在钩子线程中做最轻量判断, 复杂逻辑抛给主线程

安全说明: 钩子回调中吞掉 Enter (return 1) 后, 只有用户在确认框点"发送"才会用 SendInput 重放一次 Enter
测试模式下不重放, 绝不会误发
"""
import ctypes
from ctypes import wintypes
import threading
import queue
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    kernel32 = None

# 常量
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3

# KBDLLHOOKSTRUCT 结构 - 使用 ULONG_PTR 兼容64位
if IS_WINDOWS:
    # wintypes.ULONG_PTR 在某些Python版本不存在,  fallback到 c_void_p
    try:
        ULONG_PTR = wintypes.ULONG_PTR
    except AttributeError:
        ULONG_PTR = ctypes.c_void_p
        # 兼容部分环境
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            ULONG_PTR = ctypes.c_uint64
        else:
            ULONG_PTR = ctypes.c_ulong

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    # SendInput 相关结构, 必须 40 字节(64位)才被系统接受, 否则 err=87
    INPUT_KEYBOARD = 1
    INPUT_MOUSE = 0
    KEYEVENTF_KEYUP = 0x0002

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("_input",)
        _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT_UNION)]

    # 声明 SendInput/ keybd_event 签名, 用 c_void_p 避免数组类型严格校验
    try:
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
        user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ULONG_PTR]
        user32.keybd_event.restype = None
    except Exception:
        pass


def send_enter():
    """重放一次 Enter 按键 (按下+抬起)"""
    if not IS_WINDOWS:
        print("[hook] send_enter mock (non-Windows)")
        return
    try:
        inp_down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=0, time=0, dwExtraInfo=0))
        inp_up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0))
        inputs = (INPUT * 2)(inp_down, inp_up)
        # 注意: argtypes 已设为 c_void_p, 传数组本体即可, ctypes 会自动转为指针
        n = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
        if n != 2:
            err = kernel32.GetLastError()
            print(f"[hook] SendInput failed, sent {n}/2 err={err} sizeof(INPUT)={ctypes.sizeof(INPUT)}")
            # 备用方案: keybd_event
            print(f"[hook] fallback to keybd_event")
            user32.keybd_event(VK_RETURN, 0, 0, 0)
            user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            if n == 0:
                # 若 SendInput 完全失败, 依赖 fallback 已发送, 视为成功
                return
        else:
            print(f"[hook] SendInput ok, sent {n}/2")
    except Exception as e:
        print(f"[hook] send_enter exception: {e}")
        try:
            user32.keybd_event(VK_RETURN, 0, 0, 0)
            user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            print(f"[hook] fallback keybd_event sent")
            return
        except Exception as e2:
            print(f"[hook] fallback also failed: {e2}")
        raise


class HookManager:
    def __init__(self, config, event_queue: queue.Queue, logger=None):
        """
        config: AppConfig 实例
        event_queue: 主线程队列, 钩子命中时 put 一个事件
        logger: 可选日志回调 func(msg)
        """
        self.config = config
        self.event_queue = event_queue
        self.logger = logger or (lambda m: print(m))
        self.hook_handle = None
        self.hook_proc_ptr = None  # 防止GC回收
        self.thread = None
        self.running = False
        self._hook_proc_type = None
        self.dialog_open = False  # 弹窗打开期间不拦截, 让Enter能到达弹窗
        self._dialog_lock = threading.Lock()

    def log(self, msg):
        self.logger(msg)

    def _is_modifier_pressed(self):
        """检查 Shift/Ctrl/Alt 是否按下, 按下则说明不是单纯的 Enter 发送"""
        if not IS_WINDOWS:
            return False
        # GetAsyncKeyState 高位为1表示按下
        for vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_CONTROL, VK_LCONTROL, VK_RCONTROL, VK_MENU):
            if user32.GetAsyncKeyState(vk) & 0x8000:
                return True
        return False

    def _is_foreground_target_app(self):
        """判断前台窗口是否是已启用的目标应用, 返回 (is_target, app_key, title, class_name)"""
        if not IS_WINDOWS:
            return False, None, "", ""
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False, None, "", ""
        # 标题
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        # 类名
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        class_name = cls_buf.value or ""

        # 总开关
        if not self.config.master_enabled:
            return False, None, title, class_name

        app_key, app = self.config.get_app_by_window(title, class_name)
        if app_key:
            return True, app_key, title, class_name
        return False, None, title, class_name

    def set_dialog_open(self, open_: bool):
        with self._dialog_lock:
            self.dialog_open = open_

    def _low_level_proc(self, nCode, wParam, lParam):
        # 弹窗打开时直接放行, 让Enter能到达确认框
        with self._dialog_lock:
            if self.dialog_open:
                # 放行给弹窗
                if IS_WINDOWS:
                    return user32.CallNextHookEx(self.hook_handle, nCode, wParam, lParam)
                return 0
        # 必须尽快返回, 否则会卡所有键盘输入
        if nCode == 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            try:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                # 只关心 Enter, 且不是注入的事件(避免重放的Enter再次被拦截导致死循环)
                is_injected = (kb.flags & 0x10) != 0  # LLKHF_INJECTED
                if kb.vkCode == VK_RETURN and not is_injected:
                    # 修饰键按下 -> 放行 (Shift+Enter 换行)
                    if self._is_modifier_pressed():
                        pass
                    else:
                        is_target, app_key, title, cls = self._is_foreground_target_app()
                        if is_target:
                            # 命中! 吞掉并通知主线程, 并立即标记弹窗将打开
                            self.log(f"[hook] 拦截 Enter | 应用={app_key} | 标题={title} | 类名={cls}")
                            with self._dialog_lock:
                                self.dialog_open = True
                            # put 事件, 主线程会做 UIA 读取+弹窗
                            try:
                                self.event_queue.put_nowait(
                                    {
                                        "type": "enter_intercepted",
                                        "app_key": app_key,
                                        "title": title,
                                        "class_name": cls,
                                    }
                                )
                            except queue.Full:
                                self.log("[hook] queue full, drop event")
                                with self._dialog_lock:
                                    self.dialog_open = False
                            return 1  # 吞掉, 不传给钉钉
            except Exception as e:
                self.log(f"[hook] proc error: {e}")

        # 放行
        if IS_WINDOWS:
            return user32.CallNextHookEx(self.hook_handle, nCode, wParam, lParam)
        return 0

    def _hook_thread_func(self):
        if not IS_WINDOWS:
            self.log("[hook] non-Windows, mock thread running (no real hook)")
            # 模拟: 空转, 供Linux开发测试
            import time

            while self.running:
                time.sleep(0.5)
            return

        # 定义回调类型, 必须在线程内且保持引用
        # 64位下 WPARAM/LPARAM 是 64位, ctypes.wintypes 的 WPARAM/LPARAM 是 32位会溢出
        # 用 c_size_t / c_void_p 保证64位兼容
        CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p)
        self.hook_proc_ptr = CMPFUNC(self._low_level_proc)
        # 显式声明 CallNextHookEx 参数类型, 避免 OverflowError: int too long to convert
        try:
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p]
            user32.CallNextHookEx.restype = ctypes.c_int
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
        except Exception:
            pass

        # WH_KEYBOARD_LL 是低级钩子, 不注入DLL, hMod应为0(NULL)
        # 之前用 GetModuleHandleW(None) 在部分Python环境下会返回126 ERROR_MOD_NOT_FOUND
        # 参考: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowshookexw
        # 对低级钩子, hMod 必须为 NULL (0), dwThreadId 为 0 表示全局
        for h_mod, desc in [(0, "NULL(0)"), (kernel32.GetModuleHandleW(None), "GetModuleHandleW(None)")]:
            self.log(f"[hook] trying SetWindowsHookExW with hMod={desc} ({h_mod})")
            self.hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.hook_proc_ptr, h_mod, 0)
            if self.hook_handle:
                self.log(f"[hook] success with hMod={desc}")
                break
            err = kernel32.GetLastError()
            self.log(f"[hook] SetWindowsHookExW with {desc} failed, err={err}")
            # 尝试下一种
        if not self.hook_handle:
            err = kernel32.GetLastError()
            self.log(f"[hook] SetWindowsHookExW all attempts failed, err={err} (126=MOD_NOT_FOUND, 5=ACCESS_DENIED)")
            self.log(f"[hook] 提示: 1)请确认Python是64位且与系统一致 2)尝试以管理员身份运行 3)杀毒是否拦截")
            return

        self.log(f"[hook] installed, handle={self.hook_handle}")

        # 消息循环, 必须有, 否则钩子不生效
        msg = wintypes.MSG()
        while self.running:
            # GetMessageW 会阻塞, 用 PeekMessage 避免无法退出
            ret = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)  # PM_REMOVE=1
            if ret != 0:
                if msg.message == 0x0012:  # WM_QUIT
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                # 避免空转高CPU
                import time

                time.sleep(0.01)

        self.log("[hook] thread exiting")

    def start(self):
        if self.running:
            self.log("[hook] already running")
            return True
        self.running = True
        self.thread = threading.Thread(target=self._hook_thread_func, daemon=True, name="HookThread")
        self.thread.start()
        # 等待一点时间看是否安装成功
        import time

        time.sleep(0.2)
        if IS_WINDOWS and not self.hook_handle and self.running:
            # 线程可能还在安装中, 再等
            time.sleep(0.5)
        self.log("[hook] started")
        return True

    def stop(self):
        if not self.running:
            return
        self.running = False
        if IS_WINDOWS and self.hook_handle:
            user32.UnhookWindowsHookEx(self.hook_handle)
            self.hook_handle = None
            self.log("[hook] unhooked")
        # 唤醒消息循环
        if IS_WINDOWS and self.thread:
            user32.PostThreadMessageW(self.thread.ident, 0x0012, 0, 0)  # WM_QUIT
        if self.thread:
            self.thread.join(timeout=1.5)
        self.log("[hook] stopped")

    def replay_enter(self, app_key=""):
        """供主线程在用户确认后调用, 重放Enter"""
        if self.config.test_mode:
            self.log("[hook] 测试模式开启, 不重放Enter (安全, 不会真发送)")
            return
        target = app_key or "目标"
        self.log(f"[hook] 重放 Enter -> {target}")
        # 稍微延迟, 确保确认框已关闭且焦点回到原窗口
        import time

        time.sleep(0.12)
        try:
            send_enter()
            self.log(f"[hook] SendInput 调用完成")
        except Exception as e:
            self.log(f"[hook] 重放异常: {e}")
