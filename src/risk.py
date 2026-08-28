"""
risk.py - 第二阶段风险检测
三类检测, 任一命中即为高风险 -> 触发二次确认弹窗:
  1. 聊天对象变化: 距上次发送 <= switch_threshold_seconds 且 (app_key 或 group_name) 变化
     - 会话名(group_name)来源: 老版钉钉标题切分; 新版钉钉用会话列表选中项索引指纹(如 "钉钉#0")
     - 飞书(Chromium)/微信(Qt) 会话列表未暴露给 UIA, 群切换检测不到, 只能检测 app 级切换
     - switch_threshold_seconds = 0  -> 任何变化都弹 (默认, 严格)
     - switch_threshold_seconds < 0  -> 关闭该检测
  2. 敏感词: 消息内容命中 sensitive_words (大小写不敏感, 子串匹配)
     - 依赖 UIA 读取输入框内容; 飞书/微信读不到内容, 此检测仅在钉钉上生效
  3. 静默时段: quiet_hours.enabled 且当前时间在 [start, end) 内 (支持跨午夜, 如 22:00~08:00)
     - 与内容无关, 纯时间判断, 所有应用均生效

各检测对不同应用的可用性:
  钉钉(新版,Qt):    1(群级,伪指纹) / 2 / 3
  钉钉(老版):       1(群级,真群名) / 2 / 3
  飞书(Chromium):   1(仅app级) / 3   (2 受 UIA 限制不生效, web内容读不到)
  微信(Qt):          1(仅app级) / 3   (2 受 UIA 限制不生效)

首次发送无基准 -> 低风险放行 (但若命中 2/3 仍弹).
last_target 在拦截时更新 (不论最终确认/取消), 以"尝试发送的对象"为准.
"""
import time
from datetime import datetime
from typing import Optional


class RiskAssessor:
    def __init__(self, switch_threshold_seconds: int = 0, sensitive_words=None, quiet_hours=None):
        self.switch_threshold_seconds = switch_threshold_seconds
        self.sensitive_words = [w for w in (sensitive_words or []) if w]
        self.quiet_hours = quiet_hours or {"enabled": False, "start": "22:00", "end": "08:00"}
        # last_target: {"app_key": str, "group_name": str, "ts": float}
        self.last_target = None

    def update_config(self, switch_threshold_seconds=None, sensitive_words=None, quiet_hours=None):
        if switch_threshold_seconds is not None:
            self.switch_threshold_seconds = switch_threshold_seconds
        if sensitive_words is not None:
            self.sensitive_words = [w for w in sensitive_words if w]
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

    # --- 检测 3: 静默时段 ---
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

        # 3. 静默时段
        if self._in_quiet_hours():
            qh = self.quiet_hours
            reasons.append(f"非工作时间 ({qh['start']}~{qh['end']})")

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
