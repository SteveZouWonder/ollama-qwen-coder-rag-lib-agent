; Inno Setup 脚本 —— Cerebro Windows 安装器
; 由 GitHub Actions 调用：
;   iscc /DAppVersion=1.0.0 packaging\installer.iss
; 期望 PyInstaller 已在 dist\Cerebro\ 生成 onedir 产物。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Cerebro"
#define AppPublisher "Cerebro Open Source"
#define AppExeName "Cerebro.exe"
#define SourceDir "..\dist\Cerebro"

[Setup]
AppId={{B7E3C8A1-4F2D-4E6B-9C7A-CEREBRO000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Cerebro-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 允许普通用户安装到自己目录，无需强制管理员
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; 简体中文语言文件在 CI 中按需下载到 Inno Setup 的 Languages 目录；
; 若不存在则跳过中文，避免编译失败（降级为纯英文）。
#if FileExists(AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "开机自动启动 Cerebro"; GroupDescription: "启动选项:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} (命令行模式)"; Filename: "{app}\{#AppExeName}"; Parameters: "--cli"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; 开机自启（写入当前用户启动项）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Cerebro"; ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; Description: "立即启动 {#AppName}"; \
  Flags: nowait postinstall skipifsilent
