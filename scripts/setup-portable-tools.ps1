param(
    [string]$StudioRoot = (Join-Path $PSScriptRoot '..'),
    [switch]$Offline,
    [switch]$ForcePortable,
    [switch]$FunctionsOnly
)

# Project-local tools only. Never changes system PATH, registry, or credentials.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Process-local .NET switches plus extended paths avoid Windows PowerShell 5.1's
# legacy MAX_PATH limit without changing Windows policy or the registry.
[AppContext]::SetSwitch('Switch.System.IO.UseLegacyPathHandling', $false)
[AppContext]::SetSwitch('Switch.System.IO.BlockLongPaths', $false)

function Get-StudioIOPath([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    if ($resolved.StartsWith('\\?\')) { return $resolved }
    if ($resolved.StartsWith('\\')) { return '\\?\UNC\' + $resolved.Substring(2) }
    return '\\?\' + $resolved
}

function Write-StudioUtf8([string]$Path, [string]$Content) {
    [IO.Directory]::CreateDirectory((Get-StudioIOPath ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path))))) | Out-Null
    [IO.File]::WriteAllText((Get-StudioIOPath $Path), $Content, (New-Object Text.UTF8Encoding($false)))
}

function Write-StudioJson([string]$Path, $Value) {
    Write-StudioUtf8 $Path (($Value | ConvertTo-Json -Depth 20) + [Environment]::NewLine)
}

function Get-StudioHash([string]$Path) {
    $stream = [IO.File]::OpenRead((Get-StudioIOPath $Path))
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}

function Assert-StudioChildPath([string]$Path, [string]$Root) {
    $resolved = [IO.Path]::GetFullPath($Path)
    $boundary = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target must stay inside the intended workspace: $resolved"
    }
    return $resolved
}

function Get-StudioArchive($Spec, [string]$Root, [switch]$Offline) {
    if ($Spec.sha256 -notmatch '^[a-f0-9]{64}$' -or -not $Spec.url.StartsWith('https://')) {
        throw 'The tool lock must provide an HTTPS archive and a pinned SHA256.'
    }
    if ([IO.Path]::GetFileName($Spec.filename) -ne $Spec.filename) { throw 'Unsafe archive filename.' }
    $cache = Assert-StudioChildPath (Join-Path $Root '.tools/downloads') $Root
    [IO.Directory]::CreateDirectory($cache) | Out-Null
    $archive = Assert-StudioChildPath (Join-Path $cache ($Spec.sha256.Substring(0, 12) + '-' + $Spec.filename)) $Root
    if (Test-Path -LiteralPath $archive -PathType Leaf) {
        if ((Get-StudioHash $archive) -eq $Spec.sha256) { return $archive }
        $invalid = Assert-StudioChildPath ($archive + '.invalid-' + [Guid]::NewGuid().ToString('N')) $Root
        Move-Item -LiteralPath $archive -Destination $invalid
    }
    if ($Offline) { throw "Offline: no verified cached archive for $($Spec.filename)." }
    $partial = Assert-StudioChildPath ($archive + '.partial-' + [Guid]::NewGuid().ToString('N')) $Root
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $Spec.url -OutFile $partial -TimeoutSec 300
    if ((Get-StudioHash $partial) -ne $Spec.sha256) {
        throw "SHA256 mismatch for $($Spec.filename). Download was not extracted or executed: $partial"
    }
    Move-Item -LiteralPath $partial -Destination $archive
    return $archive
}

