"""
test_safe.py - 安全自检, 绝不向钉钉发送消息
可在 WSL/Linux 下运行, 也可在 Windows 测试模式下运行
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import AppConfig
from uia import extract_group_name_from_title, get_foreground_info, get_input_preview


def test_config():
    print("=== test_config ===")
    cfg = AppConfig()
    assert cfg.master_enabled in (True, False)
    assert cfg.test_mode is True  # 默认必须为 True (安全)
    print(f"master={cfg.master_enabled} test_mode={cfg.test_mode}")
    # 多应用可扩展
    assert "DingTalk" in cfg.apps
    assert "Feishu" in cfg.apps
    assert "WeChat" in cfg.apps
    # 关键词匹配
    k, _ = cfg.get_app_by_window("测试群 - 钉钉", "StandardFrame_DingTalk")
    assert k == "DingTalk", f"should match DingTalk, got {k}"
    k, _ = cfg.get_app_by_window("微信", "WeChatMainWndForPC")
    # WeChat默认关闭, 不应匹配
    assert k is None, "WeChat disabled should not match"
    # 开启后应匹配
    cfg.apps["WeChat"]["enabled"] = True
    k, _ = cfg.get_app_by_window("微信", "WeChatMainWndForPC")
    assert k == "WeChat"
    print("test_config PASS")


def test_group_extract():
    print("=== test_group_extract ===")
    cases = [
        ("前端交流群 - 钉钉", "前端交流群"),
        ("张三 - 钉钉", "张三"),
        ("钉钉", "钉钉"),
        ("My Group - DingTalk", "My Group"),
        ("飞书群 - 飞书", "飞书群"),
        ("", "未知会话"),
    ]
    for title, expect in cases:
        got = extract_group_name_from_title(title)
        assert got == expect, f"title={title!r} expect={expect!r} got={got!r}"
        print(f"  {title!r} -> {got!r}")
    print("test_group_extract PASS")


def test_hook_mock():
    print("=== test_hook_mock ===")
    import queue
    from hook import HookManager

    cfg = AppConfig()
    cfg.test_mode = True  # 安全
    q = queue.Queue()
    hm = HookManager(cfg, q, logger=lambda m: print(f"  [hook log] {m}"))
    hm.start()
    assert hm.running
    # 模拟 replay 在测试模式下不应真发
    hm.replay_enter()  # 应打印 测试模式开启, 不重放
    hm.stop()
    assert not hm.running
    print("test_hook_mock PASS")


def test_uia_mock():
    print("=== test_uia_mock (Linux mock) ===")
    info = get_foreground_info()
    print(f"  info={info}")
    assert "group_name" in info
    assert "preview" in info
    preview = get_input_preview()
    print(f"  preview={preview[:40]}")
    print("test_uia_mock PASS")


if __name__ == "__main__":
    test_config()
    test_group_extract()
    test_hook_mock()
    test_uia_mock()
    print("\n=== ALL SAFE TESTS PASSED ===")
    print("注意: 这些测试均未向钉钉发送任何消息")
