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
  #define AppVersion "0.12.0"
#endif

[Setup]
AppId={{D675D294-D145-4198-8922-8952E87FD305}
AppName=OY Player
AppVersion={#AppVersion}
AppVerName=OY Player {#AppVersion}
AppPublisher=Oleksandr Kyrychenko
AppPublisherURL=https://electronic-mars.github.io/
AppSupportURL=https://github.com/electronic-mars/OY/issues
AppUpdatesURL=https://github.com/electronic-mars/OY/releases
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
; a running player is closed for the update (a polite request is not enough for a tray app).
; No AppMutex: a silent setup answers its "close the program" question with Cancel and installs
; nothing, before the player that started it has finished quitting.
CloseApplications=force
; the player is started again by the [Run] line below, and only on the update path
RestartApplications=no
; Qt 6.12 runs on Windows 10 1809 and newer: on older Windows setup says so instead of
; installing a program that will not start
MinVersion=10.0.17763
; the language page only when Windows speaks none of the languages below (then the first one
; listed, English)
ShowLanguageDialog=auto
Uninstallable=not IsPortable
CreateUninstallRegKey=not IsPortable
; the shell is told at the end, so files the player was offered for show the new exe's icon
; at once and not the one Explorer cached from the old exe at the same path
ChangesAssociations=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"
; the translations Inno Setup ships for the player's other languages
Name: "ar"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "bg"; MessagesFile: "compiler:Languages\Bulgarian.isl"
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"
Name: "da"; MessagesFile: "compiler:Languages\Danish.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fi"; MessagesFile: "compiler:Languages\Finnish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "he"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "hu"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "ko"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "nb"; MessagesFile: "compiler:Languages\Norwegian.isl"
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "pl"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "pt_BR"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "pt_PT"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "sk"; MessagesFile: "compiler:Languages\Slovak.isl"
Name: "sl"; MessagesFile: "compiler:Languages\Slovenian.isl"
Name: "sv"; MessagesFile: "compiler:Languages\Swedish.isl"
Name: "th"; MessagesFile: "compiler:Languages\Thai.isl"
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

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
; The player updating itself runs this setup silently and quits so its files can be replaced;
; silent skips the line above, and without this one the update would end with the player gone.
; /RELAUNCH=1 is passed only by the player (update.py), so an administrator's silent install
; still starts nothing.
Filename: "{app}\OYPlayer.exe"; Flags: nowait; Check: StartedByThePlayer

[UninstallRun]
; the file types, if the person registered them in the settings
Filename: "{app}\OYPlayer.exe"; Parameters: "--unregister"; RunOnceId: "Unregister"; Flags: runhidden waituntilterminated skipifdoesntexist

[Code]
function IsPortable: Boolean;
begin
  Result := ExpandConstant('{param:PORTABLE|0}') = '1';
end;

function StartedByThePlayer: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
