param(
    [string]$StudioRoot = (Join-Path $PSScriptRoot '..'),
    # Destination is the full skill directory, not the parent skills directory.
    [string]$Destination
)
$ErrorActionPreference = 'Stop'
$manager = 'cupang-detail-image-studio/install-hadi-skill'
$skillName = 'detail-page-production'
$repo = (Resolve-Path -LiteralPath $StudioRoot).Path
$source = Join-Path $repo ".agents/skills/$skillName"
if (-not (Test-Path -LiteralPath (Join-Path $repo 'AGENTS.md') -PathType Leaf)) {
    throw 'StudioRoot must point to the Cupang-detail-image-studio repository.'
}
foreach ($required in @('SKILL.md', 'agents/openai.yaml')) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $required) -PathType Leaf)) {
        throw "Repository skill is missing $required. Update this repository before installing."
    }
}
if (-not $Destination) {
    $codexDirectory = $env:CODEX_HOME
    if (-not $codexDirectory) {
        $codexDirectory = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
    }
    $Destination = Join-Path $codexDirectory "skills/$skillName"
}
$target = [IO.Path]::GetFullPath($Destination).TrimEnd([IO.Path]::DirectorySeparatorChar)
$source = [IO.Path]::GetFullPath($source).TrimEnd([IO.Path]::DirectorySeparatorChar)
$comparison = [StringComparison]::OrdinalIgnoreCase
$separator = [IO.Path]::DirectorySeparatorChar
if ($target.Equals($source, $comparison) -or
    $target.StartsWith($source + $separator, $comparison) -or
    $source.StartsWith($target + $separator, $comparison)) {
    throw 'Destination must be separate from the source skill and its parent directories.'
}
$parent = Split-Path -Parent $target
$leaf = Split-Path -Leaf $target
if (-not $parent -or -not $leaf) { throw 'Destination must be a named skill directory.' }
$markerPath = Join-Path $target 'repo-location.json'
if (Test-Path -LiteralPath $target) {
    $existing = Get-Item -LiteralPath $target -Force
    if (-not $existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Destination is a file or linked directory. Existing content was preserved.'
    }
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw 'An unmanaged skill already exists at Destination. Existing content was preserved. Choose another Destination.'
    }
    $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($marker.managed_by -ne $manager -or $marker.skill_name -ne $skillName) {
        throw 'Destination belongs to another installation. Existing content was preserved.'
    }
}
New-Item -ItemType Directory -Path $parent -Force | Out-Null
$suffix = [Guid]::NewGuid().ToString('N')
$stage = [IO.Path]::GetFullPath((Join-Path $parent "$leaf.stage-$suffix"))
$backupBase = Split-Path -Parent $parent
if (-not $backupBase) { throw 'Destination needs a parent directory outside the skill search directory for backups.' }
$backupRoot = [IO.Path]::GetFullPath((Join-Path $backupBase 'skill-install-backups'))
$backup = [IO.Path]::GetFullPath((Join-Path $backupRoot "$leaf-$suffix"))
# Installation and staging stay in the skill directory; backups stay outside discovery.
foreach ($path in @($target, $stage)) {
    if (-not [String]::Equals((Split-Path -Parent $path), $parent, $comparison)) {
        throw 'Installation target escaped its destination parent.'
    }
}
if (-not [String]::Equals((Split-Path -Parent $backup), $backupRoot, $comparison) -or
    $backupRoot.Equals($parent, $comparison) -or
    $backupRoot.StartsWith($parent + $separator, $comparison)) {
    throw 'Backup location must stay outside the skill search directory.'
}
$backedUp = $false
try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $source -Force) {
        if ($item.Name -ne 'repo-location.json') {
            Copy-Item -LiteralPath $item.FullName -Destination $stage -Recurse -Force
        }
    }
    $record = [ordered]@{
        schema_version = 1
        managed_by = $manager
        skill_name = $skillName
        repository_root = $repo
        source_repository = 'https://github.com/jjwwhhjj1116-prog/Cupang-detail-image-studio.git'
        installed_at_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText((Join-Path $stage 'repo-location.json'), ($record | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $target) {
        New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
        Move-Item -LiteralPath $target -Destination $backup
        $backedUp = $true
    }
    Move-Item -LiteralPath $stage -Destination $target
} catch {
    if ($backedUp -and -not (Test-Path -LiteralPath $target)) {
        Move-Item -LiteralPath $backup -Destination $target
    }
    throw
} finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
Write-Host "Installed skill at $target"
Write-Host "Repository pointer: $repo"
if ($backedUp) { Write-Host "Previous installation retained at $backup" }
Write-Host 'The skill is available on your next Codex turn. Invoke $detail-page-production with a product URL or images.'
