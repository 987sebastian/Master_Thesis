param(
    [string]$VideoPath = "Video Project.mp4",
    [string]$OutputDir = "assets\reference",
    [double[]]$Seconds = @(0, 2, 4, 6, 8, 10, 12)
)

$ErrorActionPreference = "Stop"
$workspace = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$videoFullPath = Join-Path $workspace $VideoPath
$outputFullPath = Join-Path $workspace $OutputDir

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

$ffmpeg = Find-Ffmpeg
if (-not $ffmpeg) {
    throw "ffmpeg was not found. Run scripts\install_deps.ps1 first, then reopen the terminal if PATH changed."
}

if (-not (Test-Path -LiteralPath $videoFullPath)) {
    throw "Video file not found: $videoFullPath"
}

New-Item -ItemType Directory -Force -Path $outputFullPath | Out-Null

$manifest = @("# Reference keyframes", "", ("Source: ``" + $VideoPath + "``"), "")

foreach ($second in $Seconds) {
    $safe = "{0:00.##}" -f $second
    $safe = $safe.Replace(".", "_")
    $fileName = "keyframe_${safe}s.png"
    $target = Join-Path $outputFullPath $fileName

    & $ffmpeg -hide_banner -loglevel error -y -ss $second -i $videoFullPath -frames:v 1 $target
    if (-not (Test-Path -LiteralPath $target)) {
        throw "Failed to extract frame at ${second}s"
    }

    $manifest += "## ${second}s"
    $manifest += ""
    $manifest += "![${second}s]($fileName)"
    $manifest += ""
}

$manifestPath = Join-Path $outputFullPath "REFERENCE.md"
$manifest -join [Environment]::NewLine | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "Extracted $($Seconds.Count) keyframes to $outputFullPath"
Write-Host "Open $manifestPath to compare the SOFA scene against the video."
