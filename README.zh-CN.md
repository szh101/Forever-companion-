# Forever AI · WoW Forever 游戏助手

[English](README.md) | **简体中文**

Forever AI 由一个只读的游戏插件（AddOn）和一个游戏外的聊天助手（Companion）组成。将角色、装备、任务等快照交给 AI，询问装备掉落、配方来源、任务顺序，也可以附上游戏截图。

回复显示在桌面聊天小窗中，**目前不能在游戏聊天频道里直接与 AI 对话**。应用界面目前以中文为主。

当前为开发原型：Companion **0.4.2**，AddOn **0.3.0**。插件 TOC 为 **16001**，面向 WoW: Forever 对应客户端；不保证兼容其他正式服、经典服或测试服版本。

## 下载哪个？

**目前 GitHub 没有已发布的安装包或二进制 Release，也没有一键安装器。现在请下载源码，按下面的步骤安装。**

- 打开[仓库首页](https://github.com/szh101/Forever-companion-)，选择 **Code → Download ZIP**，然后完整解压。
- 只要游戏插件：使用解压目录中的 **`addon/ForeverAI`** 文件夹。
- 需要 AI 聊天：还要按下面的 Windows 或 macOS 步骤启动 **Companion**；插件本身不连接 AI。
- 使用 Git 的用户也可以克隆仓库：

```sh
git clone https://github.com/szh101/Forever-companion-.git
cd Forever-companion-
```

`main` 源码已包含下文介绍的紧凑浮窗，以及截图、滚轮和焦点功能。

未来独立应用会在 [GitHub Releases](https://github.com/szh101/Forever-companion-/releases) 发布。现有打包脚本的文件名规则如下，**这些是将来识别下载文件的说明，并非已上线的下载项**：

| 平台 | 独立应用文件名 | 解压后使用 |
| --- | --- | --- |
| Windows x64 | `ForeverAI-Windows-x64-<commit>.zip` | 保留整个 `Forever AI` 文件夹，运行其中的 `Forever AI.exe`；不能移走或删掉 `_internal`。包内 `addon/ForeverAI` 仍需复制到游戏目录。 |
| macOS 14+ | `ForeverAI-macOS-<architecture>-<commit>.zip` | 选择匹配电脑架构的版本，打开 `Forever AI.app`；插件另从源码的 `addon/ForeverAI` 安装。现有 Mac 打包采用临时签名，未经过 Apple 公证。 |

独立应用包不需要 Python。GitHub 自动生成的 **Source code (zip / tar.gz)** 是源码，不是独立应用。

## 1. 安装游戏插件

1. 找到你实际启动的 **Forever 客户端**目录，再进入 `Interface/AddOns`。不要仅凭 `_retail_`、`_classic_` 或 `_classic_beta_` 文件夹名称判断版本。
2. 将下载源码中的整个 **`addon/ForeverAI`** 文件夹复制进去。更新前可以先将旧插件移到游戏目录外备份。
3. 确认结构如下，不能再多套一层文件夹：

```text
<你的 Forever 客户端>/Interface/AddOns/ForeverAI/
├── ForeverAI.toc
├── ForeverAI.lua
└── Snapshot.lua
```

4. **首次安装**请完全退出并重新启动游戏，在角色选择界面的插件列表中启用 **Forever AI | Snapshot**。已经加载该插件后再更新，通常可由你手动执行 `/reload`。
5. 进入游戏，在非战斗状态输入 **`/fai`**。出现复制面板即表示插件已加载。

启动 Companion 不会自动安装插件。若插件未显示，先核对客户端版本、路径和上述三个文件。

## 2. 启动桌面助手

以下是**当前可以使用的源码安装方式**。首次安装依赖需要联网。

### Windows

1. 安装 [Python 3.11 或更新版本](https://www.python.org/downloads/windows/)，包含 **Tcl/Tk** 和 **Python launcher**。建议使用 x64 版本。
2. 在完整解压的项目文件夹中双击 **`setup-windows.cmd`**，等待依赖安装完成。它会创建项目自己的 `.venv`。
3. 双击 **`start-windows.cmd`** 启动助手。以后直接用这个文件启动，不需要重复安装。

这三步即可使用任务快照和聊天。**源码安装不会自动编译实时窗口截图组件**；需要该功能时，在安装好 .NET Framework 参考程序集和 Windows 元数据后，从项目目录运行：

```powershell
.venv\Scripts\python.exe scripts\build_windows_capture.py
```

构建依赖或组件暂时不可用时，可以继续使用插件快照，或在助手设置中导入 PNG/JPEG 游戏截图。更多构建说明见 [Windows 文档](docs/windows.md)。

### macOS

需要带 **Tcl/Tk** 的 [Python 3.11 或更新版本](https://www.python.org/downloads/macos/)。在终端进入解压后的项目目录，运行：

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
| **离线示例** | 不需要账号，用虚构文字和示意图检查界面，不会调用模型。 |
| **Codex（已登录）** | 自己安装官方 Codex CLI，并用自己的 ChatGPT 账号登录。助手通过该 CLI 使用你的账号额度，不需要在助手里填写 API key。 |
| **OpenAI / Gemini / Claude** | 对应服务商的 API key；选择模型或填写你有权限使用的模型 ID。API 费用和额度由对应服务商计算。 |

**仅安装 Codex 桌面应用，包括 Microsoft Store 版本，不保证官方 CLI 已安装或可供助手调用。** 按 [Codex 官方安装说明](https://learn.chatgpt.com/docs/codex/cli)和[登录说明](https://learn.chatgpt.com/docs/auth)安装并登录 CLI，再使用助手设置里的连接检查。连接检查不发送模型请求。若提示版本不支持隔离参数，更新提示中显示路径对应的 CLI。

密钥只在助手本次运行的内存中保存，退出后需要重新填写。请使用自己的账号或密钥，不要把它们提交到 GitHub。Claude 连接使用 API key，不支持借用 Claude 桌面应用或订阅登录状态。聊天模型和图片模型的可用性取决于你的账号与服务商。

## 4. 开始提问

1. 在游戏中输入 **`/fai`**，面板会准备并选中快照数据。
2. Windows 按 **Ctrl+C**；Mac 按 **Command+C**（或客户端支持的 Ctrl+C）。插件不能自行写入系统剪贴板，所以这一步仍需你按键。
3. 到助手点击 **粘贴 addon** 图标，或将数据直接粘贴进输入框。看到 **导入成功**和任务数量后，再输入问题。
4. 按 **Shift+Enter 发送**，**Enter 换行**。例如：“根据我的任务列表，建议一个少跑路的顺序”“这件装备哪里掉落”“这个配方如何获取”。
5. 角色状态改变后重新导出并粘贴；快照不会实时同步。查询银行、专业配方或 NPC 信息前，先打开相应游戏窗口，再导出。

每次导入替换整份快照。未加载或受限制的数据会标为未知或部分可用；这不是完整的游戏数据库。AI 可使用所选服务的网页搜索查找资料；Gemini 当前连接不启用网页搜索。没有内置完整 Forever 掉落和配方数据库，路线建议也不保证最优。

聊天可显示文字、公开攻略图片和生成的示意图。点击图片可放大，Esc 关闭预览。API 生图需配置 OpenAI 或 Gemini 图片连接，Claude 聊天需另外选择图片服务；附带截图时当前 API 流程不提供生图工具。Codex 使用自身可用的图片工具，不会自动转用另一家付费 API。详见[架构说明](docs/architecture.md)。

## 截图与窗口操作

截图默认关闭。可在设置中选择 PNG/JPEG 文件，或选择本机 WoW 窗口进行预览和按次捕获。Windows 的**截图并粘贴**图标位于粘贴 addon 旁边：点击后截取已选游戏窗口、复制到剪贴板，并附到下一次提问。未选窗口时会检测并选择第一个 WoW 窗口；没找到就不截图。多开时请在设置中自行选定。

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

当前源码通过了 154 项 Windows 自动化检查和隐藏窗口冒烟测试，另有 1 项依平台而定的检查跳过。这些检查没有操作运行中的游戏，也没有发送真实 AI 请求；最新的共享界面改动仍需在 macOS 上验证。

- [架构与接口边界](docs/architecture.md)
- [快照内容和限制](docs/snapshot.md)
- [Windows 使用与打包](docs/windows.md)
- [检查与发布流程](docs/pipeline.md)
- [验证范围](docs/verification.md) · [Windows 验证记录](docs/windows-verification.md)

详细技术文档目前混合使用英文和中文。