function Expand-StudioSafeZip([string]$Archive, [string]$Destination, [string]$AllowedRoot) {
    $destinationPath = Assert-StudioChildPath $Destination $AllowedRoot
    if (Test-Path -LiteralPath $destinationPath) { throw 'ZIP staging destination must be new.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead((Get-StudioIOPath $Archive))
    try {
        foreach ($entry in $zip.Entries) {
            if ([IO.Path]::IsPathRooted($entry.FullName) -or $entry.FullName.Contains(':')) {
                throw 'Unsafe absolute ZIP entry.'
            }
            $entryPath = [IO.Path]::GetFullPath((Join-Path $destinationPath $entry.FullName))
            $prefix = $destinationPath.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
            if (-not $entryPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Unsafe ZIP entry escapes the staging folder.'
            }
        }
        [IO.Directory]::CreateDirectory((Get-StudioIOPath $destinationPath)) | Out-Null
        foreach ($entry in $zip.Entries) {
            $entryPath = [IO.Path]::GetFullPath((Join-Path $destinationPath $entry.FullName))
            if ($entry.FullName.EndsWith('/') -or $entry.FullName.EndsWith('\')) {
                [IO.Directory]::CreateDirectory((Get-StudioIOPath $entryPath)) | Out-Null
                continue
            }
            [IO.Directory]::CreateDirectory((Get-StudioIOPath ([IO.Path]::GetDirectoryName($entryPath)))) | Out-Null
            $inputStream = $entry.Open()
            $outputStream = [IO.File]::Open((Get-StudioIOPath $entryPath), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
            try { $inputStream.CopyTo($outputStream) }
            finally { $outputStream.Dispose(); $inputStream.Dispose() }
        }
    } finally { $zip.Dispose() }
}

function Install-StudioZipTree([string]$Archive, [string]$Target, [string]$Root, [string]$InnerDirectory = '') {
    $stage = Assert-StudioChildPath (Join-Path $Root ('.tools/extract-' + [Guid]::NewGuid().ToString('N'))) $Root
    Expand-StudioSafeZip $Archive $stage $Root
    $source = $stage
    if ($InnerDirectory) {
        $source = Assert-StudioChildPath (Join-Path $stage $InnerDirectory) $stage
        if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw 'Expected archive folder is missing.' }
    }
    $targetPath = Assert-StudioChildPath $Target $Root
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($targetPath)) | Out-Null
    if (Test-Path -LiteralPath $targetPath) {
        $preserved = Assert-StudioChildPath ($targetPath + '.previous-' + [Guid]::NewGuid().ToString('N')) $Root
        [IO.Directory]::Move((Get-StudioIOPath $targetPath), (Get-StudioIOPath $preserved))
    }
    [IO.Directory]::Move((Get-StudioIOPath $source), (Get-StudioIOPath $targetPath))
    return $targetPath
}

function Test-StudioPython([string]$Path, $Lock, [string]$Origin) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or $Path -like '*\WindowsApps\*') { return $null }
    $code = "import io,json,struct,sys;import PIL;from PIL import Image;b=io.BytesIO();Image.new('RGB',(2,2)).save(b,format='PNG');Image.open(b).load();print(json.dumps({'path':sys.executable,'version':'.'.join(map(str,sys.version_info[:3])),'bits':struct.calcsize('P')*8,'pillow_version':PIL.__version__}))"
    try {
        $lines = @(& $Path -X utf8 -c $code 2>$null)
        if ($LASTEXITCODE -ne 0) { return $null }
        $result = $lines[-1] | ConvertFrom-Json
        if ([Version]$result.version -lt [Version]$Lock.python.minimum_existing_version -or $result.bits -ne 64 -or $result.pillow_version -ne $Lock.pillow.version) { return $null }
        return [ordered]@{ path = [IO.Path]::GetFullPath($result.path); version = $result.version; pillow_version = $result.pillow_version; origin = $Origin }
    } catch { return $null }
}

