"""
risk.py - 第二阶段风险检测
四类检测, 任一命中即为高风险 -> 触发二次确认弹窗:
  1. 聊天对象变化: 距上次发送 <= switch_threshold_seconds 且 (app_key 或 group_name) 变化
     - 微信 PC 标题恒为 "微信", 群切换检测不到, 只能检测 app 级切换 (已知限制, 接受)
     - switch_threshold_seconds = 0  -> 任何变化都弹 (默认, 严格)
     - switch_threshold_seconds < 0  -> 关闭该检测
  2. 敏感词: 消息内容命中 sensitive_words (大小写不敏感, 子串匹配)
  3. 高危群: 群名命中 high_risk_group_keywords 则每次必弹 (不受对象变化逻辑管)
  4. 静默时段: quiet_hours.enabled 且当前时间在 [start, end) 内 (支持跨午夜, 如 22:00~08:00)

首次发送无基准 -> 低风险放行 (但若命中 2/3/4 仍弹).
last_target 在拦截时更新 (不论最终确认/取消), 以"尝试发送的对象"为准.
"""
import time
from datetime import datetime
from typing import Optional


class RiskAssessor:
    def __init__(self, switch_threshold_seconds: int = 0, sensitive_words=None,
                 high_risk_group_keywords=None, quiet_hours=None):
        self.switch_threshold_seconds = switch_threshold_seconds
        self.sensitive_words = [w for w in (sensitive_words or []) if w]
        self.high_risk_group_keywords = [w for w in (high_risk_group_keywords or []) if w]
        self.quiet_hours = quiet_hours or {"enabled": False, "start": "22:00", "end": "08:00"}
        # last_target: {"app_key": str, "group_name": str, "ts": float}
        self.last_target = None

    def update_config(self, switch_threshold_seconds=None, sensitive_words=None,
                      high_risk_group_keywords=None, quiet_hours=None):
        if switch_threshold_seconds is not None:
            self.switch_threshold_seconds = switch_threshold_seconds
        if sensitive_words is not None:
            self.sensitive_words = [w for w in sensitive_words if w]
        if high_risk_group_keywords is not None:
            self.high_risk_group_keywords = [w for w in high_risk_group_keywords if w]
        if quiet_hours is not None:
            self.quiet_hours = quiet_hours

    # --- 检测 1: 聊天对象变化 ---
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

    # --- 检测 2: 敏感词 ---
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

    # --- 检测 3: 高危群 ---
    def _hit_high_risk_group(self, group_name: str) -> Optional[str]:
        """群名命中高危关键词返回该词, 否则 None. 大小写不敏感, 子串匹配."""
        if not group_name or not self.high_risk_group_keywords:
            return None
        g_low = group_name.lower()
        for w in self.high_risk_group_keywords:
            wl = w.lower()
            if wl and wl in g_low:
                return w
        return None

    # --- 检测 4: 静默时段 ---
    def _in_quiet_hours(self) -> bool:
        """当前本地时间是否在静默时段内. 支持跨午夜 (start > end, 如 22:00~08:00)."""
        qh = self.quiet_hours or {}
        if not qh.get("enabled"):
            return False
        start = qh.get("start")
        end = qh.get("end")
        if not start or not end:
            return False
        try:
            now = datetime.now().strftime("%H:%M")
            if start <= end:
                # 同一天, 如 09:00~18:00
                return start <= now < end
            else:
                # 跨午夜, 如 22:00~08:00 -> now >= 22:00 或 now < 08:00
                return now >= start or now < end
        except Exception:
            return False

    def assess(self, app_key: str, group_name: str, preview: str):
        """
        评估风险. 返回 dict:
          { "high_risk": bool,
            "reasons": [str, ...],     # 命中的原因 (供日志/弹窗展示)
            "hit_word": str|None,      # 命中的敏感词
            "hit_group_kw": str|None } # 命中的高危群关键词
        """
        reasons = []
        hit_word = None
        hit_group_kw = None

        # 1. 聊天对象变化
        if self._within_threshold() and self._target_changed(app_key, group_name):
            reasons.append("检测到聊天对象发生变化")

        # 2. 敏感词
        hit_word = self._hit_sensitive(preview)
        if hit_word:
            reasons.append(f"消息含敏感词: {hit_word}")

        # 3. 高危群 (不受对象变化逻辑管, 每次必弹)
        hit_group_kw = self._hit_high_risk_group(group_name)
        if hit_group_kw:
            reasons.append(f"高危群: 命中关键词 '{hit_group_kw}'")

        # 4. 静默时段
        if self._in_quiet_hours():
            qh = self.quiet_hours
            reasons.append(f"非工作时间 ({qh['start']}~{qh['end']})")

        return {
            "high_risk": bool(reasons),
            "reasons": reasons,
            "hit_word": hit_word,
            "hit_group_kw": hit_group_kw,
        }

    def update_last_target(self, app_key: str, group_name: str):
        """拦截时调用, 记录本次"尝试发送"的目标, 不论后续确认/取消"""
        self.last_target = {"app_key": app_key, "group_name": group_name or "", "ts": time.time()}

    def reset(self):
        self.last_target = None
