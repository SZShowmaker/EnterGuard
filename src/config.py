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


class AppConfig:
    def __init__(self):
        self.master_enabled = True  # 总开关
        self.test_mode = True  # 测试模式: 开启时拦截后不重放Enter, 绝不真发送 (默认开启, 安全)
        self.apps = json.loads(json.dumps(DEFAULT_APPS))  # deep copy
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.master_enabled = data.get("master_enabled", self.master_enabled)
                self.test_mode = data.get("test_mode", self.test_mode)
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
