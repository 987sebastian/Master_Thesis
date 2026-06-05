param(
    [string]$InstallRoot = "third_party",
    [switch]$SkipSofa,
    [switch]$SkipFfmpeg,
    [switch]$SkipPython
)

$ErrorActionPreference = "Stop"
$workspace = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$installFullPath = Join-Path $workspace $InstallRoot
$sofaVersion = "v25.12.00"
$sofaZipName = "SOFA_v25.12.00_Win64.zip"
$sofaZipUrl = "https://github.com/sofa-framework/sofa/releases/download/$sofaVersion/$sofaZipName"
$sofaSha256 = "538e063ef23c1ada9423aa77a99fc8cb22b163c675e67ee56070896009249c84"
$sofaZipPath = Join-Path $installFullPath $sofaZipName
$pythonVersion = "3.12.10"
$pythonZipName = "python-$pythonVersion-embed-amd64.zip"
$pythonZipUrl = "https://www.python.org/ftp/python/$pythonVersion/$pythonZipName"
$pythonZipPath = Join-Path $installFullPath $pythonZipName
$pythonDir = Join-Path $installFullPath "python312"
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$getPipPath = Join-Path $installFullPath "get-pip.py"

New-Item -ItemType Directory -Force -Path $installFullPath | Out-Null

if (-not $SkipFfmpeg) {
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        Write-Host "ffmpeg already available."
    }
    elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing ffmpeg with winget..."
        winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
        $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        $ffmpegExe = $null
        $packages = Get-ChildItem -Path (Join-Path $packageRoot "Gyan.FFmpeg*") -Directory -ErrorAction SilentlyContinue
        foreach ($package in $packages) {
            $ffmpegExe = Get-Item -Path (Join-Path $package.FullName "ffmpeg-*\bin\ffmpeg.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($ffmpegExe) { break }
        }
        if ($ffmpegExe) {
            $localFfmpegBin = Join-Path $installFullPath "ffmpeg\bin"
            New-Item -ItemType Directory -Force -Path $localFfmpegBin | Out-Null
            Copy-Item -Path (Join-Path $ffmpegExe.DirectoryName "*") -Destination $localFfmpegBin -Recurse -Force
            $env:PATH = "$($ffmpegExe.DirectoryName);$env:PATH"
            Write-Host "ffmpeg located at $($ffmpegExe.FullName)"
            Write-Host "ffmpeg copied to $localFfmpegBin"
        }
        else {
            Write-Host "If ffmpeg is still unavailable, reopen the terminal so PATH refreshes."
        }
    }
    else {
        Write-Warning "winget not found. Install ffmpeg manually and make sure ffmpeg.exe is on PATH."
    }
}

if (-not $SkipPython) {
    $pythonDll = Join-Path $pythonDir "python312.dll"
    $pythonExe = Join-Path $pythonDir "python.exe"
    $pythonPth = Join-Path $pythonDir "python312._pth"
    if (Test-Path -LiteralPath $pythonDll) {
        Write-Host "Python 3.12 embeddable runtime already available at $pythonDir"
    }
    else {
        if (-not (Test-Path -LiteralPath $pythonZipPath)) {
            Write-Host "Downloading $pythonZipName..."
            Invoke-WebRequest -Uri $pythonZipUrl -OutFile $pythonZipPath
        }

        New-Item -ItemType Directory -Force -Path $pythonDir | Out-Null
        Write-Host "Extracting Python 3.12 embeddable runtime..."
        Expand-Archive -LiteralPath $pythonZipPath -DestinationPath $pythonDir -Force
    }

    if (Test-Path -LiteralPath $pythonPth) {
        $pthContent = Get-Content -LiteralPath $pythonPth
        $updatedPth = $pthContent | ForEach-Object {
            if ($_ -eq "#import site") { "import site" } else { $_ }
        }
        $updatedPth | Set-Content -LiteralPath $pythonPth -Encoding ASCII
    }

    $numpyCheck = & $pythonExe -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('numpy') else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        if (-not (Test-Path -LiteralPath $getPipPath)) {
            Write-Host "Downloading get-pip.py..."
            Invoke-WebRequest -Uri $getPipUrl -OutFile $getPipPath
        }

        Write-Host "Installing pip into Python 3.12 embeddable runtime..."
        & $pythonExe $getPipPath --no-warn-script-location

        Write-Host "Installing numpy for SofaPython3..."
        & $pythonExe -m pip install --upgrade "numpy<3"
    }
    else {
        Write-Host "numpy already available in Python 3.12 embeddable runtime."
    }
}

if (-not $SkipSofa) {
    $existingRunSofa = Get-ChildItem -LiteralPath $installFullPath -Filter runSofa.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existingRunSofa) {
        Write-Host "SOFA already appears installed at $($existingRunSofa.FullName)"
    }
    else {
        if (-not (Test-Path -LiteralPath $sofaZipPath)) {
            Write-Host "Downloading $sofaZipName..."
            Invoke-WebRequest -Uri $sofaZipUrl -OutFile $sofaZipPath
        }

        $hash = (Get-FileHash -LiteralPath $sofaZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $sofaSha256) {
            throw "SOFA zip checksum mismatch. Expected $sofaSha256 but got $hash"
        }

        Write-Host "Extracting SOFA..."
        Expand-Archive -LiteralPath $sofaZipPath -DestinationPath $installFullPath -Force
    }
}

Write-Host "Dependency installation step completed."
Write-Host "Run scripts\check_env.ps1 to verify the result."
