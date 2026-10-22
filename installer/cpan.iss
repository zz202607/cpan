; Cpan 2.0.0 — per-user installer (no admin required to install).
; Build: ISCC.exe installer\cpan.iss
; The installed app may elevate itself for system-level cleaning.

#define MyAppName "Cpan"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Cpan"
#define MyAppExeName "Cpan.exe"

[Setup]
AppId={{A4E1C9B2-7F3D-4B8A-9C1E-5D2F6A7B8C90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Cpan
DefaultGroupName=Cpan
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=Cpan-Setup-{#MyAppVersion}
SetupIconFile=..\assets\cpan.ico
WizardImageFile=..\assets\wizard-large.bmp
WizardSmallImageFile=..\assets\wizard-small-100.bmp,..\assets\wizard-small-125.bmp,..\assets\wizard-small-150.bmp,..\assets\wizard-small-175.bmp,..\assets\wizard-small-200.bmp,..\assets\wizard-small-225.bmp,..\assets\wizard-small-250.bmp
WizardImageStretch=no
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UsePreviousAppDir=yes
VersionInfoVersion=2.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Cpan - C drive space manager
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Cpan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Cpan\Cpan"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "C 盘空间管家"
Name: "{userprograms}\Cpan\卸载 Cpan"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Cpan"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\README.md"; Description: "查看使用说明"; Flags: shellexec postinstall unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