function Test-StudioNode([string]$Path, $Lock, [string]$Origin) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $folder = [IO.Path]::GetDirectoryName($Path)
    $npm = Join-Path $folder 'npm.cmd'
    $npx = Join-Path $folder 'npx.cmd'
    if (-not (Test-Path -LiteralPath $npm -PathType Leaf) -or -not (Test-Path -LiteralPath $npx -PathType Leaf)) { return $null }
    try {
        $nodeVersion = ((& $Path --version 2>$null) | Select-Object -Last 1).Trim().TrimStart('v')
        if ($LASTEXITCODE -ne 0 -or ([Version]$nodeVersion).Major -lt [int]$Lock.node.minimum_existing_major) { return $null }
        $nodeArchitecture = ((& $Path -p 'process.arch' 2>$null) | Select-Object -Last 1).Trim()
        if ($LASTEXITCODE -ne 0 -or $nodeArchitecture -ne 'x64') { return $null }
        $npmVersion = ((& $npm --version 2>$null) | Select-Object -Last 1).Trim()
        if ($LASTEXITCODE -ne 0) { return $null }
        return [ordered]@{ path = [IO.Path]::GetFullPath($Path); npm = $npm; npx = $npx; version = $nodeVersion; npm_version = $npmVersion; origin = $Origin }
    } catch { return $null }
}

function Get-StudioRuntimeCandidates([string]$Name) {
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    foreach ($command in @(Get-Command ($Name + '.exe') -CommandType Application -All -ErrorAction SilentlyContinue)) {
        if ($command.Source) { $candidates.Add($command.Source) }
    }
    $userDirectory = [Environment]::GetFolderPath('UserProfile')
    $runtimeCache = Join-Path $userDirectory '.cache/codex-runtimes'
    if (Test-Path -LiteralPath $runtimeCache -PathType Container) {
        foreach ($runtime in @(Get-ChildItem -LiteralPath $runtimeCache -Directory | Sort-Object LastWriteTime -Descending)) {
            $relative = if ($Name -eq 'python') { 'dependencies/python/python.exe' } else { 'dependencies/node/bin/node.exe' }
            $candidate = Join-Path $runtime.FullName $relative
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $candidates.Add($candidate) }
        }
    }
    return @($candidates | Select-Object -Unique)
}

function Initialize-StudioPython([string]$Root, $Lock, [switch]$Offline, [switch]$ForcePortable) {
    if (-not $ForcePortable) {
        foreach ($candidate in @(Get-StudioRuntimeCandidates 'python')) {
            $existing = Test-StudioPython $candidate $Lock 'existing-user-runtime'
            if ($existing) { return $existing }
        }
    }
    $target = Assert-StudioChildPath (Join-Path $Root ('.tools/python-' + $Lock.python.fallback_version)) $Root
    $exe = Join-Path $target 'python.exe'
    if ((Test-Path -LiteralPath $exe -PathType Leaf) -and (Get-StudioHash $exe) -eq $Lock.python.executable_sha256) {
        $existing = Test-StudioPython $exe $Lock 'project-portable'
        if ($existing) { return $existing }
    }
    $pythonArchive = Get-StudioArchive $Lock.python.archive $Root -Offline:$Offline
    $pillowArchive = Get-StudioArchive $Lock.pillow.archive $Root -Offline:$Offline
    Install-StudioZipTree $pythonArchive $target $Root | Out-Null
    if ((Get-StudioHash $exe) -ne $Lock.python.executable_sha256) { throw 'Pinned Python executable hash mismatch.' }
    # CPython's embedded package supports vendoring packages beside the app.
    # Install the complete official wheel locally, including native pillow.libs.
    $packages = Join-Path $target 'Lib/site-packages'
    $packageStage = Assert-StudioChildPath (Join-Path $Root ('.tools/pillow-' + [Guid]::NewGuid().ToString('N'))) $Root
    Expand-StudioSafeZip $pillowArchive $packageStage $Root
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($packages)) | Out-Null
    Move-Item -LiteralPath $packageStage -Destination $packages
    $pythonPathConfig = "python312.zip`n.`nLib/site-packages`n../../scripts`n../..`nimport site`n"
    Write-StudioUtf8 (Join-Path $target 'python312._pth') $pythonPathConfig
    $verified = Test-StudioPython $exe $Lock 'project-portable'
    if (-not $verified) { throw 'Portable Python/Pillow verification failed.' }
    return $verified
}

