; Build only with scripts/build_windows_installer.py from a fixed source commit.
#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef ChineseMessagesFile
  #error ChineseMessagesFile is required
#endif

[Setup]
AppId={{4F771654-D939-49BE-B03B-D459CAAEBCED}
AppName=Forever AI
AppVersion={#AppVersion}
AppPublisher=Forever AI contributors
AppPublisherURL=https://github.com/szh101/Forever-companion-
DefaultDirName={localappdata}\Programs\Forever AI
DefaultGroupName=Forever AI
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
WizardStyle=modern
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir={#OutputDir}
OutputBaseFilename=ForeverAI-Setup-x64
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\Forever AI.exe
CloseApplications=no
RestartApplications=no
RestartIfNeededByRun=no
AlwaysRestart=no
SetupLogging=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zhCN"; MessagesFile: "{#ChineseMessagesFile}"

[CustomMessages]
en.DesktopShortcut=Create a desktop shortcut
zhCN.DesktopShortcut=创建桌面快捷方式
en.Launch=Open Forever AI
zhCN.Launch=打开 Forever AI
en.AddonTitle=Game AddOn
zhCN.AddonTitle=游戏插件
en.AddonDescription=Install the Companion and optionally the game AddOn.
zhCN.AddonDescription=安装桌面助手，并可同时安装游戏插件。
en.AddonChoice=Install the Forever AI AddOn into my game client
zhCN.AddonChoice=同时为游戏客户端安装 Forever AI 插件
en.AddonHint=The Companion works without Python. An AI account or API key is configured after installation. The game is never started or closed by Setup.
zhCN.AddonHint=桌面助手无需安装 Python。安装后可配置自己的 AI 账号或 API Key。安装程序不会启动或关闭游戏。
en.GameTitle=Choose your Forever client
zhCN.GameTitle=选择 Forever 游戏客户端
en.GameDescription=Select the client folder you actually launch.
zhCN.GameDescription=请选择你实际启动的游戏客户端文件夹。
en.GameHint=Choose the folder containing Wow*.exe, not Interface\AddOns. Setup creates Interface\AddOns if needed. Existing ForeverAI files are preserved in Interface\ForeverAI-backups. Other AddOns are left alone.
zhCN.GameHint=选择包含 Wow*.exe 的文件夹，不要选择 Interface\AddOns。安装程序会按需创建 Interface\AddOns。已有 ForeverAI 插件会备份到 Interface\ForeverAI-backups，其他插件不会改动。
en.GameLabel=Game client folder:
zhCN.GameLabel=游戏客户端文件夹：
en.InvalidGame=Choose an existing local client folder containing Wow*.exe. The Interface path must be a folder or not exist yet. Linked folders and network paths are not supported. You can go Back and skip the AddOn.
zhCN.InvalidGame=请选择包含 Wow*.exe 的本地游戏目录。Interface 路径必须是文件夹或尚未创建。不支持链接文件夹或网络路径。也可返回上一步并取消安装游戏插件。
en.AddonFailed=The AddOn could not be installed. Check write access to the selected client folder. Existing files are preserved; if a backup was made, it is under Interface\ForeverAI-backups. You can install the AddOn manually from the Companion's addon\ForeverAI folder.
zhCN.AddonFailed=游戏插件安装失败。请检查所选客户端目录的写入权限。原有文件会保留；如已创建备份，可在 Interface\ForeverAI-backups 中找到。也可将桌面助手目录中的 addon\ForeverAI 手动安装到游戏中。
en.FinishHint=Open Forever AI from the Start menu or desktop shortcut. Choose your own AI connection in Settings. For a first AddOn installation, restart the game yourself and enable Forever AI | Snapshot; then type /fai. Uninstalling the Companion keeps your game AddOn and its backups.
zhCN.FinishHint=通过开始菜单或桌面快捷方式打开 Forever AI，在设置中配置自己的 AI 连接。首次安装游戏插件后，请自行重启游戏，启用 Forever AI | Snapshot，并输入 /fai。卸载桌面助手会保留游戏插件及其备份。

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Forever AI"; Filename: "{app}\Forever AI.exe"
Name: "{autodesktop}\Forever AI"; Filename: "{app}\Forever AI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Forever AI.exe"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent unchecked

[Code]
var
  AddonPage: TInputOptionWizardPage;
  GamePage: TInputDirWizardPage;

function GetFileAttributesW(lpFileName: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';

{ Reject reparse points in every existing parent, including a junction above the
  selected client. Never follow links when copying or backing up the AddOn. }
function SafeDirectoryPath(Path: String): Boolean;
var
  Parent: String;
  Attributes: LongWord;
begin
  Result := False;
  if (Length(Path) < 3) or (Copy(Path, 2, 2) <> ':\') then Exit;
  Path := RemoveBackslashUnlessRoot(ExpandFileName(Path));
  while Length(Path) >= 3 do begin
    Attributes := GetFileAttributesW(Path);
    if Attributes <> $FFFFFFFF then begin
      if (Attributes and $400) <> 0 then Exit;
      if (Attributes and $10) = 0 then Exit;
    end;
    Parent := ExtractFileDir(Path);
    if Parent = Path then Break;
    Path := Parent;
  end;
  Result := True;
end;

function ValidGameFolder(Path: String): Boolean;
var
  Found: TFindRec;
  HasExe: Boolean;
begin
  Result := False;
  if not SafeDirectoryPath(Path) then Exit;
  Path := RemoveBackslashUnlessRoot(ExpandFileName(Path));
  if not DirExists(Path) then Exit;
  if not SafeDirectoryPath(Path + '\Interface\AddOns\ForeverAI') then Exit;
  if not SafeDirectoryPath(Path + '\Interface\ForeverAI-backups') then Exit;
  HasExe := False;
  if FindFirst(Path + '\Wow*.exe', Found) then begin
    try
      repeat
        if (Found.Attributes and ($10 or $400)) = 0 then HasExe := True;
      until not FindNext(Found);
    finally
      FindClose(Found);
    end;
  end;
  Result := HasExe;
end;

procedure InitializeWizard;
begin
  AddonPage := CreateInputOptionPage(wpSelectDir, CustomMessage('AddonTitle'),
    CustomMessage('AddonDescription'), CustomMessage('AddonHint'), False, False);
  AddonPage.Add(CustomMessage('AddonChoice'));
  AddonPage.Values[0] := CompareText(ExpandConstant('{param:INSTALLADDON|yes}'), 'no') <> 0;
  GamePage := CreateInputDirPage(AddonPage.ID, CustomMessage('GameTitle'),
    CustomMessage('GameDescription'), CustomMessage('GameHint'), False, '');
  GamePage.Add(CustomMessage('GameLabel'));
  GamePage.Values[0] := ExpandConstant('{param:GAMECLIENT|}');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
    WizardForm.FinishedLabel.Caption := CustomMessage('FinishHint');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = GamePage.ID) and not AddonPage.Values[0];
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  { Silent setup also simulates Next. Do not show a custom modal or stop on a
    hidden page: PrepareToInstall performs the same validation and returns the
    standard noninteractive failure exit code under /SUPPRESSMSGBOXES. }
  if WizardSilent then Exit;
  if (CurPageID = GamePage.ID) and AddonPage.Values[0] then begin
    Result := ValidGameFolder(GamePage.Values[0]);
    if not Result then MsgBox(CustomMessage('InvalidGame'), mbError, MB_OK);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if AddonPage.Values[0] and not ValidGameFolder(GamePage.Values[0]) then
    Result := CustomMessage('InvalidGame');
end;

function UniqueDirectory(Parent, Prefix: String): String;
var
  Index: Integer;
begin
  Index := 0;
  repeat
    Result := Parent + '\' + Prefix + GetDateTimeString('yyyymmdd-hhnnss', #0, #0) + '-' + IntToStr(Index);
    Index := Index + 1;
  until GetFileAttributesW(Result) = $FFFFFFFF;
end;

procedure InstallAddon;
var
  Client, InterfaceDir, Target, Stage, Backups, Backup: String;
  Copied, HadPrevious: Boolean;
begin
  if not ValidGameFolder(GamePage.Values[0]) then RaiseException(CustomMessage('InvalidGame'));
  Client := RemoveBackslashUnlessRoot(ExpandFileName(GamePage.Values[0]));
  InterfaceDir := Client + '\Interface';
  Target := InterfaceDir + '\AddOns\ForeverAI';
  Backups := InterfaceDir + '\ForeverAI-backups';
  if not ForceDirectories(InterfaceDir) or not SafeDirectoryPath(InterfaceDir) then
    RaiseException(CustomMessage('AddonFailed'));
  Stage := UniqueDirectory(InterfaceDir, 'ForeverAI-install-');
  Backup := '';
  if not ForceDirectories(Stage) or not SafeDirectoryPath(Stage) then
    RaiseException(CustomMessage('AddonFailed'));
  Copied := CopyFile(ExpandConstant('{app}\addon\ForeverAI\ForeverAI.toc'), Stage + '\ForeverAI.toc', True);
  Copied := CopyFile(ExpandConstant('{app}\addon\ForeverAI\ForeverAI.lua'), Stage + '\ForeverAI.lua', True) and Copied;
  Copied := CopyFile(ExpandConstant('{app}\addon\ForeverAI\Snapshot.lua'), Stage + '\Snapshot.lua', True) and Copied;
  try
    if not Copied then RaiseException(CustomMessage('AddonFailed'));
    if not ForceDirectories(InterfaceDir + '\AddOns') then RaiseException(CustomMessage('AddonFailed'));
    if not SafeDirectoryPath(Target) or not SafeDirectoryPath(Backups) then
      RaiseException(CustomMessage('AddonFailed'));
    HadPrevious := DirExists(Target);
    if HadPrevious then begin
      if not ForceDirectories(Backups) then RaiseException(CustomMessage('AddonFailed'));
      Backup := UniqueDirectory(Backups, 'ForeverAI-');
      if not RenameFile(Target, Backup) then RaiseException(CustomMessage('AddonFailed'));
    end;
    if not RenameFile(Stage, Target) then begin
      if HadPrevious then RenameFile(Backup, Target);
      RaiseException(CustomMessage('AddonFailed'));
    end;
  finally
    { Delete only our three staged files; never recursively delete game content. }
    if DirExists(Stage) and SafeDirectoryPath(Stage) then begin
      DeleteFile(Stage + '\ForeverAI.toc');
      DeleteFile(Stage + '\ForeverAI.lua');
      DeleteFile(Stage + '\Snapshot.lua');
      RemoveDir(Stage);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and AddonPage.Values[0] then InstallAddon;
end;
