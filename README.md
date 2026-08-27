# EnterGuard - 消息发送二次确认

在 Windows 下, 当你在钉钉/飞书/微信中按 `Enter` 发送消息前, 弹出确认框, 防止手滑把消息发错群。

> 安全设计: 默认开启 **测试模式**, 拦截后点"确认"也不会真发送, 可安全验证。

## 功能

- 全局钩子 `WH_KEYBOARD_LL` 拦截 `Enter` (单纯Enter才拦截, `Shift/Ctrl+Alt+Enter` 放行)
- 可视化主窗口: 总开关 / 单应用开关(钉钉/飞书/微信可扩展) / 测试模式开关
- 弹窗预览: 群名(从窗口标题提取) + 输入框内容(尝试UIA读取)
- **第二阶段: 风险检测**, 高风险才弹窗, 低风险静默放行
  - 聊天对象变化检测: 切换群/应用且在阈值窗口内 -> 高风险 (默认阈值0=任何变化都弹, 可配置)
  - 敏感词检测: 消息含敏感词(工资/密码/身份证/脏话等) -> 高风险 (词表可在GUI编辑)
  - 首次发送默认放行(无基准), 但命中敏感词仍弹
  - 已知限制: 微信PC标题恒为"微信", 群切换检测不到, 只能检测app级切换
- 未来可扩展: 加白名单等

## 安装 (Windows)

```bat
# 1. 克隆或拷贝项目到 Windows
cd EnterGuard

# 2. 安装依赖 (需要 Python 3.9+)
pip install -r requirements.txt
# requirements: pywin32, comtypes, uiautomation

# 3. 运行
python src/main.py
```

首次运行建议保持 `测试模式=开启`, 验证:

1. 打开钉钉, 在任意群输入框打字, 按 Enter
2. 同一群连续发: 低风险, 静默放行 (测试模式下不会真发, 日志显示"低风险放行")
3. 切到另一个群/应用后按 Enter: 高风险, 弹出确认框, 顶部红色显示触发原因
4. 点取消 -> 消息不发送; 点确认 -> 测试模式下也不发送 (日志显示"测试模式开启, 不重放")
5. 日志区可看每次拦截的风险判断结果

确认无误后, 在主窗口关闭 `测试模式`, 之后:
- 低风险消息: 自动重放 Enter 真发送 (无弹窗, 不影响正常聊天)
- 高风险消息: 仍弹窗, 点"确认发送"才会重放 Enter 真发送

## 自检

主窗口点 `自检 UIA` -> 5秒内把焦点切到钉钉输入框 -> 日志会显示能否读到内容

若预览为空: 说明钉钉新版为自绘, UIA读不到 `Value`, 但拦截和群名显示仍正常, 不影响防误发。

也可用 `Inspect.exe` (Windows SDK) 查看控件树:
- 按 `Ctrl` 冻结, 看焦点Edit的 `Value` 属性

`Spy++` 查看窗口类名是否为 `StandardFrame_DingTalk` 等, 用于调整 `src/config.py` 关键词

## 配置文件

`config.json` 自动生成:

```json
{
  "master_enabled": true,
  "test_mode": true,
  "switch_threshold_seconds": 0,
  "sensitive_words": ["工资", "薪水", "密码", "身份证", "银行卡", "验证码", "转账", "fuck", ...],
  "apps": {
    "DingTalk": {"enabled": true},
    "Feishu": {"enabled": false},
    "WeChat": {"enabled": false}
  }
}
```

- `switch_threshold_seconds`: 切换阈值(秒). `0`=任何变化都弹, 负数=关闭对象变化检测, 正数=N秒内切换才弹. 可在主窗口"风险检测"区改.
- `sensitive_words`: 敏感词表, 大小写不敏感, 子串匹配. 可点主窗口"编辑敏感词"增删.

要支持新应用, 在 `src/config.py: DEFAULT_APPS` 加一项即可, 无需改钩子逻辑。

## 风险检测 (第二阶段)

拦截 Enter 后, 主线程会先做风险判断, 低风险静默放行, 高风险才弹窗。两类检测任一命中即视为高风险:

| 检测 | 触发条件 | 配置项 |
|------|----------|--------|
| 聊天对象变化 | 距上次发送 ≤ `switch_threshold_seconds` 且 `app_key` 或 `group_name` 变化 | `switch_threshold_seconds` |
| 敏感词 | 消息内容命中 `sensitive_words` (大小写不敏感, 子串匹配) | `sensitive_words` |

