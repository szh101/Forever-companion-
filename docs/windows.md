# Forever AI Windows

这是与 Mac 0.4.2 共用业务逻辑的 Windows x64 版本。主窗口为 320×380 逻辑像素，
按 Windows 显示缩放调整大小；200% 缩放时客户区为 640×760 像素。设置独立打开，
Shift+Enter 发送，Enter 换行，可置顶与收起。截图默认关闭。

主窗采用图标按钮，悬停查看名称；正文与输入为 10 号字体。齿轮打开设置，图钉控制置顶，
箭头收起/展开，剪贴板粘贴 addon，纸飞机发送，叉号关闭助手。左上角拖动图标移动窗口，
右下角斜线图标调整尺寸。不透明度在设置中可调 45–100%，默认 92%，不保存到磁盘。
主窗采用统一的深色与暖金配色，输入时边框高亮；设置为固定标题、可滚动分组卡片，
说明文字随宽度换行。保持 10 号正文与紧凑布局，设置窗口默认 420×620 逻辑像素。

粘贴 addon 右侧新增“截图并粘贴”图标：先截取 WoW 窗口，再复制到
Windows 剪贴板，同时附到下一条提问。按钮不依赖自动截图开关，成功后关闭自动截图；
不弹出预览窗口，不截桌面。已选窗口时保留选择；未选时自动检测并使用检测到的第一个
WoW 窗口，未找到则不截图。多开时可在设置中改选。附件两分钟后需重新截取。
如果系统剪贴板正忙，已捕获图片仍可直接随下一条提问发送。复制的图片保留在系统剪贴板，
Windows 剪贴板历史或同步是否保存它取决于用户系统设置；助手不读取或更改这些设置。

主窗背景和普通正文点击由 Windows 穿透到下方窗口；输入框、按钮、滚动条、图片和链接
保留各自的鼠标区域。悬停聊天正文或其滚动条时，滚轮翻阅历史，不激活助手键盘。
兼容带系统注入标志的鼠标工具事件，并保留自有控件和普通窗口模式的滚轮处理。
只有点击输入框才请求键盘焦点；
发送后或在输入框按 Esc，会尝试返回此前 HWND/PID 仍匹配且可见的窗口。
输入时仅移出鼠标不结束打字；第一次点击此前游戏窗口时，释放助手自身的鼠标捕获和输入焦点，
交还该游戏窗口，保留草稿。点击先核对实际指向的窗口与保存的 HWND/PID；不因悬停切换焦点，
不吞掉或补发游戏点击，也不在用户已切到其他应用后拉回游戏。焦点交接在助手 UI 线程处理。
设置和图片预览仍按普通窗口使用。初始化失败会恢复普通窗口并在状态栏说明。

