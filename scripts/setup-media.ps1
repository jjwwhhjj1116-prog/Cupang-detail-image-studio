# Portable FFmpeg only. No system PATH or machine-wide installation changes.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$studioRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$studioTools = Join-Path $studioRoot '.tools'
New-Item -ItemType Directory -Path $studioTools -Force | Out-Null
$studioArchive = Join-Path $studioTools 'ffmpeg-release-essentials.zip'
$studioChecksum = Join-Path $studioTools 'ffmpeg-release-essentials.zip.sha256'
Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256' -OutFile $studioChecksum -TimeoutSec 60
$studioExpected = ((Get-Content -LiteralPath $studioChecksum -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
if ($studioExpected -notmatch '^[a-f0-9]{64}$') { throw 'Unexpected checksum format' }
if (-not (Test-Path -LiteralPath $studioArchive)) {
    Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $studioArchive -TimeoutSec 240
}
$studioActual = (Get-FileHash -LiteralPath $studioArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($studioActual -ne $studioExpected) { throw 'Checksum mismatch. Archive was not executed or extracted.' }
$studioExtract = Join-Path $studioTools ('ffmpeg-' + $studioActual.Substring(0,12))
if (-not (Test-Path -LiteralPath $studioExtract)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $studioZip = [IO.Compression.ZipFile]::OpenRead($studioArchive)
    try {
        foreach ($studioEntry in $studioZip.Entries) {
            $studioResolved = [IO.Path]::GetFullPath((Join-Path $studioExtract $studioEntry.FullName))
            if (-not $studioResolved.StartsWith($studioExtract + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe archive path' }
        }
    } finally { $studioZip.Dispose() }
    Expand-Archive -LiteralPath $studioArchive -DestinationPath $studioExtract
}
$studioFfmpeg = @(Get-ChildItem -LiteralPath $studioExtract -Filter ffmpeg.exe -File -Recurse)
$studioFfprobe = @(Get-ChildItem -LiteralPath $studioExtract -Filter ffprobe.exe -File -Recurse)
if ($studioFfmpeg.Count -ne 1 -or $studioFfprobe.Count -ne 1) { throw 'FFmpeg binaries not found uniquely' }
$studioVersionLines = & $studioFfmpeg[0].FullName -version
if ($LASTEXITCODE -ne 0) { throw 'FFmpeg verification failed' }
$studioVersion = $studioVersionLines[0]
@{ffmpeg=$studioFfmpeg[0].FullName; ffprobe=$studioFfprobe[0].FullName; sha256=$studioActual; version=$studioVersion; source='https://www.gyan.dev/ffmpeg/builds/'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $studioTools 'media-tools.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $studioTools 'media-tools.json')
