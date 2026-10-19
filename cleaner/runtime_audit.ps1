$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$result = @{ complete = $true; processes = @(); references = @(); paths = @(); packages = @(); errors = @() }
function Record-Error($scope) { $result.complete = $false; $result.errors += $scope }
try { $result.processes = @(Get-CimInstance Win32_Process | Select-Object Name,ExecutablePath,CommandLine) } catch { Record-Error 'processes' }
try { $result.packages = @(Get-AppxPackage -Name '*Codex*' | Select-Object Name,InstallLocation) } catch { Record-Error 'packages' }
foreach ($scope in @('Process','User','Machine')) {
    foreach ($path in ([Environment]::GetEnvironmentVariable('Path',$scope) -split ';')) {
        if ($path) { $result.paths += [Environment]::ExpandEnvironmentVariables($path.Trim('"')) }
    }
}
foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
                    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run',
                    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run')) {
    try {
        if (Test-Path -LiteralPath $key) {
            foreach ($property in (Get-ItemProperty -LiteralPath $key).PSObject.Properties) {
                if ($property.Name -notmatch '^PS') { $result.references += @{source='startup registry';value=[string]$property.Value} }
            }
        }
    } catch { Record-Error 'startup registry' }
}
foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths',
                    'HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths',
                    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths')) {
    try {
        if (Test-Path -LiteralPath $key) {
            foreach ($child in Get-ChildItem -LiteralPath $key) {
                $item = Get-ItemProperty -LiteralPath $child.PSPath
                $result.references += @{source='App Paths';value=[string]$item.'(default)'}
                $result.references += @{source='App Paths';value=[string]$item.Path}
            }
        }
    } catch { Record-Error 'App Paths' }
}
try {
    foreach ($task in Get-ScheduledTask) {
        foreach ($action in $task.Actions) {
            foreach ($value in @($action.Execute,$action.Arguments,$action.WorkingDirectory)) {
                if ($value) { $result.references += @{source='scheduled task';value=[string]$value} }
            }
        }
    }
} catch { Record-Error 'scheduled tasks' }
try {
    foreach ($service in Get-CimInstance Win32_Service) { $result.references += @{source='service';value=[string]$service.PathName} }
} catch { Record-Error 'services' }
try {
    $shell = New-Object -ComObject WScript.Shell
    $folders = @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('CommonDesktopDirectory'),
                 [Environment]::GetFolderPath('StartMenu'),[Environment]::GetFolderPath('CommonStartMenu')) | Select-Object -Unique
    foreach ($folder in $folders) {
        if (-not $folder -or -not (Test-Path -LiteralPath $folder)) { continue }
        foreach ($file in Get-ChildItem -LiteralPath $folder -Filter *.lnk -Recurse -File) {
            $link = $shell.CreateShortcut($file.FullName)
            foreach ($value in @($link.TargetPath,$link.Arguments,$link.WorkingDirectory)) {
                if ($value) { $result.references += @{source='shortcut';value=[string]$value} }
            }
        }
    }
} catch { Record-Error 'shortcuts' }
try {
    foreach ($folder in @([Environment]::GetFolderPath('Startup'),[Environment]::GetFolderPath('CommonStartup'))) {
        if (-not $folder -or -not (Test-Path -LiteralPath $folder)) { continue }
        foreach ($file in Get-ChildItem -LiteralPath $folder -File -Recurse) {
            if ($file.Extension -notin @('.cmd','.bat','.ps1','.vbs')) { continue }
            if ($file.Length -gt 2097152) { Record-Error 'startup script'; continue }
            $result.references += @{source='startup script';value=[IO.File]::ReadAllText($file.FullName)}
        }
    }
} catch { Record-Error 'startup scripts' }
$result | ConvertTo-Json -Depth 6 -Compress
