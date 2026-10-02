# Build "DINO Autofocus.exe" with the .NET Framework compiler in Windows (no SDK needed).
#   powershell -ExecutionPolicy Bypass -File tools\launcher\build.ps1 [-Port 8765] [-Out path] [-Force]
# The repo path compiled into the exe is the clone this script runs from. The default output
# is the Desktop; an existing exe there is replaced only with -Force. See docs\runbooks\launcher.md.
param(
    [int]$Port = 8765,
    [string]$Out = (Join-Path ([Environment]::GetFolderPath("Desktop")) "DINO Autofocus.exe"),
    [switch]$Force
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here "..\..")).Path
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$ico = Join-Path $here "autofocus.ico"
# absolute (csc resolves relative paths against the process directory) and with its folder present
$Out = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Out)
$outDir = Split-Path -Parent $Out
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Force $outDir | Out-Null }
if (Test-Path $Out) {
    $old = Get-Item $Out
    if (-not $Force) {
        Write-Output "exists: $Out ($($old.Length) bytes, $($old.LastWriteTime)); add -Force to replace it"
        exit 1
    }
    Write-Output "replacing: $Out ($($old.Length) bytes, $($old.LastWriteTime))"
}
if (-not (Test-Path $ico)) {
    Push-Location $repo
    try { uv run python (Join-Path $here "make_icon.py") } finally { Pop-Location }
}
$src = Join-Path $env:TEMP "DinoAutofocusLauncher.cs"
(Get-Content (Join-Path $here "Launcher.cs") -Raw -Encoding UTF8) `
    -replace 'const string Repo = @"[^"]*";', ('const string Repo = @"' + $repo + '";') `
    -replace 'const int Port = \d+;', ('const int Port = ' + $Port + ';') |
    Set-Content -Path $src -Encoding UTF8
& $csc /nologo /target:winexe /optimize+ /win32icon:"$ico" `
    /r:System.Windows.Forms.dll /r:System.Drawing.dll /out:"$Out" "$src"
if ($LASTEXITCODE -eq 0) { Write-Output "built $Out (repo $repo, port $Port)" } else { exit $LASTEXITCODE }
