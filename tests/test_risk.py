"""
test_risk.py - 第二阶段风险检测单元测试
覆盖: 聊天对象变化检测, 敏感词命中, 首次放行, 阈值边界, last_target 更新时机
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from risk import RiskAssessor


def test_first_send_low_risk():
    print("=== test_first_send_low_risk ===")
    r = RiskAssessor(switch_threshold_seconds=0, sensitive_words=["工资"])
    # 首次: 无基准, 无敏感词 -> 低风险
    res = r.assess("DingTalk", "前端群", "在吗")
    assert not res["high_risk"], f"首次应低风险, got {res}"
    # 拦截时更新
    r.update_last_target("DingTalk", "前端群")
    assert r.last_target is not None
    print("  首次发送低风险 PASS")


def test_target_change_high_risk():
    print("=== test_target_change_high_risk ===")
    r = RiskAssessor(switch_threshold_seconds=0, sensitive_words=[])
    r.update_last_target("DingTalk", "前端群")
    # 切到另一个群 (同 app) -> 高风险 (阈值0=任何变化都弹)
    res = r.assess("DingTalk", "后端群", "hi")
    assert res["high_risk"], f"群变化应高风险, got {res}"
    assert any("聊天对象发生变化" in x for x in res["reasons"])
    # 切到另一个 app -> 高风险
    r2 = RiskAssessor(switch_threshold_seconds=0, sensitive_words=[])
    r2.update_last_target("DingTalk", "前端群")
    res = r2.assess("WeChat", "微信", "hi")
    assert res["high_risk"], f"app变化应高风险, got {res}"
    print("  对象变化检测 PASS")


def test_no_change_low_risk():
    print("=== test_no_change_low_risk ===")
    r = RiskAssessor(switch_threshold_seconds=0, sensitive_words=[])
    r.update_last_target("DingTalk", "前端群")
    # 同一对象 -> 低风险
    res = r.assess("DingTalk", "前端群", "在吗")
    assert not res["high_risk"], f"对象未变应低风险, got {res}"
    print("  对象未变低风险 PASS")


def test_sensitive_word():
    print("=== test_sensitive_word ===")
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=["工资", "密码", "password"])  # 关闭对象检测
    r.update_last_target("DingTalk", "前端群")
    # 命中 -> 高风险
    res = r.assess("DingTalk", "前端群", "这个月工资发了没")
    assert res["high_risk"]
    assert res["hit_word"] == "工资"
    # 大小写不敏感 (英文词)
    res = r.assess("DingTalk", "前端群", "give me the PASSWORD")
    assert res["high_risk"]
    assert res["hit_word"].lower() == "password"
    # 不命中 -> 低风险
    res = r.assess("DingTalk", "前端群", "今天天气不错")
    assert not res["high_risk"]
    # 首次但命中敏感词 -> 仍高风险
    r2 = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=["工资"])
    res = r2.assess("DingTalk", "前端群", "工资多少")
    assert res["high_risk"], "首次但含敏感词应高风险"
    print("  敏感词检测 PASS")


def test_threshold_disabled():
    print("=== test_threshold_disabled ===")
    # 负数阈值 = 关闭对象变化检测
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=[])
    r.update_last_target("DingTalk", "前端群")
    res = r.assess("DingTalk", "后端群", "hi")
    assert not res["high_risk"], f"关闭对象检测应低风险, got {res}"
    print("  阈值关闭 PASS")


def test_threshold_window():
    print("=== test_threshold_window ===")
    # 阈值 1 秒: 1秒内变化才弹, 超过则不弹
    r = RiskAssessor(switch_threshold_seconds=1, sensitive_words=[])
    r.update_last_target("DingTalk", "前端群")
    # 立即变化 -> 高风险
    res = r.assess("DingTalk", "后端群", "hi")
    assert res["high_risk"], f"窗口内应高风险, got {res}"
    print("  阈值窗口内 PASS")


def test_last_target_updated_on_intercept():
    print("=== test_last_target_updated_on_intercept ===")
    # 规格要求: 拦截时更新 (不论确认/取消), 以"尝试发送的对象"为准
    r = RiskAssessor(switch_threshold_seconds=0, sensitive_words=[])
    r.update_last_target("DingTalk", "前端群")
    # 用户在"后端群"拦截 -> 更新 last_target=后端群
    # 即使随后"取消", 下次在"后端群"发也应是低风险 (因为基准已是后端群)
    r.assess("DingTalk", "后端群", "hi")
    r.update_last_target("DingTalk", "后端群")
    res = r.assess("DingTalk", "后端群", "hi again")
    assert not res["high_risk"], f"取消后基准应已更新, got {res}"
    print("  拦截时更新 PASS")


def test_wechat_app_level_only():
    print("=== test_wechat_app_level_only ===")
    # 微信群名读不到 (标题恒为"微信"), 群切换检测不到, 但 app 切换能检测
    r = RiskAssessor(switch_threshold_seconds=0, sensitive_words=[])
    r.update_last_target("WeChat", "微信")
    # 微信内切群: group_name 仍是"微信" -> 低风险 (已知限制)
    res = r.assess("WeChat", "微信", "hi")
    assert not res["high_risk"], f"微信群内切换应低风险(限制), got {res}"
    # 钉钉切到微信 -> 高风险 (app 变化)
    r2 = RiskAssessor(switch_threshold_seconds=0, sensitive_words=[])
    r2.update_last_target("DingTalk", "前端群")
    res = r2.assess("WeChat", "微信", "hi")
    assert res["high_risk"], f"app切换应高风险, got {res}"
    print("  微信app级限制 PASS")


def test_update_config():
    print("=== test_update_config ===")
    r = RiskAssessor(switch_threshold_seconds=0, sensitive_words=["工资"])
    r.update_config(switch_threshold_seconds=-1, sensitive_words=["密码"],
                    at_trigger_mode="any", at_all_keywords=["@all"], at_extra_keywords=["@老板"],
                    high_risk_group_keywords=["客户"], quiet_hours={"enabled": True, "start": "23:00", "end": "07:00"})
    assert r.switch_threshold_seconds == -1
    assert r.sensitive_words == ["密码"]
    assert r.at_trigger_mode == "any"
    assert r.at_all_keywords == ["@all"]
    assert r.at_extra_keywords == ["@老板"]
    assert r.high_risk_group_keywords == ["客户"]
    assert r.quiet_hours["enabled"] is True
    print("  update_config PASS")


def test_at_all_mode():
    print("=== test_at_all_mode ===")
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=[],
                     at_trigger_mode="all", at_all_keywords=["@所有人", "@all", "@全体"])
    # @所有人 -> 高风险
    res = r.assess("DingTalk", "前端群", "通知 @所有人 明天开会")
    assert res["high_risk"] and res["hit_at"] == "@所有人", res
    # 大小写
    res = r.assess("DingTalk", "前端群", "hey @ALL see this")
    assert res["high_risk"], res
    # 普通 @某人 不弹 (mode=all)
    res = r.assess("DingTalk", "前端群", "@张三 在吗")
    assert not res["high_risk"], f"mode=all 时普通@不应弹, got {res}"
    print("  @all 模式 PASS")


def test_at_any_mode():
    print("=== test_at_any_mode ===")
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=[], at_trigger_mode="any")
    # 任何 @ 都弹
    res = r.assess("DingTalk", "前端群", "@张三 在吗")
    assert res["high_risk"] and res["hit_at"] == "@", res
    print("  @any 模式 PASS")


def test_at_off_mode():
    print("=== test_at_off_mode ===")
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=[], at_trigger_mode="off")
    res = r.assess("DingTalk", "前端群", "@所有人 注意")
    assert not res["high_risk"], f"off 模式不应弹, got {res}"
    print("  @off 模式 PASS")


def test_at_extra_keywords():
    print("=== test_at_extra_keywords ===")
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=[],
                     at_trigger_mode="all", at_all_keywords=["@所有人"],
                     at_extra_keywords=["@老板", "@王总"])
    # 用户自定义@词生效
    res = r.assess("DingTalk", "前端群", "@老板 这个方案您看下")
    assert res["high_risk"] and res["hit_at"] == "@老板", res
    # 不在列表的普通@不弹
    res = r.assess("DingTalk", "前端群", "@小李 好的")
    assert not res["high_risk"], res
    print("  @自定义词 PASS")


def test_high_risk_group():
    print("=== test_high_risk_group ===")
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=[],
                     high_risk_group_keywords=["客户", "外部", "全员", "external"])
    # 群名命中 -> 高风险, 即使对象未变
    r.update_last_target("DingTalk", "客户A群")
    res = r.assess("DingTalk", "客户A群", "你好")
    assert res["high_risk"] and res["hit_group_kw"] == "客户", res
    # 大小写 (英文词)
    res = r.assess("DingTalk", "External Partner", "hi")
    assert res["high_risk"] and res["hit_group_kw"].lower() == "external", res
    # 未命中 -> 低风险
    res = r.assess("DingTalk", "内部技术群", "你好")
    assert not res["high_risk"], res
    print("  高危群 PASS")


def test_quiet_hours_same_day():
    print("=== test_quiet_hours_same_day ===")
    # 同天时段 09:00~18:00: 用 datetime.now() 检测, 这里只验证逻辑结构
    # 直接测 _in_quiet_hours 用 monkeypatch 当前时间不可行(它用 datetime.now),
    # 改为构造一个已知落在窗口内/外的 quiet_hours 验证跨午夜分支
    from datetime import datetime
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=[],
                     quiet_hours={"enabled": False, "start": "00:00", "end": "23:59"})
    # 关闭 -> 永不触发
    assert r._in_quiet_hours() is False
    # 开启且全天生效
    r.update_config(quiet_hours={"enabled": True, "start": "00:00", "end": "23:59"})
    assert r._in_quiet_hours() is True
    print("  静默时段同天 PASS")


def test_quiet_hours_cross_midnight():
    print("=== test_quiet_hours_cross_midnight ===")
    from risk import RiskAssessor
    r = RiskAssessor(switch_threshold_seconds=-1, sensitive_words=[],
                     quiet_hours={"enabled": True, "start": "22:00", "end": "08:00"})
    # 用 monkeypatch datetime 验证跨午夜
    import risk as rmod
    orig = rmod.datetime
    class FakeDT:
        @staticmethod
        def now():
            return orig.strptime("2026-08-27 23:30:00", "%Y-%m-%d %H:%M:%S")
    rmod.datetime = FakeDT
    try:
        assert r._in_quiet_hours() is True, "23:30 应在 22:00~08:00 内"
    finally:
        rmod.datetime = orig

    class FakeDT2:
        @staticmethod
        def now():
            return orig.strptime("2026-08-27 03:00:00", "%Y-%m-%d %H:%M:%S")
    rmod.datetime = FakeDT2
    try:
        assert r._in_quiet_hours() is True, "03:00 应在 22:00~08:00 内(跨午夜)"
    finally:
        rmod.datetime = orig

    class FakeDT3:
        @staticmethod
        def now():
            return orig.strptime("2026-08-27 12:00:00", "%Y-%m-%d %H:%M:%S")
    rmod.datetime = FakeDT3
    try:
        assert r._in_quiet_hours() is False, "12:00 不应在 22:00~08:00 内"
    finally:
        rmod.datetime = orig
    print("  静默时段跨午夜 PASS")


def test_combined_high_risk():
    print("=== test_combined_high_risk ===")
    # 多个原因同时命中
    r = RiskAssessor(switch_threshold_seconds=0, sensitive_words=["工资"],
                     at_trigger_mode="all", at_all_keywords=["@所有人"],
                     high_risk_group_keywords=["客户"],
                     quiet_hours={"enabled": True, "start": "00:00", "end": "23:59"})
    r.update_last_target("DingTalk", "技术群")
    res = r.assess("DingTalk", "客户群", "@所有人 本月工资已发")
    assert res["high_risk"]
    reasons = "; ".join(res["reasons"])
    assert "聊天对象" in reasons
    assert "工资" in reasons
    assert "@所有人" in reasons
    assert "客户" in reasons
    assert "非工作时间" in reasons
    print(f"  多原因组合 PASS ({len(res['reasons'])} 个)")


if __name__ == "__main__":
    test_first_send_low_risk()
    test_target_change_high_risk()
    test_no_change_low_risk()
    test_sensitive_word()
    test_threshold_disabled()
    test_threshold_window()
    test_last_target_updated_on_intercept()
    test_wechat_app_level_only()
    test_update_config()
    test_at_all_mode()
    test_at_any_mode()
    test_at_off_mode()
    test_at_extra_keywords()
    test_high_risk_group()
    test_quiet_hours_same_day()
    test_quiet_hours_cross_midnight()
    test_combined_high_risk()
    print("\n=== ALL RISK TESTS PASSED ===")
