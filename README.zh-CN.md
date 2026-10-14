# Forever AI · WoW Forever 游戏助手

[English](README.md) | **简体中文**

Forever AI 由一个只读的游戏插件（AddOn）和一个游戏外的聊天助手（Companion）组成。将角色、装备、任务等快照交给 AI，询问装备掉落、配方来源、任务顺序，也可以附上游戏截图。

回复显示在桌面聊天小窗中，**目前不能在游戏聊天频道里直接与 AI 对话**。桌面界面已统一为英文，AI 仍按你的提问语言回答。

当前为开发原型：Companion **0.4.3**，AddOn **0.3.0**。插件 TOC 为 **16001**，面向 WoW: Forever 对应客户端；不保证兼容其他正式服、经典服或测试服版本。

## 下载哪个？

**Windows 10（2004 及以上）／11 x64：[下载 ForeverAI-Setup-x64.exe](https://github.com/szh101/Forever-companion-/releases/latest/download/ForeverAI-Setup-x64.exe)。** 运行一次安装向导即可安装桌面 Companion 和游戏 AddOn，已经包含 Python 运行环境和截图组件，无需下载源码或编译。

1. 运行 **`ForeverAI-Setup-x64.exe`**，选择简体中文或英文。
2. 保持勾选安装 AddOn，选择**实际游玩的 Forever 客户端目录**，其中应包含 `Wow.exe` 或 `WowClassic.exe`。不要选择 Battle.net 启动器目录；只需要桌面助手也可以跳过 AddOn。
3. 完成后，从开始菜单或桌面快捷方式打开 **Forever AI**。
4. 下次完整启动游戏后，在插件列表启用 **Forever AI | Snapshot**，然后按下文[连接 AI](#3-连接-ai)和[开始提问](#4-开始提问)操作。

仍需使用你自己的模型账号或 API key；安装器不会代你登录或重启游戏。安装包未代码签名，Windows 可能显示未知发布者或信誉提示。

更新 AddOn 时，安装器会将旧插件目录保存在客户端的 `Interface/ForeverAI-backups`。卸载 Companion 会保留游戏插件和这些备份。

其他下载见 [Releases 页面](https://github.com/szh101/Forever-companion-/releases)：

| 下载文件 | 用途 |
| --- | --- |
| **`ForeverAI-Setup-x64.exe`** | 推荐的 Windows 安装包，可同时安装 AddOn。 |
| `ForeverAI-Windows-x64-<commit>.zip` | Windows 便携版；保留整个 `Forever AI` 文件夹，运行 `Forever AI.exe`，包内 AddOn 需要手动安装。 |
| `ForeverAI-AddOn-*.zip` | 仅游戏插件；将 `ForeverAI` 解压到客户端的 `Interface/AddOns`。 |
| `SHA256SUMS.txt` | 下载文件的校验值。 |

**macOS：** 本次 Windows 发布不包含 Mac 安装包，请使用下方的 [macOS 源码步骤](#macos)。GitHub 的 **Code → Download ZIP** 和自动生成的 **Source code (zip / tar.gz)** 用于源码安装和开发。

## 1. 安装游戏插件

**Windows 安装器可以代你完成这一步。** 下列手动步骤适用于便携版、仅插件和源码下载。

1. 找到你实际启动的 **Forever 客户端**目录，再进入 `Interface/AddOns`。不要仅凭 `_retail_`、`_classic_` 或 `_classic_beta_` 文件夹名称判断版本。
2. 将插件 ZIP 中的整个 **`ForeverAI`** 文件夹，或便携版／源码中的 **`addon/ForeverAI`** 复制进去。手动更新前可以先将旧插件移到游戏目录外备份。
3. 确认结构如下，不能再多套一层文件夹：

```text
<你的 Forever 客户端>/Interface/AddOns/ForeverAI/
├── ForeverAI.toc
├── ForeverAI.lua
└── Snapshot.lua
```

4. **首次安装**请完全退出并重新启动游戏，在角色选择界面的插件列表中启用 **Forever AI | Snapshot**。已经加载该插件后再更新，通常可由你手动执行 `/reload`。
5. 进入游戏，在非战斗状态输入 **`/fai`**。出现复制面板即表示插件已加载。

若插件未显示，先核对所选客户端版本、路径和上述三个文件。单独启动 Companion 不会安装插件。

## 2. 启动桌面助手

**使用安装包的用户：** 从快捷方式打开 Forever AI，直接继续[连接 AI](#3-连接-ai)。下面的源码步骤对 Windows 是可选项；macOS 目前仍需使用。首次安装源码依赖需要联网。

### Windows 源码安装（可选）

使用 **Code → Download ZIP** 下载并解压源码，或用 Git 克隆：

```sh
git clone https://github.com/szh101/Forever-companion-.git
cd Forever-companion-
```

1. 安装 [Python 3.11 或更新版本](https://www.python.org/downloads/windows/)，包含 **Tcl/Tk** 和 **Python launcher**。建议使用 x64 版本。
2. 在完整解压的项目文件夹中双击 **`setup-windows.cmd`**，等待依赖安装完成。它会创建项目自己的 `.venv`。
3. 双击 **`start-windows.cmd`** 启动助手。以后直接用这个文件启动，不需要重复安装。

这三步即可使用任务快照和聊天。**源码安装不会自动编译实时窗口截图组件**；需要该功能时，在安装好 .NET Framework 参考程序集和 Windows 元数据后，从项目目录运行：

```powershell
.venv\Scripts\python.exe scripts\build_windows_capture.py
```

构建依赖或组件暂时不可用时，可以继续使用插件快照，或在助手设置中导入 PNG/JPEG 游戏截图。更多构建说明见 [Windows 文档](docs/windows.md)。

### macOS

使用 **Code → Download ZIP** 下载并解压源码。需要带 **Tcl/Tk** 的 [Python 3.11 或更新版本](https://www.python.org/downloads/macos/)。在终端进入解压后的项目目录，运行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m companion.app
```

以后只需运行最后一行。若提示缺少 `_tkinter`，请换用包含 Tcl/Tk 的 Python，再创建虚拟环境。

实时窗口截图需要 **macOS 14+** 和用 Swift 编译的辅助组件。安装 Xcode Command Line Tools 后运行：

```sh
.venv/bin/python scripts/build_native.py
```

已有 `.venv` 和 Swift 工具链时，也可以用 `zsh start-mac.command` 启动，它会在缺少组件时先编译。录屏权限仅在你点击助手中的授权按钮时申请；不使用截图时可跳过组件构建和权限设置。

## 3. 连接 AI

打开助手的**齿轮图标**，选择一种连接方式：

| 连接方式 | 你需要准备什么 |
| --- | --- |
| **Offline demo（离线示例）** | 不需要账号，用虚构文字和示意图检查界面，不会调用模型。 |
| **Codex (signed in)（已登录）** | 自己安装官方 Codex CLI，并用自己的 ChatGPT 账号登录。助手通过该 CLI 使用你的账号额度，不需要在助手里填写 API key。 |
| **OpenAI / Gemini / Claude** | 对应服务商的 API key；选择模型或填写你有权限使用的模型 ID。API 费用和额度由对应服务商计算。 |

**仅安装 Codex 桌面应用，包括 Microsoft Store 版本，不保证官方 CLI 已安装或可供助手调用。** 按 [Codex 官方安装说明](https://learn.chatgpt.com/docs/codex/cli)和[登录说明](https://learn.chatgpt.com/docs/auth)安装并登录 CLI，再使用助手设置里的连接检查。连接检查不发送模型请求。若提示版本不支持隔离参数，更新提示中显示路径对应的 CLI。

密钥只在助手本次运行的内存中保存，退出后需要重新填写。请使用自己的账号或密钥，不要把它们提交到 GitHub。Claude 连接使用 API key，不支持借用 Claude 桌面应用或订阅登录状态。聊天模型和图片模型的可用性取决于你的账号与服务商。

## 4. 开始提问

1. 在游戏中输入 **`/fai`**，面板会准备并选中快照数据。
2. Windows 按 **Ctrl+C**；Mac 按 **Command+C**（或客户端支持的 Ctrl+C）。插件不能自行写入系统剪贴板，所以这一步仍需你按键。
3. 到助手点击 **Paste AddOn snapshot（粘贴插件快照）** 图标，或将数据直接粘贴进输入框。看到 **Import successful（导入成功）**和任务数量后，再输入问题。
4. 按 **Shift+Enter 发送**，**Enter 换行**。例如：“根据我的任务列表，建议一个少跑路的顺序”“这件装备哪里掉落”“这个配方如何获取”。
5. 角色状态改变后重新导出并粘贴；快照不会实时同步。查询银行、专业配方或 NPC 信息前，先打开相应游戏窗口，再导出。

每次导入替换整份快照。未加载或受限制的数据会标为未知或部分可用；这不是完整的游戏数据库。AI 可使用所选服务的网页搜索查找资料；Gemini 当前连接不启用网页搜索。没有内置完整 Forever 掉落和配方数据库，路线建议也不保证最优。

聊天可显示文字、公开攻略图片和生成的示意图。点击图片可放大，Esc 关闭预览。API 生图需配置 OpenAI 或 Gemini 图片连接，Claude 聊天需另外选择图片服务；附带截图时当前 API 流程不提供生图工具。Codex 使用自身可用的图片工具，不会自动转用另一家付费 API。详见[架构说明](docs/architecture.md)。

## 截图与窗口操作

截图默认关闭。可在设置中选择 PNG/JPEG 文件，或选择本机 WoW 窗口进行预览和按次捕获。Windows 和 macOS 的 **Capture & paste（截图并粘贴）**图标位于粘贴 addon 旁边：点击后截取已选游戏窗口、复制到剪贴板，并附到下一次提问。未选窗口时会检测并选择第一个 WoW 窗口；没找到就不截图。多开时请在设置中自行选定。

成功后会关闭“每次发送前截图”，附件两分钟后需要重新获取。剪贴板忙时截图仍可作为附件使用。捕获失败不会改截整个桌面。

当前源码提供紧凑小窗、图标按钮、收起/展开和置顶。设置可调整主窗不透明度（45–100%，本次运行有效）。Windows 可拖动左上角图标移动窗口，拖动右下角图标调整大小；聊天区域支持滚轮，背景点击穿透。

点击输入框进入打字，鼠标移出时仍可继续输入；点击此前的游戏窗口时结束输入并保留未发送文字。发送或在输入框按 Esc 也会尝试将焦点交回此前的窗口。设置和图片预览使用普通窗口。不同客户端和显示环境下的实际交互仍需验证，自动化测试不能代替游戏内验收。

## 数据与游戏边界

- AddOn 通过允许访问的游戏 UI API 读取资料，由你主动导出快照；不读取游戏内存、不自动操作角色，不收集私聊、邮件正文或好友/公会名册。他人装备仅使用你主动观察后已公开的数据。
- 普通 AddOn 不能直接发送 HTTP 请求、启动本地程序或连接 MCP。联网和 AI 请求由游戏外 Companion 完成，当前不向游戏聊天回写回复。
- 发送问题时，所选模型服务会收到问题、已导入的快照以及你附上的图片；请求仅重放最近四轮文字。截图可能包含画面中的角色名或聊天内容，请自行选择要发送的画面。
- 助手不持久保存密钥、对话或下载配图。普通 API 图片留在内存；**Codex 附图**会短暂写入每次请求的专用临时目录，正常结束、失败或超时后清理，强制终止可能留下临时文件。你主动复制到系统剪贴板的截图由系统管理。
- Codex 自身可能保留它生成的图片；助手只读取本次调用的新图片，不查看其他会话、认证文件或登录令牌。账号及服务端数据保留规则由提供商管理。
- 公开攻略配图下载不携带 API key、cookie 或登录信息，仅接受受大小、像素和地址限制的 HTTPS 图片。AI 输出不会作为代码或游戏命令执行。

本项目未取得暴雪批准或合规认证。快照字段、可用条件与读取限制见 [快照文档](docs/snapshot.md)。

## 开发与文档

开发检查使用锁定依赖：

```sh
uv sync --locked --group dev
uv run --locked --group dev python scripts/check.py
uv run --locked python scripts/gui_smoke.py
```

独立应用从固定 Git 提交构建：Windows 使用 `scripts/build_windows.py`，Mac 使用 `scripts/build_macos.py`，均需 `--commit FULL_COMMIT_SHA` 和对应平台工具链。构建产物与运行数据不提交 Git。

0.4.3 源码 [`c6ada6424c2f`](https://github.com/szh101/Forever-companion-/commit/c6ada6424c2f73cbca1adb9503f4dbfabaec8fa1) 在 Windows 的 161 项检查中通过 160 项，跳过 1 项平台相关检查；在 macOS 的 161 项检查中通过 155 项，跳过 6 项 Windows 专用检查。两平台的隐藏界面检查均通过，Windows 应用入口自检、macOS 原生组件编译与私有粘贴板检查也通过。详见[源码检查记录](https://github.com/szh101/Forever-companion-/actions/runs/38533867098)。

打包应用与安装器的检查结果单独记载于[验证记录](docs/verification.md)。安装与升级检查使用虚构游戏目录；这些检查不涉及运行中的游戏、真实 AI 请求或 macOS 可见界面验收。

- [架构与接口边界](docs/architecture.md)
- [快照内容和限制](docs/snapshot.md)
- [Windows 使用与打包](docs/windows.md)
- [检查与发布流程](docs/pipeline.md)
- [验证范围](docs/verification.md) · [Windows 验证记录](docs/windows-verification.md)

详细技术文档目前混合使用英文和中文。
