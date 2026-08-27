"""
dialog.py - 二次确认弹窗
用 tkinter 实现, 零依赖, TopMost
"""
import sys

IS_WINDOWS = sys.platform == "win32"


def show_confirm_dialog(parent, app_key: str, app_display: str, group_name: str, preview: str, title: str, class_name: str, test_mode: bool, reasons=None, hwnd_setter=None) -> bool:
    """
    弹出确认框, 返回 True=用户点发送, False=取消
    parent: tkinter root 或 None
    reasons: 风险原因列表 (第二阶段), 展示在标题下方, 如 ["检测到聊天对象发生变化", "消息含敏感词: 工资"]
    hwnd_setter: 可选回调 fn(hwnd), 弹窗创建后传入其顶级 HWND, 供钩子判断前台是否切到弹窗
    """
    # 非Windows或无tk环境降级为控制台确认 (供Linux开发测试)
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as e:
        print(f"[dialog] tkinter unavailable: {e}")
        print(f"--- 拦截预览 ---")
        print(f"应用: {app_display}({app_key})")
        print(f"群名: {group_name}")
        print(f"标题: {title}")
        print(f"内容: {preview[:120] if preview else '(无法读取)'}")
        print(f"测试模式: {test_mode}")
        # Linux下默认返回 False (取消) 避免误发
        return False

    result = {"confirmed": False}

    # 创建 Toplevel, 保证在最前
    dialog = tk.Toplevel(parent) if parent else tk.Toplevel()
    dialog.title("发送确认")
    dialog.attributes("-topmost", True)
    dialog.resizable(False, False)
    # 先不设固定大小, 让内容决定大小, 之后再居中
    # 防止在多屏/高DPI下被裁剪, 先给一个临时位置
    dialog.geometry("+0+0")
    # 强制先 withdraw 避免闪烁定位错误 (可选)
    dialog.withdraw()

    # 样式
    style = ttk.Style(dialog)
    try:
        style.theme_use("vista" if IS_WINDOWS else "clam")
    except:
        pass

    # 内容区
    main = ttk.Frame(dialog, padding=16)
    main.pack(fill="both", expand=True)

    # 标题行 - 带图标
    header = ttk.Label(main, text="⚠️  确定要发送这条消息吗？", font=("微软雅黑", 12, "bold"), foreground="#d97706")
    header.pack(anchor="w", pady=(0, 12))

    # 风险原因 (第二阶段) - 红色高亮展示
    if reasons:
        reason_frame = ttk.Frame(main, relief="solid", borderwidth=1)
        reason_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(reason_frame, text="⚠️ 触发原因:", font=("微软雅黑", 9, "bold"), foreground="#dc2626").pack(anchor="w", padx=8, pady=(6, 2))
        for r in reasons:
            ttk.Label(reason_frame, text=f"• {r}", font=("微软雅黑", 9), foreground="#dc2626").pack(anchor="w", padx=16, pady=1)
        # 留点底部空白
        ttk.Frame(reason_frame, height=4).pack()

    # 应用和群名
    info_frame = ttk.Frame(main)
    info_frame.pack(fill="x", pady=(0, 8))

    ttk.Label(info_frame, text=f"应用: ", font=("微软雅黑", 9, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(info_frame, text=f"{app_display} ({app_key})", font=("微软雅黑", 9)).grid(row=0, column=1, sticky="w")

    ttk.Label(info_frame, text=f"会话: ", font=("微软雅黑", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(4, 0))
    # 群名高亮
    group_label = ttk.Label(info_frame, text=group_name or "未知会话", font=("微软雅黑", 10, "bold"), foreground="#2563eb", wraplength=300)
    group_label.grid(row=1, column=1, sticky="w", pady=(4, 0))

    # 窗口标题调试信息 (小字灰色)
    if title:
        ttk.Label(main, text=f"窗口: {title[:40]}", font=("微软雅黑", 7), foreground="#9ca3af").pack(anchor="w")

    # 内容预览框
    ttk.Label(main, text="内容预览:", font=("微软雅黑", 9, "bold")).pack(anchor="w", pady=(12, 4))
    preview_frame = ttk.Frame(main, relief="solid", borderwidth=1)
    preview_frame.pack(fill="both", expand=True, pady=(0, 8))

    text = tk.Text(preview_frame, height=5, wrap="word", font=("微软雅黑", 9), bg="#f9fafb", relief="flat", padx=8, pady=6)
    text.pack(fill="both", expand=True)
    if preview:
        text.insert("1.0", preview[:500])
    else:
        text.insert("1.0", "(无法读取输入框内容，可能是钉钉新版自绘控件)\n但仍可确认是否发送到该会话。")
        text.configure(foreground="#6b7280", font=("微软雅黑", 8, "italic"))
    text.configure(state="disabled")

    # 测试模式提示
    if test_mode:
        tip = ttk.Label(main, text="🛡️ 测试模式已开启: 点发送也不会真发 (安全)", font=("微软雅黑", 8), foreground="#059669")
        tip.pack(anchor="w", pady=(0, 8))

    # 按钮区 - 固定在底部, 保证始终可见
    btn_frame = ttk.Frame(main)
    btn_frame.pack(fill="x", pady=(12, 0), side="bottom")

    # 提示: Enter=发送, Esc=取消
    ttk.Label(btn_frame, text="Enter发送 / Esc取消", font=("微软雅黑", 7), foreground="#9ca3af").pack(side="left")

    def on_confirm(event=None):
        result["confirmed"] = True
        if hwnd_setter:
            try:
                hwnd_setter(0)
            except Exception:
                pass
        try:
            dialog.grab_release()
        except:
            pass
        try:
            dialog.attributes("-topmost", False)
        except:
            pass
        dialog.destroy()

    def on_cancel(event=None):
        result["confirmed"] = False
        if hwnd_setter:
            try:
                hwnd_setter(0)
            except Exception:
                pass
        try:
            dialog.grab_release()
        except:
            pass
        try:
            dialog.attributes("-topmost", False)
        except:
            pass
        dialog.destroy()

    # 按钮顺序: 取消在左, 发送在右 (防手滑) - 用 pack right 保证可见
    btn_cancel = ttk.Button(btn_frame, text="取消 (Esc)", command=on_cancel, width=12)
    btn_cancel.pack(side="right", padx=(8, 0))
    btn_send = ttk.Button(btn_frame, text="确认发送 (Enter)", command=on_confirm, width=14)
    btn_send.pack(side="right")
    # 更显眼的样式 (如果支持)
    try:
        style.configure("Send.TButton", foreground="#dc2626")
        btn_send.configure(style="Send.TButton")
    except:
        pass

    # --- 自适应大小并居中 (关键修复) ---
    dialog.update_idletasks()
    # 让窗口按内容自适应, 最小 420x300, 最大不超过屏幕 70%
    req_w = max(420, dialog.winfo_reqwidth() + 20)
    req_h = max(300, dialog.winfo_reqheight() + 20)
    try:
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        req_w = min(req_w, int(sw * 0.6))
        req_h = min(req_h, int(sh * 0.6))
        x = (sw - req_w) // 2
        y = (sh - req_h) // 2
        dialog.geometry(f"{req_w}x{req_h}+{x}+{y}")
    except:
        dialog.geometry(f"{req_w}x{req_h}")
    dialog.deiconify()  # 显示
    # 强制前台并夺取键盘焦点, 否则 Windows 前台锁会让原应用(微信/钉钉)保留前台,
    # 钩子虽因 dialog_open=True 放行 Enter, 但按键进入原应用把消息发出, 弹窗却收不到 Enter 无法确认.
    # 单纯 SetForegroundWindow 会被前台锁拦截(只闪烁任务栏), 必须用 AttachThreadInput 合并输入队列绕过.
    try:
        dialog.lift()
        dialog.attributes("-topmost", True)
        dialog.focus_force()
        if IS_WINDOWS:
            import ctypes
            from ctypes import wintypes as _wt

            _u = ctypes.windll.user32
            _k = ctypes.windll.kernel32
            _u.GetWindowThreadProcessId.restype = _wt.DWORD
            _u.GetWindowThreadProcessId.argtypes = [_wt.HWND, ctypes.POINTER(_wt.DWORD)]
            _k.GetCurrentThreadId.restype = _wt.DWORD
            _u.AttachThreadInput.restype = _wt.BOOL
            _u.AttachThreadInput.argtypes = [_wt.DWORD, _wt.DWORD, _wt.BOOL]
            _u.SetForegroundWindow.restype = _wt.BOOL
            _u.SetForegroundWindow.argtypes = [_wt.HWND]
            _u.BringWindowToTop.restype = _wt.BOOL
            _u.BringWindowToTop.argtypes = [_wt.HWND]
            _u.SetFocus.restype = _wt.HWND
            _u.SetFocus.argtypes = [_wt.HWND]
            _u.GetAncestor.restype = _wt.HWND
            _u.GetAncestor.argtypes = [_wt.HWND, _wt.UINT]
            _u.ShowWindow.restype = _wt.BOOL
            _u.ShowWindow.argtypes = [_wt.HWND, ctypes.c_int]

            hwnd = dialog.winfo_id()
            # winfo_id 对 Toplevel 一般即顶级 HWND, 用 GetAncestor(GA_ROOT) 兜底取根窗口
            top_hwnd = _u.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT = 2
            # 通知钩子弹窗的 HWND, 使其在 dialog_open 期间判断 Enter 该不该放行
            if hwnd_setter:
                try:
                    hwnd_setter(top_hwnd)
                except Exception:
                    pass
            fg = _u.GetForegroundWindow()
            my_tid = _k.GetCurrentThreadId()
            fg_tid = 0
            attached = False
            # 合并本线程与前台线程的输入队列, 使 SetForegroundWindow 被允许
            if fg and fg != top_hwnd:
                fg_tid = _u.GetWindowThreadProcessId(fg, None)
                if fg_tid and fg_tid != my_tid:
                    attached = bool(_u.AttachThreadInput(my_tid, fg_tid, True))
            try:
                _u.ShowWindow(top_hwnd, 9)  # SW_RESTORE = 9, 防止最小化状态下无法激活
                _u.SetForegroundWindow(top_hwnd)
                _u.BringWindowToTop(top_hwnd)
                _u.SetFocus(top_hwnd)
            finally:
                if attached and fg_tid:
                    _u.AttachThreadInput(my_tid, fg_tid, False)
    except Exception as e:
        print(f"[dialog] focus setup failed: {e}")
    dialog.grab_set()  # 模态 (需在 deiconify 后)
    # 再次确保焦点在确认按钮 (延迟一点, 等 Win32 前台切换生效)
    def _reassert_focus():
        try:
            btn_send.focus_force()
            if IS_WINDOWS:
                import ctypes
                hwnd = dialog.winfo_id()
                ctypes.windll.user32.SetForegroundWindow(
                    ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd
                )
        except Exception:
            pass

    try:
        dialog.after(30, _reassert_focus)
    except:
        pass

    # 键盘绑定 - Enter确认 Esc取消
    # 之前焦点在取消导致按Enter会触发取消按钮的默认调用, 日志显示[user] 取消发送
    # 改为焦点在确认按钮, 且全窗口绑定, 保证按Enter即确认
    dialog.bind("<Return>", on_confirm)
    dialog.bind("<Escape>", on_cancel)
    btn_send.bind("<Return>", on_confirm)
    btn_cancel.bind("<Return>", on_confirm)  # 即使焦点在取消, 按Enter也视为确认(符合提示)
    btn_send.focus_set()

    # 窗口关闭等同取消
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    # 声音提示 (Windows)
    if IS_WINDOWS:
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except:
            pass

    # 模态等待
    if parent:
        parent.wait_window(dialog)
    else:
        dialog.wait_window(dialog)

    return result["confirmed"]
