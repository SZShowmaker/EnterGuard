"""
main.py - 可视化主窗口
功能:
  - 总开关: 显式开启/关闭拦截
  - 应用开关: 钉钉/飞书/微信可分别勾选, 后续可扩展
  - 测试模式: 默认开启, 拦截后不重放Enter, 绝不误发 (强烈建议验证阶段保持开启)
  - 状态日志 + 托盘提示
  - 处理 hook 事件队列 -> UIA 读取 -> 弹窗

运行: python src/main.py  (Windows 下)
"""
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import time

IS_WINDOWS = sys.platform == "win32"

# 允许以 `python src/main.py` 和 `python -m src.main` 两种方式运行
try:
    from config import AppConfig
    from hook import HookManager
    from uia import get_foreground_info
    from dialog import show_confirm_dialog
    from risk import RiskAssessor
except ImportError:
    from .config import AppConfig
    from .hook import HookManager
    from .uia import get_foreground_info
    from .dialog import show_confirm_dialog
    from .risk import RiskAssessor


class App:
    def __init__(self, root):
        self.root = root
        self.config = AppConfig()
        self.event_queue = queue.Queue(maxsize=32)
        self.hook = HookManager(self.config, self.event_queue, logger=self.log)
        self._dialog_open = False
        # 风险检测器 (第二阶段): 低风险静默放行, 高风险才弹窗
        self.risk = RiskAssessor(
            switch_threshold_seconds=self.config.switch_threshold_seconds,
            sensitive_words=self.config.sensitive_words,
            quiet_hours=self.config.quiet_hours,
        )

        self.root.title("消息发送二次确认 - DingDing Guard")
        # 自适应: 先设较大默认, 之后按内容自动调整
        self.root.geometry("560x620")
        self.root.minsize(540, 560)
        # Windows下设置图标和置顶提示
        try:
            self.root.attributes("-topmost", False)
        except:
            pass

        self.build_ui()
        self.hook.start()
        self.update_status()
        # 轮询钩子事件
        self.root.after(100, self.poll_events)
        # 关闭协议
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.log("=== DingDing Guard 已启动 ===")
        # 诊断信息: Python位数
        import struct

        bits = struct.calcsize("P") * 8
        self.log(f"Python位数: {bits}位 | 可执行: {sys.executable}")
        self.log(f"测试模式: {'开启(安全, 不会真发)' if self.config.test_mode else '关闭(会真发!)'}")
        self.log(f"总开关: {'开启' if self.config.master_enabled else '关闭'}")
        self.log(f"当前系统: {sys.platform} {'(真实钩子)' if IS_WINDOWS else '(模拟, 仅Linux开发)'}")
        if not IS_WINDOWS:
            self.log("⚠️ 当前为Linux/WSL, 无法真实拦截钉钉, 仅为界面预览。")
            self.log("   请将本项目拷贝到 Windows 上运行: python src/main.py")
        self.log("提示: 测试模式开启时, 拦截后点'确认发送'也不会重放Enter, 可安全测试。")
        self.log("")
        # 延迟检查钩子是否真的装上
        self.root.after(800, self.check_hook_installed)

    def build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista" if IS_WINDOWS else "clam")
        except:
            pass

        # 顶部标题
        header = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        header.pack(fill="x")
        ttk.Label(header, text="🛡️ 消息发送二次确认", font=("微软雅黑", 14, "bold")).pack(anchor="w")
        ttk.Label(header, text="在钉钉/飞书/微信按 Enter 前弹窗确认, 防止手滑发错群", font=("微软雅黑", 8), foreground="#6b7280").pack(anchor="w", pady=(2, 0))

        # 总开关区
        master_frame = ttk.LabelFrame(self.root, text=" 总控制 ", padding=12)
        master_frame.pack(fill="x", padx=16, pady=(8, 8))

        self.master_var = tk.BooleanVar(value=self.config.master_enabled)
        self.test_var = tk.BooleanVar(value=self.config.test_mode)

        # 总开关 - 用大按钮更直观
        self.master_btn = ttk.Button(master_frame, text="", command=self.toggle_master, width=20)
        self.master_btn.pack(anchor="w", pady=(0, 8))
        self._refresh_master_btn()

        # 测试模式
        test_cb = ttk.Checkbutton(
            master_frame,
            text="🛡️ 测试模式 (开启时点'确认'也不会真发送, 安全)",
            variable=self.test_var,
            command=self.toggle_test_mode,
        )
        test_cb.pack(anchor="w")
        ttk.Label(master_frame, text="建议: 先开启测试模式验证弹窗, 确认无误后再关闭", font=("微软雅黑", 7), foreground="#059669").pack(anchor="w", padx=(22, 0))

        # --- 第二阶段: 风险检测配置 ---
        risk_frame = ttk.LabelFrame(self.root, text=" 风险检测 (高风险才弹窗, 低风险静默放行) ", padding=12)
        risk_frame.pack(fill="x", padx=16, pady=(0, 8))

        row1 = ttk.Frame(risk_frame)
        row1.pack(fill="x", pady=(0, 6))
        ttk.Label(row1, text="切换阈值(秒):", font=("微软雅黑", 8)).pack(side="left")
        self.threshold_var = tk.StringVar(value=str(self.config.switch_threshold_seconds))
        ttk.Entry(row1, textvariable=self.threshold_var, width=6, font=("微软雅黑", 8)).pack(side="left", padx=(4, 8))
        ttk.Button(row1, text="保存", width=6, command=self.save_threshold).pack(side="left")
        ttk.Label(
            row1,
            text="0=任何变化都弹  负数=关闭对象变化检测  正数=N秒内切换才弹",
            font=("微软雅黑", 7),
            foreground="#6b7280",
        ).pack(side="left", padx=(8, 0))

        row2 = ttk.Frame(risk_frame)
        row2.pack(fill="x")
        ttk.Label(row2, text="敏感词:", font=("微软雅黑", 8)).pack(side="left")
        self.words_count_var = tk.StringVar(value=f"当前 {len(self.config.sensitive_words)} 个")
        ttk.Label(row2, textvariable=self.words_count_var, font=("微软雅黑", 8), foreground="#2563eb").pack(side="left", padx=(4, 8))
        ttk.Button(row2, text="编辑敏感词", command=self.edit_sensitive_words).pack(side="left")
        ttk.Label(
            row2,
            text="消息含敏感词时必弹 (大小写不敏感, 子串匹配)",
            font=("微软雅黑", 7),
            foreground="#6b7280",
        ).pack(side="left", padx=(8, 0))

        # 静默时段
        row5 = ttk.Frame(risk_frame)
        row5.pack(fill="x", pady=(6, 0))
        self.quiet_enabled_var = tk.BooleanVar(value=self.config.quiet_hours.get("enabled", False))
        ttk.Checkbutton(row5, text="静默时段", variable=self.quiet_enabled_var, command=self.save_quiet_hours).pack(side="left")
        ttk.Label(row5, text="起:", font=("微软雅黑", 8)).pack(side="left", padx=(6, 0))
        self.quiet_start_var = tk.StringVar(value=self.config.quiet_hours.get("start", "22:00"))
        ttk.Entry(row5, textvariable=self.quiet_start_var, width=6, font=("微软雅黑", 8)).pack(side="left", padx=(2, 6))
        ttk.Label(row5, text="止:", font=("微软雅黑", 8)).pack(side="left", padx=(0, 0))
        self.quiet_end_var = tk.StringVar(value=self.config.quiet_hours.get("end", "08:00"))
        ttk.Entry(row5, textvariable=self.quiet_end_var, width=6, font=("微软雅黑", 8)).pack(side="left", padx=(2, 8))
        ttk.Button(row5, text="保存", width=6, command=self.save_quiet_hours).pack(side="left")
        ttk.Label(
            row5,
            text="时段内一律高风险 (支持跨午夜, 如 22:00~08:00)",
            font=("微软雅黑", 7),
            foreground="#6b7280",
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            risk_frame,
            text="首次发送默认放行(无基准); 新版钉钉用选中项索引检测群切换; 微信只能检测app级切换(已知限制)",
            font=("微软雅黑", 7),
            foreground="#9ca3af",
            wraplength=460,
        ).pack(anchor="w", pady=(6, 0))

        # 应用开关区 (可扩展)
        app_frame = ttk.LabelFrame(self.root, text=" 监控应用 (可多选, 后续可扩展) ", padding=12)
        app_frame.pack(fill="x", padx=16, pady=(0, 8))

        self.app_vars = {}
        # 动态生成 Checkbutton, 后续加应用只需改 config.DEFAULT_APPS
        for idx, (key, app) in enumerate(self.config.apps.items()):
            var = tk.BooleanVar(value=app.get("enabled", False))
            self.app_vars[key] = var
            cb = ttk.Checkbutton(
                app_frame,
                text=f"{app.get('display_name','')} ({key})  - 关键词: {', '.join(app.get('keywords',[])[:2])}",
                variable=var,
                command=lambda k=key, v=var: self.toggle_app(k, v.get()),
            )
            cb.grid(row=idx, column=0, sticky="w", pady=2)
            # 状态灯
            dot = ttk.Label(app_frame, text="●", foreground="#10b981" if var.get() else "#d1d5db", font=("微软雅黑", 8))
            dot.grid(row=idx, column=1, padx=(8, 0))
            # 保存引用以便刷新
            # 简单存一下
            if not hasattr(self, "_app_dots"):
                self._app_dots = {}
            self._app_dots[key] = dot

        ttk.Label(app_frame, text="提示: 已勾选的应用, 前台按 Enter 才会拦截。搜索框误弹是已知现象(已接受)。", font=("微软雅黑", 7), foreground="#9ca3af", wraplength=460).grid(
            row=len(self.config.apps), column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        # 状态栏 - 先 pack 到底部, 保证始终可见
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, font=("微软雅黑", 7), foreground="#6b7280", anchor="w", padding=(16, 4))
        status_bar.pack(fill="x", side="bottom")

        # 底部按钮 - 固定在状态栏上方, side=bottom 保证不被日志区挤出
        bottom = ttk.Frame(self.root, padding=(16, 8, 16, 12))
        bottom.pack(fill="x", side="bottom")

        ttk.Button(bottom, text="清空日志", command=self.clear_log).pack(side="left")
        ttk.Button(bottom, text="自检 UIA", command=self.inspect_uia).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="重启钩子", command=self.restart_hook).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="退出", command=self.on_close).pack(side="right")
        # 模拟拦截按钮 (Windows下也保留, 用于安全测试弹窗)
        ttk.Button(bottom, text="模拟拦截", command=self.mock_intercept).pack(side="right", padx=(0, 8))

        # 状态日志 - 最后 pack 填充剩余空间, 随窗口自适应
        log_frame = ttk.LabelFrame(self.root, text=" 运行日志 ", padding=8)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.log_text = tk.Text(log_frame, height=8, wrap="word", font=("Consolas", 8) if IS_WINDOWS else ("Monospace", 8), bg="#f9fafb", relief="flat")
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.configure(state="disabled")
        # 窗口自适应: 根据内容计算所需高度, 保证底栏可见
        self.root.update_idletasks()
        req_h = self.root.winfo_reqheight()
        # 若当前设置高度小于需求, 自动扩高 (限制在屏幕 80% 内)
        try:
            screen_h = self.root.winfo_screenheight()
            cur_w = self.root.winfo_width()
            # 取 max(当前620, 需求+60装饰)
            new_h = max(620, min(req_h + 60, int(screen_h * 0.85)))
            self.root.geometry(f"560x{new_h}")
        except:
            pass

    def _refresh_master_btn(self):
        if self.master_var.get():
            self.master_btn.configure(text="🟢 防护已开启 (点击关闭)")
        else:
            self.master_btn.configure(text="🔴 防护已关闭 (点击开启)")

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        print(line, end="")
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", line)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except:
            pass

    def update_status(self):
        master = "开启" if self.config.master_enabled else "关闭"
        test = "测试" if self.config.test_mode else "真实"
        enabled_apps = [k for k, v in self.config.apps.items() if v.get("enabled")]
        self.status_var.set(f"防护:{master} | 模式:{test} | 监控:{'/'.join(enabled_apps) if enabled_apps else '无'} | 钩子:{'运行中' if self.hook.running else '未运行'}")

    # --- 事件处理 ---
    def toggle_master(self):
        new_val = not self.master_var.get()
        self.master_var.set(new_val)
        self.config.master_enabled = new_val
        self.config.save()
        self._refresh_master_btn()
        self.update_status()
        self.log(f"总开关 -> {'开启' if new_val else '关闭'}")

    def toggle_test_mode(self):
        val = self.test_var.get()
        self.config.test_mode = val
        self.config.save()
        self.update_status()
        if val:
            self.log("测试模式 -> 开启 (安全, 不会重放Enter)")
        else:
            self.log("⚠️ 测试模式 -> 关闭 (点确认会真发送Enter!)")
            # 二次提醒
            messagebox.showwarning("提醒", "测试模式已关闭\n\n此后在钉钉按Enter并点'确认发送'会真的把消息发出去!\n\n请确认你是在安全环境测试。", parent=self.root)

    def toggle_app(self, key, val):
        self.config.apps[key]["enabled"] = val
        self.config.save()
        if key in self._app_dots:
            self._app_dots[key].configure(foreground="#10b981" if val else "#d1d5db")
        self.update_status()
        self.log(f"应用 {key} -> {'监控' if val else '忽略'}")

    def save_threshold(self):
        raw = self.threshold_var.get().strip()
        try:
            val = int(raw)
        except ValueError:
            messagebox.showwarning("提示", f"请输入整数, 当前输入: {raw!r}", parent=self.root)
            self.threshold_var.set(str(self.config.switch_threshold_seconds))
            return
        self.config.switch_threshold_seconds = val
        self.config.save()
        self.risk.update_config(switch_threshold_seconds=val)
        desc = "任何变化都弹" if val == 0 else ("关闭对象变化检测" if val < 0 else f"{val}秒内切换才弹")
        self.log(f"切换阈值 -> {val} ({desc})")

    def edit_sensitive_words(self):
        """弹出敏感词编辑窗口, 每行一个词"""
        def on_save(words):
            self.config.sensitive_words = words
            self.config.save()
            self.risk.update_config(sensitive_words=words)
            self.words_count_var.set(f"当前 {len(words)} 个")
            self.log(f"敏感词已更新 -> {len(words)} 个")

        self._edit_word_list(
            title="编辑敏感词 (每行一个)",
            hint="每行一个词, 大小写不敏感, 子串匹配. 空行自动忽略",
            initial=list(self.config.sensitive_words),
            on_save=on_save,
        )

    def _edit_word_list(self, title, hint, initial, on_save):
        """通用列表编辑器弹窗: 每行一个词. on_save(words) 在保存时回调."""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.attributes("-topmost", True)
        win.geometry("520x480")
        win.minsize(440, 380)
        win.resizable(True, True)
        try:
            win.grab_set()
        except:
            pass

        ttk.Label(win, text=hint, font=("微软雅黑", 8), foreground="#6b7280", justify="left").pack(anchor="w", padx=10, pady=(8, 4))

        def do_save():
            raw = txt.get("1.0", "end").splitlines()
            words = [w.strip() for w in raw if w.strip()]
            try:
                on_save(words)
            except Exception as e:
                self.log(f"保存失败: {e}")
            win.destroy()

        def do_cancel():
            win.destroy()

        # 先 pack 底部按钮 (side=bottom), 再 pack 可扩展 Text, 否则按钮被挤出可视区
        btns = ttk.Frame(win)
        btns.pack(fill="x", side="bottom", padx=10, pady=(4, 10))
        ttk.Button(btns, text="保存", command=do_save).pack(side="right", padx=(4, 0))
        ttk.Button(btns, text="取消", command=do_cancel).pack(side="right")

        txt = tk.Text(win, wrap="word", font=("微软雅黑", 9))
        txt.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        for w in initial:
            txt.insert("end", w + "\n")

        self.root.wait_window(win)

    def save_quiet_hours(self):
        enabled = bool(self.quiet_enabled_var.get())
        start = self.quiet_start_var.get().strip()
        end = self.quiet_end_var.get().strip()
        # 简单校验 HH:MM
        def _ok(t):
            parts = t.split(":")
            if len(parts) != 2:
                return False
            try:
                h, m = int(parts[0]), int(parts[1])
                return 0 <= h < 24 and 0 <= m < 60
            except ValueError:
                return False
        if not (_ok(start) and _ok(end)):
            messagebox.showwarning("提示", f"时间格式应为 HH:MM, 如 22:00\n当前: 起={start!r} 止={end!r}", parent=self.root)
            self.quiet_start_var.set(self.config.quiet_hours.get("start", "22:00"))
            self.quiet_end_var.set(self.config.quiet_hours.get("end", "08:00"))
            self.quiet_enabled_var.set(self.config.quiet_hours.get("enabled", False))
            return
        qh = {"enabled": enabled, "start": start, "end": end}
        self.config.quiet_hours = qh
        self.config.save()
        self.risk.update_config(quiet_hours=qh)
        self.log(f"静默时段 -> {'开启' if enabled else '关闭'} ({start}~{end})")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def inspect_uia(self):
        self.log("--- 开始 UIA 自检 (请5秒内切到钉钉输入框) ---")
        # 在后台线程做, 避免卡UI
        def task():
            time.sleep(5)
            try:
                from uia import get_foreground_info, inspect_current_window

                info = get_foreground_info()
                self.log(f"自检结果: title='{info['title']}'")
                self.log(f"  group='{info['group_name']}' preview='{info['preview'][:60] if info['preview'] else '(空)'}'")
                # 详细树打印到控制台
                inspect_current_window()
                self.log("自检完成, 详情见控制台/日志")
                if not info["preview"]:
                    self.log("提示: 预览为空可能是钉钉自绘导致, 仍可拦截, 只是弹窗不显示内容")
            except Exception as e:
                self.log(f"自检失败: {e}")

        threading.Thread(target=task, daemon=True).start()

    def check_hook_installed(self):
        if IS_WINDOWS and not self.hook.hook_handle:
            self.log("❌ 钩子未安装成功 (handle为0), 拦截不会生效!")
            self.log("  原因 err=126 为 MOD_NOT_FOUND, 已在新版尝试 hMod=0 修复, 请重启应用")
            self.log("  若仍失败: 1)以管理员身份运行 2)确认Python为64位(如系统是64位) 3)检查杀毒/安全软件是否拦截")
            self.status_var.set("钩子: 安装失败 ❌ 请点 重启钩子 或以管理员重开")
        elif IS_WINDOWS and self.hook.hook_handle:
            self.log(f"✅ 钩子已就绪 handle={self.hook.hook_handle} , 现在可在钉钉按Enter测试 (测试模式安全)")
            self.update_status()

    def restart_hook(self):
        self.log("--- 重启钩子 ---")
        self.hook.stop()
        import time

        time.sleep(0.3)
        self.hook.start()
        self.update_status()
        self.root.after(800, self.check_hook_installed)

    def mock_intercept(self):
        """模拟一次拦截, 用于安全测试弹窗 (不经过钩子, 直接走弹窗流程)"""
        self.event_queue.put({"type": "enter_intercepted", "app_key": "DingTalk", "title": "测试群 - 钉钉", "class_name": "Mock"})
        self.log("[mock] 已注入模拟拦截事件 -> 应立即弹窗 (若不弹, 检查弹窗是否被遮挡)")

    def poll_events(self):
        """主线程轮询钩子事件, 避免在钩子线程弹UI"""
        # 若弹窗已打开, 暂不处理新事件, 避免队列堆积导致重复弹窗
        if self._dialog_open:
            self.root.after(80, self.poll_events)
            return
        try:
            while True:
                evt = self.event_queue.get_nowait()
                if evt.get("type") == "enter_intercepted":
                    # 若已有弹窗, 丢弃重复事件
                    if self._dialog_open:
                        self.log("[intercept] 已有弹窗, 忽略重复 Enter")
                        continue
                    self.handle_intercept(evt)
                    # 一次只处理一个弹窗, 剩余等弹窗关闭后再处理
                    break
        except queue.Empty:
            pass
        self.root.after(80, self.poll_events)

    def handle_intercept(self, evt):
        if self._dialog_open:
            self.log("[intercept] 弹窗已打开, 忽略")
            return
        self._dialog_open = True
        # 同步到 hook, 已在 hook 拦截时设为 True, 这里再确保
        self.hook.set_dialog_open(True)
        if not self.config.master_enabled:
            self.log("[intercept] 已关闭防护, 忽略")
            self._dialog_open = False
            self.hook.set_dialog_open(False)
            return
        app_key = evt.get("app_key", "Unknown")
        app = self.config.apps.get(app_key, {})
        app_display = app.get("display_name", app_key)
        title = evt.get("title", "")
        class_name = evt.get("class_name", "")

        # UIA 读取群名和预览 (在主线程做, 钩子已吞掉Enter, 有时间)
        info = get_foreground_info()
        # 优先用 UIA 标题, 否则用钩子时捕获的标题
        group_name = info.get("group_name") or title
        preview = info.get("preview") or ""
        real_title = info.get("title") or title
        real_cls = info.get("class_name") or class_name

        # 如果UIA没读到群名, 用hook时的title兜底
        if not group_name or group_name == "未知会话":
            from uia import extract_group_name_from_title

            group_name = extract_group_name_from_title(real_title)

        # --- 第二阶段: 风险检测 ---
        # 拦截时立即更新 last_target (不论后续确认/取消), 以"尝试发送的对象"为准
        risk = self.risk.assess(app_key, group_name, preview)
        is_first = self.risk.last_target is None
        self.risk.update_last_target(app_key, group_name)

        evt_hwnd = evt.get("hwnd", 0)

        if not risk["high_risk"]:
            # 低风险: 静默放行, 不弹窗
            tag = "首次发送" if is_first else "对象未变且无敏感词"
            self.log(f"[intercept] 低风险放行 ({tag}) | {app_display} | 群:{group_name} | 预览:{preview[:30] if preview else '(空)'}")
            self._dialog_open = False
            self.hook.set_dialog_open(False)
            # 焦点切回原应用后重放 Enter
            self._restore_focus_and_replay(evt_hwnd, app_key, group_name)
            return

        # 高风险: 弹窗
        reason_str = "; ".join(risk["reasons"])
        self.log(f"[intercept] ⚠️ 高风险 -> 弹窗 | {app_display} | 群:{group_name} | 原因:{reason_str} | 预览:{preview[:30] if preview else '(空)'}")

        # 弹窗 (模态, 阻塞)
        try:
            confirmed = show_confirm_dialog(
                self.root, app_key, app_display, group_name, preview, real_title, real_cls, self.config.test_mode,
                reasons=risk["reasons"],
                hwnd_setter=self.hook.set_dialog_hwnd,
            )
        except Exception as e:
            self.log(f"[dialog] error: {e}")
            confirmed = False
        finally:
            self._dialog_open = False
            self.hook.set_dialog_open(False)
            self.hook.set_dialog_hwnd(0)
            # 清空弹窗期间堆积的重复 Enter, 避免关闭后立即又弹
            try:
                cleared = 0
                while not self.event_queue.empty():
                    self.event_queue.get_nowait()
                    cleared += 1
                if cleared:
                    self.log(f"[intercept] 已清理 {cleared} 个堆积事件")
            except:
                pass
            # 注意: 不要 self.root.focus_force() — 那会把焦点拉回 Guard 主窗口,
            # 导致 replay_enter 的 SendInput 把 Enter 发给 Guard 而非原应用.
            # 焦点恢复由下面的 SetForegroundWindow + replay_enter 内部处理.

        # 焦点切回原应用窗口 (弹窗是 Toplevel(root), 关闭后焦点默认回到 Guard, 必须显式切回)
        # 否则确认后 SendInput 的 Enter 会发给 Guard 自己, 取消后用户也无法继续编辑原消息
        if IS_WINDOWS and evt_hwnd:
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(evt_hwnd)
                ctypes.windll.user32.SetFocus(evt_hwnd)
            except Exception as e:
                self.log(f"[intercept] 恢复焦点失败: {e}")

        if confirmed:
            self.log(f"[user] 确认发送 -> {group_name} ({app_key})")
            self.hook.replay_enter(app_key, target_hwnd=evt_hwnd)
        else:
            self.log(f"[user] 取消发送 -> {group_name}")

    def _restore_focus_and_replay(self, evt_hwnd, app_key, group_name):
        """低风险放行: 焦点切回原应用后重放 Enter (复用 replay_enter 的安全路径)"""
        if IS_WINDOWS and evt_hwnd:
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(evt_hwnd)
                ctypes.windll.user32.SetFocus(evt_hwnd)
            except Exception as e:
                self.log(f"[intercept] 恢复焦点失败: {e}")
        self.hook.replay_enter(app_key, target_hwnd=evt_hwnd)

    def on_close(self):
        if messagebox.askokcancel("退出", "确定退出 DingDing Guard?\n退出后将不再拦截。", parent=self.root):
            self.hook.stop()
            self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
