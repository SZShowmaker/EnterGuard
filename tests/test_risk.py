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
    r.update_config(switch_threshold_seconds=-1, sensitive_words=["密码"])
    assert r.switch_threshold_seconds == -1
    assert r.sensitive_words == ["密码"]
    print("  update_config PASS")


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
    print("\n=== ALL RISK TESTS PASSED ===")
