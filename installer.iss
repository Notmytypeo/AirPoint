; ==============================================================================
; Inno Setup Script for AirPoint
; Creates a professional Windows installer from the PyInstaller dist output
; ==============================================================================

#define MyAppName "AirPoint"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AirPoint"
#define MyAppExeName "AirPoint.exe"
#define MyAppDescription "Gesture-controlled mouse and system controls using hand tracking"

[Setup]
AppId={{A1RP01NT-GEST-CTRL-APP0-000000000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL=https://github.com/airpoint
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=AirPoint_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start AirPoint automatically with Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Bundle the entire PyInstaller output folder
Source: "dist\AirPoint\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--minimized"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
