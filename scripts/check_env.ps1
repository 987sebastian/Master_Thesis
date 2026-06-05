param(
    [string]$SofaRoot = "",
    [string]$ScenePath = "scenes\capsulorhexis.py",
    [string]$VideoPath = "Video Project.mp4"
)

$ErrorActionPreference = "Stop"
$workspace = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")

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

    $localCandidates = @(
        (Join-Path $workspace "third_party\SOFA_v25.12.00_Win64\bin\runSofa.exe"),
        (Join-Path $workspace "third_party\SOFA_v25.12.00_Win64\runSofa.exe")
    )

    foreach ($candidate in $localCandidates) {
        if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
    }

    $thirdParty = Join-Path $workspace "third_party"
    if (-not (Test-Path -LiteralPath $thirdParty)) { return $null }

    $found = Get-ChildItem -LiteralPath $thirdParty -Filter runSofa.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }

    return $null
}

function Find-Ffmpeg {
    $local = Join-Path $workspace "third_party\ffmpeg\bin\ffmpeg.exe"
    if (Test-Path -LiteralPath $local) { return (Resolve-Path -LiteralPath $local).Path }

    $command = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $packageRoot) {
        $packages = Get-ChildItem -Path (Join-Path $packageRoot "Gyan.FFmpeg*") -Directory -ErrorAction SilentlyContinue
        foreach ($package in $packages) {
            $candidate = Get-Item -Path (Join-Path $package.FullName "ffmpeg-*\bin\ffmpeg.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($candidate) { return $candidate.FullName }
        }
    }

    return $null
}

function Add-Check {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    [PSCustomObject]@{
        Check = $Name
        OK = $Ok
        Detail = $Detail
    }
}

$results = @()

$sceneFullPath = Join-Path $workspace $ScenePath
$videoFullPath = Join-Path $workspace $VideoPath
$ffmpeg = Find-Ffmpeg
$runSofa = Find-RunSofa -Root $SofaRoot
$python312 = Join-Path $workspace "third_party\python312\python312.dll"

$results += Add-Check "scene" (Test-Path -LiteralPath $sceneFullPath) $sceneFullPath
$results += Add-Check "video" (Test-Path -LiteralPath $videoFullPath) $videoFullPath
$results += Add-Check "ffmpeg" ($null -ne $ffmpeg) $(if ($ffmpeg) { $ffmpeg } else { "not found in third_party, PATH, or WinGet package directory" })
$results += Add-Check "runSofa" ($null -ne $runSofa) $(if ($runSofa) { $runSofa } else { "not found on PATH or third_party" })
$results += Add-Check "python312.dll" (Test-Path -LiteralPath $python312) $python312

if ($runSofa) {
    try {
        $help = & $runSofa -h 2>&1 | Select-Object -First 8
        $results += Add-Check "runSofa starts" $true (($help -join " ").Trim())
    }
    catch {
        $results += Add-Check "runSofa starts" $false $_.Exception.Message
    }
}

if ($ffmpeg -and (Test-Path -LiteralPath $videoFullPath)) {
    try {
        $ffprobe = Join-Path (Split-Path -Parent $ffmpeg) "ffprobe.exe"
        if (-not (Test-Path -LiteralPath $ffprobe)) {
            throw "ffprobe.exe not found next to ffmpeg.exe"
        }
        $duration = & $ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $videoFullPath
        $stream = & $ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of default=noprint_wrappers=1 $videoFullPath
        $results += Add-Check "video readable" ($LASTEXITCODE -eq 0 -and $duration) ("duration=${duration}s | " + (($stream | ForEach-Object { $_.Trim() }) -join " "))
    }
    catch {
        $results += Add-Check "video readable" $false $_.Exception.Message
    }
}

$results | Format-Table -AutoSize

if (@($results | Where-Object { -not $_.OK }).Count -gt 0) {
    exit 1
}