**阈值含义**:
- `0` (默认, 严格): 任何聊天对象变化都弹
- 正数 `N`: 仅 N 秒内切换才弹 (停留久了再换视为有意为之, 不弹)
- 负数: 关闭对象变化检测, 仅靠敏感词

**基准更新时机**: 拦截时立即更新 `last_target` (不论后续确认/取消), 以"尝试发送的对象"为准。这样即使取消发送, 下次在同一对象发送也会被正确识别为"未变化"而不弹。

**首次发送**: 无基准, 默认低风险放行; 但若命中敏感词仍弹。

**已知限制**: 微信 PC 版窗口标题恒为"微信", 群/联系人切换检测不到, 只能检测 app 级切换 (如 钉钉↔微信)。钉钉/飞书标题格式为 `群名 - 钉钉`, 可正常检测群切换。

## 项目结构

```
src/
  main.py        可视化主窗口 (Tkinter): 总开关/应用开关/测试模式/风险检测配置/日志
  config.py      配置读写 (config.json), 默认应用列表, 默认敏感词表
  hook.py        WH_KEYBOARD_LL 低级键盘钩子, SendInput 重放 Enter
  hook_fallback.py 基于 keyboard 库的备用钩子 (ctypes 钩子失败时诊断用)
  uia.py         UI Automation 读取群名和输入框内容预览
  dialog.py      二次确认弹窗 (Toplevel, 模态, 强制前台)
  risk.py        风险检测: 聊天对象变化 + 敏感词 (纯逻辑, 可单元测试)
  diagnose.py    Windows 上一键诊断钩子问题
tests/
  test_safe.py   安全自检 (跨平台, 绝不真发消息)
  test_risk.py   风险检测单元测试 (9 个用例)
```

## 安全说明

- 本工具不注入钉钉进程, 不 Hook API, 仅用系统级低级钩子, 不会被视作外挂
- 钩子回调中 `return 1` 吞掉按键, 只有用户点确认才会重放一次注入的 Enter (带 `LLKHF_INJECTED` 标记, 不会二次拦截)
- 搜索框误弹: 已知, 按需求接受, 若要优化可在 `src/uia.py` 加焦点类型判断
- 绝不在代码中主动发送测试消息

## 开发 (WSL/Linux)

Linux下 `src/main.py` 可运行但为 mock 模式 (无真实钩子), 仅预览界面。点 `模拟拦截` 可演示弹窗。

```bash
python3 src/main.py
python3 -m src.uia          # 自检 mock
python3 tests/test_safe.py  # 安全自检 (跨平台)
python3 tests/test_risk.py  # 风险检测单元测试 (纯逻辑, 跨平台)
```

## 常见问题

Q: 按 Enter 没反应?
A: 检查总开关/应用开关是否开启, 是否按了 Shift, 前台窗口标题是否含目标应用关键词, 用 `Inspect` 确认

Q: 同一个群连续发消息怎么不弹窗了?
A: 这是第二阶段设计 — 聊天对象未变且无敏感词, 判为低风险, 静默放行 (日志显示"低风险放行"). 想每次都弹可把阈值改大, 或在敏感词里加目标内容

Q: 切群/切应用后按 Enter, 消息直接发出去了还弹了窗?
A: 已修复. 原因是钩子吞 Enter 后到弹窗真正抢到焦点之间有几百 ms 窗口, 此期间 Enter 自动重复被放行到仍持焦点的原应用. 现钩子在弹窗期间对 Enter 增加前台校验: 前台非弹窗则吞掉, 不再误发

Q: 弹窗按 Enter / Esc 没反应, 要用鼠标?
A: 弹窗已强制前台并绑定 Enter=确认 / Esc=取消, 焦点默认在"确认发送"按钮. 若仍无反应, 可能是某些安全软件拦截了 SetForegroundWindow, 用鼠标点一次按钮即可

Q: 开机自启?
A: 把 `python src/main.py` 的快捷方式放到 `shell:startup` 目录, 或写注册表 `HKCU\...\Run`

Q: Python 版本要求?
A: 3.9+. 注: 不要在类型注解里用 `str | None` 语法 (需 3.10+), 用 `Optional[str]` 兼容 3.9
