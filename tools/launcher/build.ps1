# Build "DINO Autofocus.exe" onto the Desktop with the .NET Framework compiler in Windows.
#   powershell -ExecutionPolicy Bypass -File tools\launcher\build.ps1
# The repo path compiled into the exe is the clone this script runs from.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here "..\..")).Path
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$ico = Join-Path $here "autofocus.ico"
$out = Join-Path ([Environment]::GetFolderPath("Desktop")) "DINO Autofocus.exe"
if (-not (Test-Path $ico)) { python (Join-Path $here "make_icon.py") }
$src = Join-Path $env:TEMP "DinoAutofocusLauncher.cs"
(Get-Content (Join-Path $here "Launcher.cs") -Raw) -replace `
    'const string Repo = @"[^"]*";', ('const string Repo = @"' + $repo + '";') |
    Set-Content -Path $src -Encoding UTF8
& $csc /nologo /target:winexe /optimize+ /win32icon:"$ico" /r:System.Windows.Forms.dll `
    /out:"$out" "$src"
if ($LASTEXITCODE -eq 0) { Write-Output "built $out (repo $repo)" } else { exit $LASTEXITCODE }
