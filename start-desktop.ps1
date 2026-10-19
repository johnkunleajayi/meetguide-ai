$ProjectRoot = $PSScriptRoot
$CargoHome = Join-Path $ProjectRoot "work\tools\cargo"
$RustupHome = Join-Path $ProjectRoot "work\tools\rustup"
$DesktopDir = Join-Path $ProjectRoot "desktop"

$env:CARGO_HOME = $CargoHome
$env:RUSTUP_HOME = $RustupHome
$env:PATH = "$CargoHome\bin;$env:PATH"

Set-Location $DesktopDir

Write-Host "Starting MeetGuide AI Desktop..."
npm run tauri dev