实现使用永久透明命中主窗及不激活的小型自有窗口，并将自有控件的鼠标事件交给 Tk。
鼠标钩子处理聊天区滚轮、自有控件拖动，以及输入期间回到此前窗口的按下通知；拖动还使用控件自身移动事件，以及按下后
有界的鼠标位置/按钮状态采样，避免完全依赖钩子。普通窗口模式也可使用拖动图标。不安装键盘钩子、不向游戏发送输入，
不读取游戏内容。钩子回调不执行 Tk 操作，事件有界并排队；隐藏测试不启动原生窗口或钩子。
行为依据为 Microsoft 的 [分层窗口命中规则](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features#layered-windows)
和 [不激活鼠标点击](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-mouseactivate)。
点击后的目标校验使用 [WindowFromPoint](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-windowfrompoint)，
焦点交回使用 [SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)。
真实游戏的焦点、穿透、拖动及滚轮尚待用户验证；独占全屏、原始输入或系统限制可能影响表现。

## 使用独立应用

推荐下载 [ForeverAI-Setup-x64.exe](https://github.com/szh101/Forever-companion-/releases/latest/download/ForeverAI-Setup-x64.exe)。
中英文安装向导会安装桌面助手，并可将 AddOn 安装到你选定的 Forever 客户端。
无需安装 Python 或编译截图组件。首次安装插件后，由你自行完整重启游戏使其加载。
更新时，旧插件目录保存在该客户端的 `Interface/ForeverAI-backups`；卸载助手保留插件和备份。

选择便携版 ZIP 时，
保留整个 `Forever AI` 文件夹，双击其中的 `Forever AI.exe`，或使用桌面快捷方式。
无需安装 Python。`_internal` 是应用的一部分，不可只复制单独的 exe。
公开 Windows 安装包目前未经过代码签名，Windows 可能显示未知发布者或信誉提示。
请按 [README](../README.md) 查看下载与使用步骤。

检测到官方 Codex CLI 时默认使用 Codex（已登录）；认证由官方 CLI 管理。
Windows 优先使用 PATH 中的 CLI；找不到时，检查 `%USERPROFILE%\AppData\Local\OpenAI\Codex\bin\*\codex.exe`。
这覆盖 Microsoft Store 版 Codex 已安装 CLI、但桌面启动环境没有对应 PATH 的情况。
查找不写死版本目录，不修改系统 PATH，也不要求为此重复安装或登录；所找到的 CLI 仍需通过
隔离能力与 ChatGPT 登录预检。仅安装桌面应用但尚无 CLI 二进制时，仍会明确提示未找到。
OpenAI、Gemini、Claude 使用 API key，仅在本次进程内存保留。不要向第三方提供登录令牌。
设置中的离线示例只使用虚构任务与程序绘制图片，不发起模型请求。

CLI 检查失败会分别说明启动失败、超时、缺少隔离参数或登录检查失败，并显示实际调用的
CLI 路径。只有帮助命令正常退出且缺少必要参数时，才提示更新 CLI；不会移除隔离参数重试。
最近一次检查失败的诊断位于 `%USERPROFILE%\AppData\Local\ForeverAI\Diagnostics\codex-probe.json`，
仅包含时间、CLI 路径、失败阶段、退出码、缺少参数和输出字节数，不保存原始输出、登录详情、
密钥、提示词、快照或对话。目录不可写时仍显示原来的错误。

游戏内 `/fai` 准备隐藏数据选区，用户按 Ctrl+C 后，在助手点击“粘贴 addon”。
聊天区显示导入成功和任务数后，再提问；任务改变后重新导出。新装 addon 需用户启动
Forever 客户端加载，更新已加载 addon 时由用户方便时 `/reload`。文件复制和模拟测试
都不证明客户端复制功能已通过。不要照抄另一台电脑的游戏安装目录。

addon 0.3.0 的广范围快照与现有 0.4.2 exe 兼容，无需重装桌面应用。
更新插件时必须同时复制 `ForeverAI.toc`、`ForeverAI.lua`、`Snapshot.lua` 三个文件；
银行／专业等资料需要打开对应游戏窗口再导出，具体范围见 [快照说明](snapshot.md)。

应用不会自动截桌面、操作角色、读取游戏内存、执行模型代码或把回复回灌游戏。
密钥和对话不由助手落盘。Codex CLI 的临时图片与自身生成产物遵循主 README 的边界。

窗口预览使用 Windows Graphics Capture，直接绑定所选游戏窗口，取代旧的 GDI 截图。
每次只取一帧后结束，可能短暂显示系统捕获边框；不主动切换、移动或恢复游戏窗口。
窗口最小化、关闭、尺寸变化或捕获超时都会报错，不回退到桌面截图。游戏本身绘制的覆盖层
仍属于游戏画面；HDR 和独占全屏的显示效果尚待实测。

## 开发与打包

使用 Windows x64 Python 3.11（含 Tcl/Tk），在独立项目目录执行：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-windows-build.txt
.venv\Scripts\python.exe scripts\build_windows_capture.py
.venv\Scripts\pythonw.exe scripts\windows_quiet.py --report .runtime\windows-quiet.json
.venv\Scripts\python.exe -X utf8 scripts\build_windows.py --commit FULL_COMMIT_SHA
```

测试后读取 JSON，不能用进程已启动代替通过。Windows 测试补充目录 junction、硬链接、
无终端 CLI 选项、npm shim、临时附件清理和 DPI；Mac 检查与共享发布配置保留。
某些执行沙箱限制 Windows 最终文件路径 API 或创建 junction；此时应记录限制，在正常
Windows 进程运行同一离线测试，不降低路径校验规则。一般符号链接用例仍可能按平台跳过。

打包器从固定 Git 提交导出源码，先跑契约与隐藏 GUI，再生成无终端 exe，最后实际运行
exe 的 `--self-test-report` 检查，产物和清单位于 `dist/windows-<commit>/`。
打包时从同一固定源码编译 `native/WindowsCapture.cs`，将截图组件随 exe 一同打包。
使用本机 .NET Framework 编译器、Framework 引用程序集与 Windows WinMetadata；缺少引用
程序集时构建会停止，不自动安装工具链。无需 C++ 编译器；
源码运行时的组件位于 `.runtime/native/forever-capture-windows.exe`。
自检使用虚构快照、替代剪贴板读取函数，不读取或修改系统剪贴板，不访问游戏或网络。
构建日志在 `.runtime`，都不进 Git。可见 UI、真实模型和实际游戏截图另行记录。

排查用户机器上的 CLI 时，可单独运行以下无窗口预检。它使用实际 exe 中的桥接代码执行
`codex exec --help` 与 `codex login status`，不打开聊天窗口、不发模型请求、不读取认证文件。
这是本机连接检查，不能代替真实模型请求验证，也不属于离线包自检：

```powershell
& '.\Forever AI.exe' --check-codex-report '.\codex-check.json'
```

读取报告的 `passed` 和 `phase`；失败记录不包含 CLI 原始 stdout/stderr。

按 [项目检查与发布](pipeline.md) 提交 review 分支。共享 UI 改动仍需 macOS 回归与
原生编译检查；不能把 Windows 打包成功当作 Mac 验证成功，不删除 Mac 检查。

## 验证范围

当前实现通过 156 项离线检查中的 155 项，1 项通用符号链接用例按平台跳过，隐藏 GUI 通过。
真实游戏截图、滚轮、拖动、穿透和焦点交接，以及客户端 addon 导出仍需单独验证。
Mac 合约检查通过 150 项、跳过 6 项 Windows 专用检查，原生组件编译通过；可见界面和真实截图仍需验收。
详细范围见 [Windows 验证记录](windows-verification.md)，
安装步骤见 [README](../README.md)。这些结果不表示下载者的电脑已经安装或验证。
