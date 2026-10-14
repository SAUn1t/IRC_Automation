#ifndef AppVersion
  #error AppVersion must be supplied by the release workflow
#endif

[Setup]
AppId={{47A0C5A2-B55C-42FD-876D-6388F113B18B}
AppName=IR Center Assistant
AppVersion={#AppVersion}
AppPublisher=SAUn1t
AppPublisherURL=https://github.com/SAUn1t/IRC_Automation
DefaultDirName={localappdata}\Programs\IRCenterAssistant
DefaultGroupName=IR Center Assistant
UninstallDisplayIcon={app}\IRCenterAssistant.exe
OutputDir=..\dist-installer
OutputBaseFilename=IRCenterAssistant-Setup
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
WizardStyle=modern

[Files]
Source: "..\dist\IRCenterAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\IR Center Assistant"; Filename: "{app}\IRCenterAssistant.exe"
Name: "{group}\Uninstall IR Center Assistant"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\IRCenterAssistant.exe"; Flags: nowait runasoriginaluser
