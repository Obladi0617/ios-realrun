#define MyAppName "iOS RealRun"
#ifndef MyBuildDir
  #define MyBuildDir "dist\iOSRealRun"
#endif
#ifndef MyInstallerDir
  #define MyInstallerDir "dist\installer"
#endif
#define MyAppVersion GetStringFileInfo(MyBuildDir + "\iOSRealRun.exe", "ProductVersion")
#define MyAppPublisher "iOSRealRun"
#define MyAppExeName "iOSRealRun.exe"

[Setup]
AppId={{8DB6C5C5-4F4D-4AA8-AF5A-2EAA4A153C5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir={#MyInstallerDir}
OutputBaseFilename=iOS-RealRun-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
AppMutex=Local\iOSRealRunGui
CloseApplications=no

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\iOS RealRun"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\iOS RealRun"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch iOS RealRun"; Flags: nowait postinstall skipifsilent
