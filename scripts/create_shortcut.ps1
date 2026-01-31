$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath 'Worldbuilding Interactive Program.lnk'

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = 'pythonw.exe'
$Shortcut.Arguments = '-m app.main'
$Shortcut.WorkingDirectory = 'C:\Worldbuilding-Interactive-Program'
$Shortcut.IconLocation = 'C:\Worldbuilding-Interactive-Program\app\resources\icon.ico'
$Shortcut.Description = 'Launch Worldbuilding Interactive Program'
$Shortcut.Save()

Write-Host "Desktop shortcut created at: $ShortcutPath"
