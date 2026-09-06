; Установщик C++ Win32 «Оффлайн Переводчик» (без языковых моделей).
; Соберите lite-папку: powershell -File cpp\package_win32.ps1
; Компиляция: ISCC.exe cpp\OfflineTranslatorCpp.iss
;
; Деинсталлятор удаляет файлы из {app}, включая {app}\data (модели,
; скачанные в каталог программы). Каталог
; %USERPROFILE%\.local\share\offline-translator не трогается.

#define AppName "Оффлайн Переводчик"
#define AppVersion "0.995-beta"
#define AppPublisher "TAP3AH"
#define AppExeName "offline_translator_win32.exe"
#define PortableDir "portable-win32-lite"

[Setup]
AppId={{c4e8a91f-7b2d-4f15-9e3a-6d8c1b0a2475}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Offline Translator C++
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer-output
OutputBaseFilename=offline-translator-cpp-0.995-beta-setup
SetupIconFile=..\assets\app.ico
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=0.995.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName}
VersionInfoProductName={#AppName}
VersionInfoProductVersion=0.995.0.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные значки:"; Flags: unchecked

[Dirs]
Name: "{app}\data"

[Files]
Source: "{#PortableDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

; Только данные внутри каталога установки. Профиль пользователя не удалять.
[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: dirifempty; Name: "{app}"

[Code]
function UserSettingsPath: String;
var
  HomeEnv: String;
begin
  HomeEnv := GetEnv('OFFLINE_TRANSLATOR_HOME');
  if HomeEnv <> '' then
  begin
    Result := AddBackslash(HomeEnv) + 'settings.json';
    if FileExists(Result) then
      Exit;
  end;
  Result := AddBackslash(GetEnv('USERPROFILE')) +
    '.local\share\offline-translator\settings.json';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir, AppSettings, ProfileSettings: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  DataDir := ExpandConstant('{app}\data');
  if not DirExists(DataDir) then
    ForceDirectories(DataDir);
  AppSettings := AddBackslash(DataDir) + 'settings.json';
  ProfileSettings := UserSettingsPath;
  { Перенос settings.json из профиля, если в data его ещё нет. }
  if FileExists(ProfileSettings) and (not FileExists(AppSettings)) then
    CopyFile(ProfileSettings, AppSettings, False);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RunCommand: String;
  AppDir: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  AppDir := ExpandConstant('{app}');
  if RegQueryStringValue(
       HKCU,
       'Software\Microsoft\Windows\CurrentVersion\Run',
       'OfflineTranslator',
       RunCommand) then
  begin
    { Снимаем автозагрузку только если она указывает на этот каталог. }
    if Pos(AnsiLowercase(AppDir), AnsiLowercase(RunCommand)) > 0 then
      RegDeleteValue(
        HKCU,
        'Software\Microsoft\Windows\CurrentVersion\Run',
        'OfflineTranslator');
  end;
end;
