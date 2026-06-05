param(
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$workspace = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$defaultProfilePath = Join-Path $workspace "assets\capsulorhexis_profile.json"
$customProfilePath = Join-Path $workspace "assets\capsulorhexis_profile.custom.json"
$assetsDir = Join-Path $workspace "assets"

function Read-ProfileFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Profile not found: $Path"
    }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Load-ProfileBundle {
    $defaultProfile = Read-ProfileFile -Path $defaultProfilePath
    $activeProfilePath = $defaultProfilePath
    $activeProfile = $defaultProfile

    if (Test-Path -LiteralPath $customProfilePath) {
        $activeProfile = Read-ProfileFile -Path $customProfilePath
        $activeProfilePath = $customProfilePath
    }

    return @{
        Default = $defaultProfile
        Active = $activeProfile
        ActivePath = $activeProfilePath
    }
}

function Get-IsLeafValue {
    param($Value)

    if ($null -eq $Value) {
        return $false
    }
    if ($Value -is [bool] -or $Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64] -or $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
        return $true
    }
    if ($Value -is [System.Array]) {
        foreach ($entry in $Value) {
            if (-not ($entry -is [byte] -or $entry -is [int16] -or $entry -is [int32] -or $entry -is [int64] -or $entry -is [single] -or $entry -is [double] -or $entry -is [decimal])) {
                return $false
            }
        }
        return $true
    }
    return $false
}

function Get-ValueByPath {
    param(
        $Object,
        [string]$Path
    )

    $current = $Object
    foreach ($segment in $Path.Split(".")) {
        if ($current -is [System.Collections.IDictionary]) {
            $current = $current[$segment]
            continue
        }
        $property = $current.PSObject.Properties[$segment]
        if ($null -eq $property) {
            throw "Missing profile path: $Path"
        }
        $current = $property.Value
    }
    return $current
}

function Set-ValueByPath {
    param(
        $Object,
        [string]$Path,
        $Value
    )

    $segments = $Path.Split(".")
    $current = $Object
    for ($index = 0; $index -lt ($segments.Length - 1); $index++) {
        $segment = $segments[$index]
        if ($current -is [System.Collections.IDictionary]) {
            $current = $current[$segment]
        } else {
            $current = $current.PSObject.Properties[$segment].Value
        }
    }

    $last = $segments[-1]
    if ($current -is [System.Collections.IDictionary]) {
        $current[$last] = $Value
    } else {
        $current.PSObject.Properties[$last].Value = $Value
    }
}

function Copy-ProfileObject {
    param($Object)

    return ($Object | ConvertTo-Json -Depth 20 | ConvertFrom-Json)
}

function Get-EditableFields {
    param(
        $Object,
        [string]$RootPath,
        [string]$Title
    )

    $fields = New-Object System.Collections.Generic.List[object]

    function Add-LeafFields {
        param(
            $Node,
            [string]$CurrentPath,
            [string]$RootPathForLabels,
            $Bucket
        )

        foreach ($property in $Node.PSObject.Properties) {
            $path = if ([string]::IsNullOrWhiteSpace($CurrentPath)) { $property.Name } else { "$CurrentPath.$($property.Name)" }
            $value = $property.Value
            if (Get-IsLeafValue -Value $value) {
                $label = if ($path.StartsWith("$RootPathForLabels.")) { $path.Substring($RootPathForLabels.Length + 1) } else { $path }
                $kind = if ($value -is [bool]) {
                    "bool"
                } elseif ($value -is [System.Array]) {
                    "array"
                } elseif ($value -is [byte] -or $value -is [int16] -or $value -is [int32] -or $value -is [int64]) {
                    "int"
                } else {
                    "float"
                }
                $Bucket.Add(
                    [PSCustomObject]@{
                        Group = $Title
                        Path = $path
                        Label = $label
                        Kind = $kind
                    }
                )
                continue
            }
            if ($value -and $value.PSObject.Properties.Count -gt 0) {
                Add-LeafFields -Node $value -CurrentPath $path -RootPathForLabels $RootPathForLabels -Bucket $Bucket
            }
        }
    }

    $rootNode = Get-ValueByPath -Object $Object -Path $RootPath
    Add-LeafFields -Node $rootNode -CurrentPath $RootPath -RootPathForLabels $RootPath -Bucket $fields
    return $fields
}

