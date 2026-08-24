"""
hook_fallback.py - 基于 keyboard 库的备用钩子
当 ctypes 的 SetWindowsHookExW 失败时启用 (err=126等)

需要: pip install keyboard
注意: keyboard 的 suppress 在部分系统需要管理员权限
"""
import sys
import queue

IS_WINDOWS = sys.platform == "win32"


class KeyboardFallback:
    def __init__(self, config, event_queue, logger):
        self.config = config
        self.event_queue = event_queue
        self.logger = logger
        self.hook = None
        self.running = False

    def log(self, msg):
        self.logger(msg)

    def start(self):
        if not IS_WINDOWS:
            self.log("[fallback] non-Windows, no fallback needed")
            return False
        try:
            import keyboard
        except ImportError:
            self.log("[fallback] keyboard 库未安装, 请 pip install keyboard 后重试")
            self.log("[fallback] 安装: pip install keyboard")
            return False

        def on_key(event):
            # event.name == 'enter', event_type == 'down'
            if event.name != "enter" or event.event_type != "down":
                return
            # keyboard 无法直接判断是否是注入, 用时间戳简单过滤? 先不处理
            # 检查修饰键
            # keyboard.is_pressed 可查
            try:
                if keyboard.is_pressed("shift") or keyboard.is_pressed("ctrl") or keyboard.is_pressed("alt"):
                    return
            except:
                pass
            # 检查前台窗口
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value or ""
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cls = cls_buf.value or ""
            if not self.config.master_enabled:
                return
            app_key, _ = self.config.get_app_by_window(title, cls)
            if not app_key:
                return
            self.log(f"[fallback] 拦截 Enter | 应用={app_key} | 标题={title}")
            try:
                self.event_queue.put_nowait({"type": "enter_intercepted", "app_key": app_key, "title": title, "class_name": cls})
            except queue.Full:
                pass
            # 返回 False 且 suppress=True 会拦截, 但 keyboard 需要在 hook 时设置 suppress
            # 这里通过返回来? 实际 keyboard 的回调返回值不影响, suppress 由 hook 参数控制
            # 所以我们需要 suppress=True, 则所有 enter 都会被拦, 需要手动放行非目标的
            # 妥协: fallback 下只 suppress 目标应用的 enter, 其他放行通过额外 Send
            # 但 keyboard 无法动态决定 suppress, 所以 fallback 有局限: 要么全拦要么全放
            # 我们选择 hook 时 suppress=False, 然后在拦截后用 keyboard.block? 复杂
            # 简化: 提示用户此 fallback 仅用于诊断
            return

        try:
            # 尝试 suppress=True 全局拦, 然后非目标我们手动重放 (会有延迟)
            # 这里先用 suppress=False 仅监听, 不拦截, 仅用于验证事件是否能收到
            self.hook = keyboard.hook(on_key, suppress=False)
            self.running = True
            self.log("[fallback] keyboard hook 已安装 (监听模式, 不拦截)")
            self.log("[fallback] 若此模式能收到钉钉Enter日志, 说明是 ctypes hMod问题, 可改用 suppress=True 版本")
            return True
        except Exception as e:
            self.log(f"[fallback] 启动失败: {e} (可能需要管理员权限)")
            return False

        # 完整拦截版本 (需管理员):
        # self.hook = keyboard.hook(on_key, suppress=True)
        # 然后在 on_key  return True/False 控制? 但实际需自己管理

    def stop(self):
        if self.running:
            try:
                import keyboard

                if self.hook:
                    keyboard.unhook(self.hook)
            except:
                pass
            self.running = False
            self.log("[fallback] 已停止")

    def replay_enter(self):
        if self.config.test_mode:
            self.log("[fallback] 测试模式, 不重放")
            return
        self.log("[fallback] 重放 Enter")
        try:
            import keyboard

            keyboard.send("enter")
        except Exception as e:
            self.log(f"[fallback] send failed: {e}")
            # 备用 ctypes SendInput
            from hook import send_enter

            send_enter()
