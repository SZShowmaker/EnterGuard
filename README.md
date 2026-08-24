# EnterGuard - 消息发送二次确认

在 Windows 下, 当你在钉钉/飞书/微信中按 `Enter` 发送消息前, 弹出确认框, 防止手滑把消息发错群。

> 安全设计: 默认开启 **测试模式**, 拦截后点"确认"也不会真发送, 可安全验证。

## 功能

- 全局钩子 `WH_KEYBOARD_LL` 拦截 `Enter` (单纯Enter才拦截, `Shift/Ctrl+Alt+Enter` 放行)
- 可视化主窗口: 总开关 / 单应用开关(钉钉/飞书/微信可扩展) / 测试模式开关
- 弹窗预览: 群名(从窗口标题提取) + 输入框内容(尝试UIA读取)
- 未来可扩展: 加白名单、关键词过滤等

## 安装 (Windows)

```bat
# 1. 克隆或拷贝项目到 Windows
cd EnterGuard

# 2. 安装依赖 (需要 Python 3.10+)
pip install -r requirements.txt
# requirements: pywin32, comtypes, uiautomation

# 3. 运行
python src/main.py
```

首次运行建议保持 `测试模式=开启`, 验证:

1. 打开钉钉, 在任意群输入框打字, 按 Enter
2. 应弹出确认框, 显示群名和预览
3. 点取消 -> 消息不应发送; 点确认 -> 测试模式下也不发送 (日志显示"测试模式开启, 不重放")
4. 日志区可看拦截记录

确认无误后, 在主窗口关闭 `测试模式`, 之后点确认才会 `SendInput` 重放 Enter 真发送。

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
  "apps": {
    "DingTalk": {"enabled": true},
    "Feishu": {"enabled": false},
    "WeChat": {"enabled": false}
  }
}
```

要支持新应用, 在 `src/config.py: DEFAULT_APPS` 加一项即可, 无需改钩子逻辑。

## 安全说明

- 本工具不注入钉钉进程, 不 Hook API, 仅用系统级低级钩子, 不会被视作外挂
- 钩子回调中 `return 1` 吞掉按键, 只有用户点确认才会重放一次注入的 Enter (带 `LLKHF_INJECTED` 标记, 不会二次拦截)
- 搜索框误弹: 已知, 按需求接受, 若要优化可在 `src/uia.py` 加焦点类型判断
- 绝不在代码中主动发送测试消息

## 开发 (WSL/Linux)

Linux下 `src/main.py` 可运行但为 mock 模式 (无真实钩子), 仅预览界面。点 `模拟拦截` 可演示弹窗。

```bash
python3 src/main.py
python3 -m src.uia  # 自检 mock
```

## 常见问题

Q: 按 Enter 没反应?
A: 检查总开关/应用开关是否开启, 是否按了 Shift, 前台窗口标题是否含"钉钉"关键词, 用 `Inspect` 确认

Q: 弹窗焦点在取消按钮?
A: 是的, 防手滑, 默认焦点在"取消", 需 Tab 或鼠标点"确认", Enter 默认会触发取消以外的逻辑已绑定但焦点在取消上可防误触

Q: 开机自启?
A: 把 `python src/main.py` 的快捷方式放到 `shell:startup` 目录, 或写注册表 `HKCU\...\Run`
