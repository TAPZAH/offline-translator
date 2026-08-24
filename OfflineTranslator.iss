; Установщик Оффлайн Переводчика для Windows 10/11 x64 (без языковых моделей).

#define AppName "Оффлайн Переводчик"
#define AppVersion "0.97-beta"
#define AppPublisher "Gelezyaka"
#define AppExeName "OfflineTranslator.exe"
#define PortableDir "dist\offline-translator-portable-lite"

[Setup]
AppId={{255ec5d1-6b1b-490e-bfb4-5ae7de3e2074}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Offline Translator
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=release
OutputBaseFilename=offline-translator-0.97-beta-setup
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=0.97.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName}
VersionInfoProductName={#AppName}
VersionInfoProductVersion=0.97.0.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные значки:"; Flags: unchecked

[Files]
Source: "{#PortableDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