function Initialize-StudioNode([string]$Root, $Lock, [switch]$Offline, [switch]$ForcePortable) {
    if (-not $ForcePortable) {
        foreach ($candidate in @(Get-StudioRuntimeCandidates 'node')) {
            $existing = Test-StudioNode $candidate $Lock 'existing-user-runtime'
            if ($existing) { return $existing }
        }
    }
    $directoryName = 'node-v' + $Lock.node.fallback_version + '-win-x64'
    $target = Assert-StudioChildPath (Join-Path $Root ('.tools/' + $directoryName)) $Root
    $exe = Join-Path $target 'node.exe'
    if ((Test-Path -LiteralPath $exe -PathType Leaf) -and (Get-StudioHash $exe) -eq $Lock.node.executable_sha256) {
        $existing = Test-StudioNode $exe $Lock 'project-portable'
        if ($existing) { return $existing }
    }
    $archive = Get-StudioArchive $Lock.node.archive $Root -Offline:$Offline
    Install-StudioZipTree $archive $target $Root $directoryName | Out-Null
    if ((Get-StudioHash $exe) -ne $Lock.node.executable_sha256) { throw 'Pinned Node executable hash mismatch.' }
    $verified = Test-StudioNode $exe $Lock 'project-portable'
    if (-not $verified) { throw 'Portable Node/npm verification failed.' }
    return $verified
}

function Initialize-StudioMedia([string]$Root, $Lock, [switch]$Offline) {
    $target = Assert-StudioChildPath (Join-Path $Root ('.tools/ffmpeg-' + $Lock.ffmpeg.archive.sha256.Substring(0, 12))) $Root
    $bin = Join-Path $target ('ffmpeg-' + $Lock.ffmpeg.version + '-essentials_build/bin')
    $ffmpeg = Join-Path $bin 'ffmpeg.exe'
    $ffprobe = Join-Path $bin 'ffprobe.exe'
    $valid = (Test-Path -LiteralPath $ffmpeg -PathType Leaf) -and (Test-Path -LiteralPath $ffprobe -PathType Leaf)
    if ($valid) { $valid = (Get-StudioHash $ffmpeg) -eq $Lock.ffmpeg.ffmpeg_sha256 -and (Get-StudioHash $ffprobe) -eq $Lock.ffmpeg.ffprobe_sha256 }
    if (-not $valid) {
        $archive = Get-StudioArchive $Lock.ffmpeg.archive $Root -Offline:$Offline
        Install-StudioZipTree $archive $target $Root | Out-Null
    }
    if ((Get-StudioHash $ffmpeg) -ne $Lock.ffmpeg.ffmpeg_sha256 -or (Get-StudioHash $ffprobe) -ne $Lock.ffmpeg.ffprobe_sha256) { throw 'Pinned FFmpeg binary hash mismatch.' }
    $versionLines = @(& $ffmpeg -version 2>$null)
    if ($LASTEXITCODE -ne 0 -or $versionLines[0] -notmatch ('^ffmpeg version ' + [regex]::Escape($Lock.ffmpeg.version))) { throw 'FFmpeg version verification failed.' }
    $probeLines = @(& $ffprobe -version 2>$null)
    if ($LASTEXITCODE -ne 0 -or $probeLines[0] -notmatch ('^ffprobe version ' + [regex]::Escape($Lock.ffmpeg.version))) { throw 'FFprobe version verification failed.' }
    $receipt = [ordered]@{ ffmpeg = $ffmpeg; ffprobe = $ffprobe; sha256 = $Lock.ffmpeg.archive.sha256; version = $versionLines[0]; source = $Lock.ffmpeg.source; ffmpeg_sha256 = $Lock.ffmpeg.ffmpeg_sha256; ffprobe_sha256 = $Lock.ffmpeg.ffprobe_sha256 }
    Write-StudioJson (Join-Path $Root '.tools/media-tools.json') $receipt
    return [ordered]@{ path = $ffmpeg; ffprobe = $ffprobe; version = $Lock.ffmpeg.version; sha256 = $Lock.ffmpeg.ffmpeg_sha256; origin = 'project-portable' }
}

