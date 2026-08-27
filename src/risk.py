"""
risk.py - 第二阶段风险检测
两类检测, 任一命中即为高风险 -> 触发二次确认弹窗:
  1. 聊天对象变化: 距上次发送 <= switch_threshold_seconds 且 (app_key 或 group_name) 变化
     - 微信 PC 标题恒为 "微信", 群切换检测不到, 只能检测 app 级切换 (已知限制, 接受)
     - switch_threshold_seconds = 0  -> 任何变化都弹 (默认, 严格)
     - switch_threshold_seconds < 0  -> 关闭该检测
  2. 敏感词: 消息内容命中 sensitive_words (大小写不敏感, 子串匹配)

首次发送无基准 -> 低风险放行 (但若命中敏感词仍弹).
last_target 在拦截时更新 (不论最终确认/取消), 以"尝试发送的对象"为准.
"""
import time
from typing import Optional


class RiskAssessor:
    def __init__(self, switch_threshold_seconds: int = 0, sensitive_words=None):
        self.switch_threshold_seconds = switch_threshold_seconds
        self.sensitive_words = [w for w in (sensitive_words or []) if w]
        # last_target: {"app_key": str, "group_name": str, "ts": float}
        self.last_target = None

    def update_config(self, switch_threshold_seconds=None, sensitive_words=None):
        if switch_threshold_seconds is not None:
            self.switch_threshold_seconds = switch_threshold_seconds
        if sensitive_words is not None:
            self.sensitive_words = [w for w in sensitive_words if w]

    def _target_changed(self, app_key: str, group_name: str) -> bool:
        """比对当前目标与上次目标 (app_key + group_name 任一变化即视为变化)"""
        if not self.last_target:
            return False  # 无基准不算变化
        if self.last_target["app_key"] != app_key:
            return True
        # group_name 可能为空或 "未知会话", 此时只看 app 级
        cur_g = group_name or ""
        last_g = self.last_target["group_name"] or ""
        if cur_g and last_g and cur_g != last_g:
            return True
        return False

    def _within_threshold(self) -> bool:
        """距上次发送是否在阈值窗口内"""
        if self.switch_threshold_seconds < 0:
            return False  # 关闭检测
        if not self.last_target:
            return False
        elapsed = time.time() - self.last_target["ts"]
        # 0 表示任何变化都弹 -> 不限时间窗口, 视为恒在窗口内
        if self.switch_threshold_seconds == 0:
            return True
        return elapsed <= self.switch_threshold_seconds

    def _hit_sensitive(self, preview: str) -> Optional[str]:
        """命中敏感词返回该词, 否则 None. 大小写不敏感, 子串匹配."""
        if not preview or not self.sensitive_words:
            return None
        preview_low = preview.lower()
        for w in self.sensitive_words:
            wl = w.lower()
            if wl and wl in preview_low:
                return w
        return None

    def assess(self, app_key: str, group_name: str, preview: str):
        """
        评估风险. 返回 dict:
          { "high_risk": bool,
            "reasons": [str, ...],   # 命中的原因 (供日志/弹窗展示)
            "hit_word": str|None }   # 命中的敏感词
        """
        reasons = []
        hit_word = None

        # 1. 聊天对象变化
        if self._within_threshold() and self._target_changed(app_key, group_name):
            reasons.append("检测到聊天对象发生变化")

        # 2. 敏感词
        hit_word = self._hit_sensitive(preview)
        if hit_word:
            reasons.append(f"消息含敏感词: {hit_word}")

        return {
            "high_risk": bool(reasons),
            "reasons": reasons,
            "hit_word": hit_word,
        }

    def update_last_target(self, app_key: str, group_name: str):
        """拦截时调用, 记录本次"尝试发送"的目标, 不论后续确认/取消"""
        self.last_target = {"app_key": app_key, "group_name": group_name or "", "ts": time.time()}

    def reset(self):
        self.last_target = None
