param(
    [string]$SofaRoot = "",
    [string]$ScenePath = "scenes\capsulorhexis.py",
    [switch]$Batch,
    [int]$Iterations = 900,
    [switch]$NoAutoStart,
    [switch]$NoInteractive,
    [switch]$NoProfileMenu
)

$ErrorActionPreference = "Stop"
$workspace = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$sceneFullPath = Join-Path $workspace $ScenePath

function Find-RunSofa {
    param([string]$Root)

    if ($Root) {
        $candidate = Join-Path $Root "bin\runSofa.exe"
        if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
        $candidate = Join-Path $Root "runSofa.exe"
        if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
    }

    $command = Get-Command runSofa -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $thirdParty = Join-Path $workspace "third_party"
    if (-not (Test-Path -LiteralPath $thirdParty)) { return $null }

    $found = Get-ChildItem -LiteralPath $thirdParty -Filter runSofa.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }

    return $null
}

if (-not (Test-Path -LiteralPath $sceneFullPath)) {
    throw "Scene not found: $sceneFullPath"
}

$runSofa = Find-RunSofa -Root $SofaRoot
if (-not $runSofa) {
    throw "runSofa.exe not found. Run scripts\install_deps.ps1 or pass -SofaRoot."
}

$sofaBin = Split-Path -Parent $runSofa
$sofaRoot = Split-Path -Parent $sofaBin
$sofaPythonBin = Join-Path $sofaRoot "plugins\SofaPython3\bin"
$python312 = Join-Path $workspace "third_party\python312"

if (Test-Path -LiteralPath $python312) {
    $env:PATH = "$python312;$env:PATH"
    $env:PYTHONHOME = $python312
}

if (Test-Path -LiteralPath $sofaPythonBin) {
    $env:PATH = "$sofaPythonBin;$env:PATH"
    $env:PYTHONPATH = "$sofaPythonBin;$env:PYTHONPATH"
}

$env:PATH = "$sofaBin;$env:PATH"

if (-not $Batch -and -not $NoProfileMenu) {
    $profileEditor = Join-Path $workspace "scripts\capsulorhexis_profile_editor.ps1"
    if (Test-Path -LiteralPath $profileEditor) {
        Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $profileEditor
        ) | Out-Null
    }
}

$args = @("-l", "SofaPython3")
if ($Batch) {
    $args += @("-g", "batch", "-n", "$Iterations")
} else {
    if (-not $NoAutoStart) {
        $args += "-a"
    }
    if (-not $NoInteractive) {
        $args += "--interactive"
    }
}
$args += $sceneFullPath

Write-Host "Starting SOFA: $runSofa $($args -join ' ')"
& $runSofa @args