function Format-FieldValue {
    param(
        [string]$Kind,
        $Value
    )

    if ($Kind -eq "array") {
        return (($Value | ForEach-Object { [string]$_ }) -join ", ")
    }
    if ($Kind -eq "bool") {
        return [bool]$Value
    }
    return [string]$Value
}

function Parse-FieldValue {
    param(
        [string]$Kind,
        $Value
    )

    if ($Kind -eq "bool") {
        return [bool]$Value
    }
    if ($Kind -eq "int") {
        return [int]::Parse(($Value | Out-String).Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
    }
    if ($Kind -eq "float") {
        return [double]::Parse(($Value | Out-String).Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
    }
    if ($Kind -eq "array") {
        $parts = (($Value | Out-String).Trim() -split "[,; ]+") | Where-Object { $_ -ne "" }
        return @($parts | ForEach-Object { [double]::Parse($_, [System.Globalization.CultureInfo]::InvariantCulture) })
    }
    throw "Unsupported field kind: $Kind"
}

if ($SelfTest) {
    $bundle = Load-ProfileBundle
    $groups = @(
        @{ RootPath = "geometry"; Title = "Geometry" },
        @{ RootPath = "simulation"; Title = "Simulation" },
        @{ RootPath = "controls"; Title = "Controls" },
        @{ RootPath = "view"; Title = "View" },
        @{ RootPath = "materials"; Title = "Materials" },
        @{ RootPath = "visuals"; Title = "Visuals" },
        @{ RootPath = "assets.forceps_model"; Title = "Forceps" },
        @{ RootPath = "assets.eye_model"; Title = "EyeModel" }
    )
    $fieldCount = 0
    foreach ($group in $groups) {
        $fieldCount += (Get-EditableFields -Object $bundle.Active -RootPath $group.RootPath -Title $group.Title).Count
    }
    Write-Host "Profile editor self-test ok"
    Write-Host "default=$defaultProfilePath"
    Write-Host "active=$($bundle.ActivePath)"
    Write-Host "editable_fields=$fieldCount"
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$profileBundle = Load-ProfileBundle
$activeProfile = Copy-ProfileObject -Object $profileBundle.Active
$defaultProfile = Copy-ProfileObject -Object $profileBundle.Default
$editableGroups = @(
    @{ RootPath = "geometry"; Title = "Geometry" },
    @{ RootPath = "simulation"; Title = "Simulation" },
    @{ RootPath = "controls"; Title = "Controls" },
    @{ RootPath = "view"; Title = "View" },
    @{ RootPath = "materials"; Title = "Materials" },
    @{ RootPath = "visuals"; Title = "Visuals" },
    @{ RootPath = "assets.forceps_model"; Title = "Forceps" },
    @{ RootPath = "assets.eye_model"; Title = "Eye Model" }
)

$form = New-Object System.Windows.Forms.Form
$form.Text = "Capsulorhexis Parameter Menu"
$form.Size = New-Object System.Drawing.Size(980, 820)
$form.StartPosition = "CenterScreen"

$controlMap = @{}

$menuStrip = New-Object System.Windows.Forms.MenuStrip
$fileMenu = New-Object System.Windows.Forms.ToolStripMenuItem("File")
$saveMenuItem = New-Object System.Windows.Forms.ToolStripMenuItem("Save Custom")
$reloadMenuItem = New-Object System.Windows.Forms.ToolStripMenuItem("Reload Active")
$loadDefaultMenuItem = New-Object System.Windows.Forms.ToolStripMenuItem("Load Default Into Form")
$openAssetsMenuItem = New-Object System.Windows.Forms.ToolStripMenuItem("Open Assets Folder")
$fileMenu.DropDownItems.AddRange(@($saveMenuItem, $reloadMenuItem, $loadDefaultMenuItem, $openAssetsMenuItem))
$menuStrip.Items.Add($fileMenu)
$form.MainMenuStrip = $menuStrip
$form.Controls.Add($menuStrip)

$summaryPanel = New-Object System.Windows.Forms.Panel
$summaryPanel.Dock = "Top"
$summaryPanel.Height = 92
$summaryPanel.Padding = New-Object System.Windows.Forms.Padding(12, 6, 12, 6)
$form.Controls.Add($summaryPanel)

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "Eye anatomy / trocar / material parameters"
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold)
$titleLabel.AutoSize = $true
$titleLabel.Location = New-Object System.Drawing.Point(10, 10)
$summaryPanel.Controls.Add($titleLabel)

$pathsLabel = New-Object System.Windows.Forms.Label
$pathsLabel.AutoSize = $true
$pathsLabel.Location = New-Object System.Drawing.Point(12, 42)
$pathsLabel.Text = "Default: $defaultProfilePath`r`nActive: $($profileBundle.ActivePath)`r`nCustom save target: $customProfilePath"
$summaryPanel.Controls.Add($pathsLabel)

$hintLabel = New-Object System.Windows.Forms.Label
$hintLabel.AutoSize = $true
$hintLabel.Location = New-Object System.Drawing.Point(12, 74)
$hintLabel.Text = "Save writes a local custom profile. Return to SOFA and press Ctrl+R to reload the scene."
$summaryPanel.Controls.Add($hintLabel)

$buttonsPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$buttonsPanel.Dock = "Bottom"
$buttonsPanel.Height = 52
$buttonsPanel.FlowDirection = "LeftToRight"
$buttonsPanel.Padding = New-Object System.Windows.Forms.Padding(12, 8, 12, 8)
$form.Controls.Add($buttonsPanel)

$saveButton = New-Object System.Windows.Forms.Button
$saveButton.Text = "Save Custom"
$saveButton.AutoSize = $true
$buttonsPanel.Controls.Add($saveButton)

$reloadButton = New-Object System.Windows.Forms.Button
$reloadButton.Text = "Reload Active"
$reloadButton.AutoSize = $true
$buttonsPanel.Controls.Add($reloadButton)

$defaultButton = New-Object System.Windows.Forms.Button
$defaultButton.Text = "Load Default"
$defaultButton.AutoSize = $true
$buttonsPanel.Controls.Add($defaultButton)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.AutoSize = $true
$statusLabel.Margin = New-Object System.Windows.Forms.Padding(18, 8, 0, 0)
$statusLabel.Text = "Ready"
$buttonsPanel.Controls.Add($statusLabel)

$tabControl = New-Object System.Windows.Forms.TabControl
$tabControl.Dock = "Fill"
$tabControl.Padding = New-Object System.Drawing.Point(16, 8)
$form.Controls.Add($tabControl)
$tabControl.BringToFront()

function Fill-ControlsFromProfile {
    param($SourceProfile)

    foreach ($entry in $controlMap.GetEnumerator()) {
        $meta = $entry.Value.Meta
        $control = $entry.Value.Control
        $value = Get-ValueByPath -Object $SourceProfile -Path $meta.Path
        if ($meta.Kind -eq "bool") {
            $control.Checked = [bool](Format-FieldValue -Kind $meta.Kind -Value $value)
        } else {
            $control.Text = Format-FieldValue -Kind $meta.Kind -Value $value
        }
    }
}

function Apply-ControlsToProfile {
    param($TargetProfile)

    foreach ($entry in $controlMap.GetEnumerator()) {
        $meta = $entry.Value.Meta
        $control = $entry.Value.Control
        $rawValue = if ($meta.Kind -eq "bool") { $control.Checked } else { $control.Text }
        $parsed = Parse-FieldValue -Kind $meta.Kind -Value $rawValue
        Set-ValueByPath -Object $TargetProfile -Path $meta.Path -Value $parsed
    }
}

function Reload-FromDisk {
    $script:profileBundle = Load-ProfileBundle
    $script:activeProfile = Copy-ProfileObject -Object $script:profileBundle.Active
    $script:defaultProfile = Copy-ProfileObject -Object $script:profileBundle.Default
    $pathsLabel.Text = "Default: $defaultProfilePath`r`nActive: $($script:profileBundle.ActivePath)`r`nCustom save target: $customProfilePath"
    Fill-ControlsFromProfile -SourceProfile $script:activeProfile
    $statusLabel.Text = "Reloaded from disk"
}

function Save-CustomProfile {
    $candidate = Copy-ProfileObject -Object $script:activeProfile
    Apply-ControlsToProfile -TargetProfile $candidate
    $json = $candidate | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($customProfilePath, $json + [Environment]::NewLine, $utf8NoBom)
    $script:activeProfile = $candidate
    $script:profileBundle = @{
        Default = $script:defaultProfile
        Active = $script:activeProfile
        ActivePath = $customProfilePath
    }
    $pathsLabel.Text = "Default: $defaultProfilePath`r`nActive: $customProfilePath`r`nCustom save target: $customProfilePath"
    $statusLabel.Text = "Saved custom profile"
    [System.Windows.Forms.MessageBox]::Show("Custom profile saved to:`r`n$customProfilePath`r`n`r`nBack in SOFA, press Ctrl+R to reload the scene.", "Profile Saved") | Out-Null
}

foreach ($group in $editableGroups) {
    $fields = Get-EditableFields -Object $activeProfile -RootPath $group.RootPath -Title $group.Title
    if ($fields.Count -eq 0) {
        continue
    }

    $tabPage = New-Object System.Windows.Forms.TabPage
    $tabPage.Text = $group.Title

    $scrollPanel = New-Object System.Windows.Forms.Panel
    $scrollPanel.Dock = "Fill"
    $scrollPanel.AutoScroll = $true
    $tabPage.Controls.Add($scrollPanel)

    $table = New-Object System.Windows.Forms.TableLayoutPanel
    $table.Dock = "Top"
    $table.AutoSize = $true
    $table.AutoSizeMode = "GrowAndShrink"
    $table.ColumnCount = 2
    $table.Padding = New-Object System.Windows.Forms.Padding(12)
    $table.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 42)))
    $table.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 58)))
    $scrollPanel.Controls.Add($table)

    foreach ($field in $fields) {
        $table.RowCount += 1
        $rowIndex = $table.RowCount - 1
        $table.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))

        $label = New-Object System.Windows.Forms.Label
        $label.Text = $field.Label
        $label.AutoSize = $true
        $label.Margin = New-Object System.Windows.Forms.Padding(3, 8, 12, 8)
        $table.Controls.Add($label, 0, $rowIndex)

        if ($field.Kind -eq "bool") {
            $editor = New-Object System.Windows.Forms.CheckBox
            $editor.AutoSize = $true
            $editor.Checked = [bool](Get-ValueByPath -Object $activeProfile -Path $field.Path)
            $editor.Margin = New-Object System.Windows.Forms.Padding(3, 6, 3, 6)
        } else {
            $editor = New-Object System.Windows.Forms.TextBox
            $editor.Width = 320
            $editor.Text = Format-FieldValue -Kind $field.Kind -Value (Get-ValueByPath -Object $activeProfile -Path $field.Path)
            $editor.Margin = New-Object System.Windows.Forms.Padding(3, 4, 3, 4)
        }

        $table.Controls.Add($editor, 1, $rowIndex)
        $controlMap[$field.Path] = @{
            Meta = $field
            Control = $editor
        }
    }

    [void]$tabControl.TabPages.Add($tabPage)
}

$saveAction = {
    try {
        Save-CustomProfile
    } catch {
        $statusLabel.Text = "Save failed"
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "Save Failed", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
}

$reloadAction = {
    try {
        Reload-FromDisk
    } catch {
        $statusLabel.Text = "Reload failed"
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "Reload Failed", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
}

$loadDefaultAction = {
    Fill-ControlsFromProfile -SourceProfile $defaultProfile
    $statusLabel.Text = "Default values loaded into form"
}

$openAssetsAction = {
    Start-Process explorer.exe -ArgumentList $assetsDir
}

$saveButton.Add_Click($saveAction)
$saveMenuItem.Add_Click($saveAction)
$reloadButton.Add_Click($reloadAction)
$reloadMenuItem.Add_Click($reloadAction)
$defaultButton.Add_Click($loadDefaultAction)
$loadDefaultMenuItem.Add_Click($loadDefaultAction)
$openAssetsMenuItem.Add_Click($openAssetsAction)

[void]$form.ShowDialog()
