; OY Player installer (Inno Setup 6). Built by tools\build.cmd after PyInstaller.
;
; Per user, without administrator rights: %LOCALAPPDATA%\Programs\OY Player. An administrator
; install would start the player elevated after setup, and an elevated program takes no part
; in drag and drop. File types are not touched here: the player offers itself to Windows only
; when the person asks in its settings; the uninstaller takes back whatever it wrote then.
;
; /PORTABLE=1 (checks only): copy the files, nothing else: no uninstaller, no entry in
; Installed apps, no shortcuts, no registry.

#ifndef AppVersion
  #define AppVersion "0.10.0"
#endif

[Setup]
AppId={{D675D294-D145-4198-8922-8952E87FD305}
AppName=OY Player
AppVersion={#AppVersion}
AppVerName=OY Player {#AppVersion}
AppPublisher=Oleksandr Kyrychenko
DefaultDirName={autopf}\OY Player
DefaultGroupName=OY Player
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=OYPlayer-{#AppVersion}-setup
SetupIconFile=..\src\oyplayer\oyplayer.ico
UninstallDisplayIcon={app}\OYPlayer.exe
UninstallDisplayName=OY Player
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; a running player is closed for the update (a polite request is not enough for a tray app)
CloseApplications=force
; Qt 6.12 runs on Windows 10 1809 and newer: on older Windows setup says so instead of
; installing a program that will not start
MinVersion=10.0.17763
; the language page only when Windows speaks neither Ukrainian nor English (then the first
; one listed, English)
ShowLanguageDialog=auto
Uninstallable=not IsPortable
CreateUninstallRegKey=not IsPortable

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; An update replaces the program's own folder whole: files a new version no longer has (an
; older Qt's plugins and QML) must not stay beside it and be loaded. The person's data is in
; %LOCALAPPDATA%\OYPlayer, not here.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\OYPlayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\OY Player"; Filename: "{app}\OYPlayer.exe"; Check: not IsPortable
Name: "{autodesktop}\OY Player"; Filename: "{app}\OYPlayer.exe"; Tasks: desktopicon; Check: not IsPortable

[Run]
Filename: "{app}\OYPlayer.exe"; Description: "{cm:LaunchProgram,OY Player}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; the file types, if the person registered them in the settings
Filename: "{app}\OYPlayer.exe"; Parameters: "--unregister"; RunOnceId: "Unregister"; Flags: runhidden waituntilterminated skipifdoesntexist

[Code]
function IsPortable: Boolean;
begin
  Result := ExpandConstant('{param:PORTABLE|0}') = '1';
end;
