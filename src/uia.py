"""
uia.py - 读取群名和输入框内容预览
优先用窗口标题(最稳), 再尝试 UI Automation 读 Edit 的 Value

在 Linux 下为 mock, 不会报错
"""
import sys

IS_WINDOWS = sys.platform == "win32"


def get_window_title_and_class():
    """获取前台窗口标题和类名, 用于日志和群名提取"""
    if not IS_WINDOWS:
        return "MockWindow - 钉钉", "MockClass_DingTalk"
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value or ""
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    cls = cls_buf.value or ""
    return title, cls


def extract_group_name_from_title(title: str) -> str:
    """
    钉钉标题常见格式:
      "群名 - 钉钉" / "人名 - 钉钉" / "钉钉"
    飞书: "群名 - 飞书"
    微信: "微信"
    这里做简单切分, 取 ' - ' 前的部分
    """
    if not title:
        return "未知会话"
    # 去掉 " - 钉钉" 后缀
    for suffix in [" - 钉钉", " - DingTalk", " - 飞书", " - Feishu", " - Lark", " - 微信", " - WeChat"]:
        if title.endswith(suffix):
            name = title[: -len(suffix)].strip()
            return name if name else title
    # 有些版本标题就是群名本身
    if " - " in title:
        return title.split(" - ")[0].strip()
    return title.strip()


def get_input_preview(max_len=120) -> str:
    """
    尝试通过 UI Automation 读取当前焦点输入框的内容
    成功返回文本, 失败返回 "" (不抛异常)
    """
    if not IS_WINDOWS:
        return "【Linux Mock预览】这是一条模拟的消息内容, 用于测试弹窗显示..."

    # 方案1: uiautomation 库 (pip install uiautomation)
    try:
        import uiautomation as auto

        # 获取焦点控件
        focused = auto.GetFocusedControl()
        if focused:
            # 尝试 ValuePattern
            try:
                val = focused.GetValuePattern()
                if val:
                    text = val.Value or ""
                    if text:
                        return text[:max_len]
            except Exception:
                pass
            # 备用: Name 属性有时也存文本
            try:
                name = focused.Name or ""
                # 过滤掉按钮名等, 只有较长文本才认为是输入内容
                if name and len(name) > 1 and name not in ["发送", "Send"]:
                    return name[:max_len]
            except Exception:
                pass
    except ImportError:
        pass
    except Exception as e:
        print(f"[uia] uiautomation read failed: {e}")

    # 方案2: comtypes 直接调 UIA (更底层, 作为兜底)
    try:
        import comtypes.client

        # 这里不做复杂实现, 仅作为扩展点, 避免引入过多依赖
        # 真实场景下可通过 IUIAutomation::GetFocusedElement() 实现
        pass
    except Exception:
        pass

    # 方案3: 读不到就返回空, 调用方会显示"无法读取内容"
    return ""


def get_foreground_info():
    """
    一站式获取: 群名 + 内容预览 + 标题 + 类名
    返回 dict: {title, class_name, group_name, preview}
    """
    title, cls = get_window_title_and_class()
    group = extract_group_name_from_title(title)
    # 内容预览可能稍慢, 放在后面
    preview = get_input_preview()
    return {
        "title": title,
        "class_name": cls,
        "group_name": group,
        "preview": preview,
    }


# --- 自检工具 ---
def inspect_current_window():
    """打印当前前台窗口的 UIA 树, 供用户用来自检钉钉版本是否支持读取"""
    if not IS_WINDOWS:
        print("[inspect] non-Windows mock")
        print(get_foreground_info())
        return
    try:
        import uiautomation as auto

        print("=== 当前前台窗口 UIA 树 (前2层) ===")
        root = auto.GetRootControl()
        # 只打印前台窗口分支, 避免全树过长
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        ctrl = auto.ControlFromHandle(hwnd)
        if ctrl:
            print(f"Handle={hwnd}, Name={ctrl.Name}, Class={ctrl.ClassName}, ControlType={ctrl.ControlTypeName}")
            for child in ctrl.GetChildren()[:20]:
                print(f"  |- {child.ControlTypeName} Name='{child.Name}' Class='{child.ClassName}'")
                # 打印孙子
                try:
                    for gc in child.GetChildren()[:5]:
                        val = ""
                        try:
                            val = gc.GetValuePattern().Value[:50] if gc.GetValuePattern() else ""
                        except:
                            pass
                        print(f"     |- {gc.ControlTypeName} Name='{gc.Name}' Value='{val}'")
                except:
                    pass
        else:
            print("ControlFromHandle failed")
    except ImportError:
        print("[inspect] need pip install uiautomation")
    except Exception as e:
        print(f"[inspect] error: {e}")


if __name__ == "__main__":
    # 命令行自检: python -m src.uia
    import time

    print("请在5秒内把焦点切到钉钉聊天输入框...")
    time.sleep(5)
    info = get_foreground_info()
    print(info)
    print("\n--- UIA Tree ---")
    inspect_current_window()