function Initialize-StudioFont([string]$Root, $Lock, [switch]$Offline) {
    $target = Assert-StudioChildPath (Join-Path $Root '.tools/fonts/gmarket-sans') $Root
    $font = Join-Path $target $Lock.font.filename
    $valid = (Test-Path -LiteralPath $font -PathType Leaf)
    if ($valid) { $valid = (Get-StudioHash $font) -eq $Lock.font.sha256 }
    if (-not $valid) {
        $archive = Get-StudioArchive $Lock.font.archive $Root -Offline:$Offline
        $stage = Assert-StudioChildPath (Join-Path $Root ('.tools/font-' + [Guid]::NewGuid().ToString('N'))) $Root
        Expand-StudioSafeZip $archive $stage $Root
        $source = Join-Path $stage $Lock.font.filename
        if ((Get-StudioHash $source) -ne $Lock.font.sha256) { throw 'Pinned Gmarket font hash mismatch.' }
        [IO.Directory]::CreateDirectory($target) | Out-Null
        if (Test-Path -LiteralPath $font) {
            $preserved = Assert-StudioChildPath ($font + '.previous-' + [Guid]::NewGuid().ToString('N')) $Root
            Move-Item -LiteralPath $font -Destination $preserved
        }
        Copy-Item -LiteralPath $source -Destination $font
    }
    $notice = Join-Path $target 'LICENSE-NOTICE.txt'
    Write-StudioUtf8 $notice ("Gmarket Sans font license notice`nOfficial source: https://corp.gmarket.com/fonts/`n`nThe official Gmarket font page declares the SIL Open Font License and allows personal and corporate commercial and non-commercial use. The supplied TTF ZIP contains three font files and no separate license document. Keep this notice with the downloaded font; consult the official page for its terms.`n`nSIL OFL reference: https://openfontlicense.org/open-font-license-official-text/`nFont files are kept project-local; no Windows font registration is performed.`n")
    return [ordered]@{ path = $font; sha256 = $Lock.font.sha256; license_notice = $notice; origin = 'official-gmarket-project-local' }
}

if ($FunctionsOnly) { return }
if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess -or $env:OS -ne 'Windows_NT') { throw 'This installer supports 64-bit Windows and 64-bit PowerShell.' }
$resolvedStudioRoot = [IO.Path]::GetFullPath($StudioRoot)
$lockPath = Join-Path $resolvedStudioRoot 'config/toolchain.lock.json'
$toolLock = Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($toolLock.platform -ne 'windows-x64' -or $toolLock.schema_version -ne 1) { throw 'Unsupported toolchain lock.' }
$pythonRuntime = Initialize-StudioPython $resolvedStudioRoot $toolLock -Offline:$Offline -ForcePortable:$ForcePortable
$nodeRuntime = Initialize-StudioNode $resolvedStudioRoot $toolLock -Offline:$Offline -ForcePortable:$ForcePortable
$mediaRuntime = Initialize-StudioMedia $resolvedStudioRoot $toolLock -Offline:$Offline
$fontRuntime = Initialize-StudioFont $resolvedStudioRoot $toolLock -Offline:$Offline
$runtime = [ordered]@{
    schema_version = 1
    platform = 'windows-x64'
    studio_root = $resolvedStudioRoot
    python = $pythonRuntime
    node = $nodeRuntime
    ffmpeg = $mediaRuntime
    font = $fontRuntime
    toolchain_lock_sha256 = Get-StudioHash $lockPath
    installation_scope = 'project-local .tools; existing user runtimes may be reused'
    credentials_copied = $false
    persistent_path_modified = $false
}
Write-StudioJson (Join-Path $resolvedStudioRoot '.local/runtime.json') $runtime
$runtime | ConvertTo-Json -Depth 20 -Compress
