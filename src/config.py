"""
config.py - 全局配置, 支持多应用扩展
"""
import json
import os

# 默认监控的应用列表, 关键词用于匹配窗口标题/类名
# 后续要加飞书/微信, 只需在这里加一项, 或通过GUI动态修改
DEFAULT_APPS = {
    "DingTalk": {
        "display_name": "钉钉",
        "keywords": ["DingTalk", "钉钉"],
        "class_keywords": ["DingTalk", "StandardFrame"],
        "enabled": True,
    },
    "Feishu": {
        "display_name": "飞书",
        "keywords": ["Feishu", "飞书", "Lark"],
        "class_keywords": ["Feishu", "Lark"],
        "enabled": False,
    },
    "WeChat": {
        "display_name": "微信",
        "keywords": ["WeChat", "微信"],
        "class_keywords": ["WeChatMainWndForPC", "mmui"],
        "enabled": False,
    },
}

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")

# 默认敏感词表 (高危/隐私 + 常见脏话), 用户可在 config.json 或 GUI 中增删
# 匹配为子串包含 (大小写不敏感), 词越短误伤越大, 故最短取2字
DEFAULT_SENSITIVE_WORDS = [
    # 隐私/财务
    "工资", "薪水", "薪酬", "收入",
    "密码", "口令", "验证码", "动态码",
    "身份证", "身份证号", "护照",
    "银行卡", "卡号", "账号", "账户",
    "转账", "汇款", "打款", "收款",
    # 常见脏话 (保守收录, 用户可自行扩充)
    "傻逼", "草泥马", "fuck", "shit", "bitch",
]

# 高危群关键词: 群名命中任一则该群每次发送都弹 (不受对象变化逻辑管)
# 用户可自行补充, 如 "客户", "外部", "全员", "领导"
DEFAULT_HIGH_RISK_GROUP_KEYWORDS = ["客户", "外部", "全员", "领导", "大群"]

# 静默时段 (非工作时间): 该时段内一律高风险
DEFAULT_QUIET_HOURS = {"enabled": False, "start": "22:00", "end": "08:00"}


class AppConfig:
    def __init__(self):
        self.master_enabled = True  # 总开关
        self.test_mode = True  # 测试模式: 开启时拦截后不重放Enter, 绝不真发送 (默认开启, 安全)
        # 风险检测配置 (第二阶段)
        # 切换阈值(秒): 距上次发送 <= 该值且聊天对象变化 -> 高风险. 0 = 任何变化都弹, 负数 = 关闭该检测
        self.switch_threshold_seconds = 0
        # 敏感词表: 命中任一即高风险 (大小写不敏感, 子串匹配)
        self.sensitive_words = list(DEFAULT_SENSITIVE_WORDS)
        # 高危群关键词: 群名命中则每次必弹
        self.high_risk_group_keywords = list(DEFAULT_HIGH_RISK_GROUP_KEYWORDS)
        # 静默时段 (非工作时间)
        self.quiet_hours = {
            "enabled": DEFAULT_QUIET_HOURS["enabled"],
            "start": DEFAULT_QUIET_HOURS["start"],
            "end": DEFAULT_QUIET_HOURS["end"],
        }
        self.apps = json.loads(json.dumps(DEFAULT_APPS))  # deep copy
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.master_enabled = data.get("master_enabled", self.master_enabled)
                self.test_mode = data.get("test_mode", self.test_mode)
                self.switch_threshold_seconds = data.get("switch_threshold_seconds", self.switch_threshold_seconds)
                # 敏感词: 优先用用户配置, 否则保留默认
                if "sensitive_words" in data:
                    self.sensitive_words = list(data["sensitive_words"])
                # 高危群
                if "high_risk_group_keywords" in data:
                    self.high_risk_group_keywords = list(data["high_risk_group_keywords"])
                # 静默时段
                qh = data.get("quiet_hours")
                if isinstance(qh, dict):
                    self.quiet_hours = {
                        "enabled": bool(qh.get("enabled", DEFAULT_QUIET_HOURS["enabled"])),
                        "start": qh.get("start", DEFAULT_QUIET_HOURS["start"]),
                        "end": qh.get("end", DEFAULT_QUIET_HOURS["end"]),
                    }
                # 合并 apps, 保留新增的默认值
                loaded_apps = data.get("apps", {})
                for k, v in loaded_apps.items():
                    if k in self.apps:
                        self.apps[k].update(v)
                    else:
                        self.apps[k] = v
            except Exception as e:
                print(f"[config] load failed: {e}, use default")

    def save(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "master_enabled": self.master_enabled,
                        "test_mode": self.test_mode,
                        "switch_threshold_seconds": self.switch_threshold_seconds,
                        "sensitive_words": self.sensitive_words,
                        "high_risk_group_keywords": self.high_risk_group_keywords,
                        "quiet_hours": self.quiet_hours,
                        "apps": self.apps,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            print(f"[config] save failed: {e}")

    def is_app_enabled(self, app_key: str) -> bool:
        return self.apps.get(app_key, {}).get("enabled", False)

    def get_enabled_keywords(self):
        """返回所有已启用应用的关键词列表, 供hook快速判断"""
        kws = []
        for app in self.apps.values():
            if app.get("enabled"):
                kws.extend(app.get("keywords", []))
                kws.extend(app.get("class_keywords", []))
        return kws

    def get_app_by_window(self, title: str, class_name: str):
        """根据窗口标题/类名反查是哪个应用, 未匹配返回None"""
        title_low = (title or "").lower()
        class_low = (class_name or "").lower()
        for key, app in self.apps.items():
            if not app.get("enabled"):
                continue
            for kw in app.get("keywords", []):
                if kw.lower() in title_low:
                    return key, app
            for kw in app.get("class_keywords", []):
                if kw.lower() in class_low:
                    return key, app
        return None, None
