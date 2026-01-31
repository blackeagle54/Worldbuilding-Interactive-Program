; Inno Setup Script for Worldbuilding Interactive Program
; Build with: iscc installer.iss

; Read version dynamically from the VERSION file so this stays in sync.
; If the preprocessor read fails, fall back to a hardcoded value.
#define VersionFile FileOpen(SourcePath + "\..\VERSION")
#if VersionFile
  #define MyAppVersion Trim(FileRead(VersionFile))
  #expr FileClose(VersionFile)
#else
  ; Fallback -- keep this in sync with the VERSION file when updating.
  #define MyAppVersion "0.3.0"
#endif

#define MyAppName "Worldbuilding Interactive Program"
#define MyAppPublisher "WorldbuildingApp"
#define MyAppExeName "WorldbuildingApp.exe"
#define MyAppURL "https://github.com/blackeagle54/Worldbuilding-Interactive-Program"

[Setup]
AppId={{A7B3C4D5-E6F7-8901-A2B3-C4D5E6F78901}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Per-user install, no admin required
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer_output
OutputBaseFilename=WorldbuildingSetup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
SetupIconFile=..\app\resources\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Include the entire PyInstaller output directory
Source: "..\dist\WorldbuildingApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only remove the application directory; user data in {userappdata}\WorldbuildingApp is preserved
Type: filesandordirs; Name: "{app}\PySide6"
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"

[Code]
// User data is stored in {userappdata}\WorldbuildingApp (not in {app})
// so it survives uninstall/reinstall cycles.
procedure InitializeWizard;
begin
  // Ensure user data directory exists on first run
  if not DirExists(ExpandConstant('{userappdata}\WorldbuildingApp')) then
    CreateDir(ExpandConstant('{userappdata}\WorldbuildingApp'));
end;
