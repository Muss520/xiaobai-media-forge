$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskClassified=(Split-Path $PSScriptRoot -Leaf) -eq '开发资料' -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot '..\project.marker'))
$taskProject=if ($taskClassified) { [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')) } else { $PSScriptRoot }
$taskRun=if ($taskClassified) { Join-Path $taskProject '运行数据' } else { $PSScriptRoot }
$taskDocs=if ($taskClassified) { Join-Path $taskProject '文档' } else { Join-Path $PSScriptRoot 'docs' }
$taskRelease=if ($taskClassified) { Join-Path $taskProject '发布包' } else { $PSScriptRoot }
$taskLicenses=Join-Path $taskDocs 'licenses'
New-Item -ItemType Directory -Force -Path $taskRelease | Out-Null
$env:TEMP = Join-Path $taskRun 'temp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot 'downloads\pip-cache'
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot 'build\pyinstaller-cache'
New-Item -ItemType Directory -Force -Path $env:TEMP, (Join-Path $PSScriptRoot 'tools'), (Join-Path $PSScriptRoot 'downloads') | Out-Null
$portableResources = Join-Path $PSScriptRoot '..\_internal'
if (Test-Path -LiteralPath $portableResources) {
    foreach ($engineFile in @('ffmpeg.exe','ffprobe.exe','exiftool.exe')) {
        $localEngine = Join-Path $PSScriptRoot ('tools\' + $engineFile)
        if (-not (Test-Path -LiteralPath $localEngine)) {
            Copy-Item -LiteralPath (Join-Path $portableResources ('tools\' + $engineFile)) -Destination $localEngine
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'tools\exiftool_files'))) {
        Copy-Item -LiteralPath (Join-Path $portableResources 'tools\exiftool_files') -Destination (Join-Path $PSScriptRoot 'tools\exiftool_files') -Recurse
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'assets') | Out-Null
    foreach ($assetFile in @('mediaforge.ico','NotoSansCJKsc-Regular.otf')) {
        $localAsset = Join-Path $PSScriptRoot ('assets\' + $assetFile)
        if (-not (Test-Path -LiteralPath $localAsset)) {
            Copy-Item -LiteralPath (Join-Path $portableResources ('assets\' + $assetFile)) -Destination $localAsset
        }
    }
}
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $localPython = Join-Path $PSScriptRoot 'runtime\python.exe'
    if (Test-Path -LiteralPath $localPython) { & $localPython -m venv '.\.venv' }
    else { & py -3.12 -m venv '.\.venv' }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 environment creation failed' }
}
if (Test-Path -LiteralPath '.\downloads\wheels') { & $taskPython -m pip install --no-index --find-links '.\downloads\wheels' -r '.\requirements.lock.txt' }
else { & $taskPython -m pip install -r '.\requirements.lock.txt' }
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$taskBrandJson = & $taskPython -c "import sys,json;sys.path.insert(0,'src');from mediaforge.product import NAME,EXE_NAME,ARCHIVE_NAME,LAUNCHER_NAME;print(json.dumps(dict(name=NAME,exe=EXE_NAME,archive=ARCHIVE_NAME,launcher=LAUNCHER_NAME)))"
if ($LASTEXITCODE -ne 0) { throw 'Cannot load product information' }
$taskProduct = $taskBrandJson | ConvertFrom-Json
if (-not (Test-Path -LiteralPath '.\tools\exiftool.exe')) {
    $exifManifest = Get-Content -LiteralPath '.\tools\exiftool-manifest.json' -Raw | ConvertFrom-Json
    $exifArchive = '.\downloads\exiftool-13.59_64.zip'
    if (-not (Test-Path -LiteralPath $exifArchive)) { Invoke-WebRequest -Uri $exifManifest.url -OutFile $exifArchive }
    if ((Get-FileHash -LiteralPath $exifArchive -Algorithm SHA256).Hash -ne $exifManifest.sha256) { throw 'ExifTool archive checksum mismatch' }
    Expand-Archive -LiteralPath $exifArchive -DestinationPath '.\tools\exiftool-package' -Force
    Copy-Item -LiteralPath '.\tools\exiftool-package\ExifTool.exe' -Destination '.\tools\exiftool.exe'
    Copy-Item -LiteralPath '.\tools\exiftool-package\exiftool_files' -Destination '.\tools\exiftool_files' -Recurse -Force
}
if (-not (Test-Path -LiteralPath '.\tools\ffmpeg.exe')) {
    $archive = '.\downloads\ffmpeg-release-essentials.zip'
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $archive
    }
    $manifest = Get-Content -LiteralPath '.\tools\ffmpeg-manifest.json' -Raw | ConvertFrom-Json
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $manifest.archive_sha256) {
        throw 'FFmpeg archive checksum differs from the pinned build. Obtain the matching 9.0.2 archive.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath '.\tools\ffmpeg-distribution' -Force
    Get-ChildItem -LiteralPath '.\tools\ffmpeg-distribution' -Recurse -Filter '*.exe' | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination '.\tools'
    }
}
$testFolder = Join-Path $taskRun ('temp\build-tests-' + [Guid]::NewGuid().ToString('N'))
& $taskPython -m pytest --basetemp $testFolder -p no:cacheprovider -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; packaging stopped' }
$ffmpegBinary = (Join-Path $PSScriptRoot 'tools\ffmpeg.exe') + ';tools'
$ffprobeBinary = (Join-Path $PSScriptRoot 'tools\ffprobe.exe') + ';tools'
$exifBinary = (Join-Path $PSScriptRoot 'tools\exiftool.exe') + ';tools'
$exifData = (Join-Path $PSScriptRoot 'tools\exiftool_files') + ';tools\exiftool_files'
$assetData = (Join-Path $PSScriptRoot 'assets') + ';assets'
$iconFile = Join-Path $PSScriptRoot 'assets\mediaforge.ico'
$sourcePath = Join-Path $PSScriptRoot 'src'
& $taskPython '.\scripts\make_version_info.py'
if ($LASTEXITCODE -ne 0) { throw 'Windows version information failed' }
$taskVersionFile=Join-Path $PSScriptRoot 'build\version-info.txt'
& $taskPython -m PyInstaller --noconfirm --clean --windowed --onedir --name $taskProduct.name --version-file $taskVersionFile --icon $iconFile --paths $sourcePath --add-binary $ffmpegBinary --add-binary $ffprobeBinary --add-binary $exifBinary --add-data $exifData --add-data $assetData --collect-all pillow_heif --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --distpath '.\build\staging' --workpath '.\build\pyinstaller' --specpath '.\build' '.\src\main.py'
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
$builtFolder = Join-Path (Join-Path $PSScriptRoot 'build\staging') $taskProduct.name
& $taskPython '.\scripts\prune_bundle.py' $builtFolder
if ($LASTEXITCODE -ne 0) { throw 'Bundle dependency cleanup failed' }
$portableFolder = if ($taskClassified) { Join-Path $taskProject '软件程序\MediaForge' } else { Join-Path $PSScriptRoot '成品\MediaForge' }
$taskPublishAbsolute=[IO.Path]::GetFullPath($portableFolder)
if (-not $taskPublishAbsolute.StartsWith($taskProject+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected portable output path' }
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($taskPublishAbsolute)) | Out-Null
if (Test-Path -LiteralPath $portableFolder) {
    # Overwrite generated payload only; retain user data/media in the portable folder.
    Copy-Item -LiteralPath (Join-Path $builtFolder $taskProduct.exe) -Destination $portableFolder -Force
    Copy-Item -LiteralPath (Join-Path $builtFolder '_internal') -Destination $portableFolder -Recurse -Force
} else {
    Move-Item -LiteralPath $builtFolder -Destination $portableFolder
}
Copy-Item -LiteralPath (Join-Path $taskDocs '使用说明.txt'),(Join-Path $taskDocs 'LICENSE.txt') -Destination $portableFolder
Copy-Item -LiteralPath $taskLicenses -Destination $portableFolder -Recurse -Force
$sourcePackage = Join-Path $portableFolder '源码'
New-Item -ItemType Directory -Force -Path $sourcePackage | Out-Null
Copy-Item -LiteralPath '.\src','.\tests','.\scripts' -Destination $sourcePackage -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $sourcePackage 'docs') | Out-Null
Get-ChildItem -LiteralPath $taskDocs -Force | Copy-Item -Destination (Join-Path $sourcePackage 'docs') -Recurse -Force
Copy-Item -LiteralPath '.\requirements.lock.txt','.\pytest.ini','.\build.ps1',(Join-Path $taskDocs 'LICENSE.txt'),(Join-Path $taskDocs '使用说明.txt') -Destination $sourcePackage
Copy-Item -LiteralPath '.\requirements-dev.lock.txt' -Destination $sourcePackage
New-Item -ItemType Directory -Force -Path (Join-Path $sourcePackage 'assets') | Out-Null
Copy-Item -LiteralPath '.\assets\xiaobai-frames.png','.\assets\xiaobai-logo.png','.\assets\xiaobai-atlas.png','.\assets\xiaobai-states.json','.\assets\mediaforge.ico','.\assets\mediaforge.png','.\assets\pixel-cat-sheet.png','.\assets\chevron-down.svg','.\assets\chevron-up.svg','.\assets\check.svg' -Destination (Join-Path $sourcePackage 'assets')
Copy-Item -LiteralPath '.\assets\xiaobai-actions-38-source.png' -Destination (Join-Path $sourcePackage 'assets')
Copy-Item -LiteralPath '.\assets\chevron-left.svg','.\assets\chevron-right.svg' -Destination (Join-Path $sourcePackage 'assets')
Copy-Item -LiteralPath '.\assets\sounds' -Destination (Join-Path $sourcePackage 'assets') -Recurse -Force
Copy-Item -LiteralPath '.\assets\support' -Destination (Join-Path $sourcePackage 'assets') -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $sourcePackage 'tools') | Out-Null
Copy-Item -LiteralPath '.\tools\ffmpeg-manifest.json','.\tools\exiftool-manifest.json' -Destination (Join-Path $sourcePackage 'tools')
Copy-Item -LiteralPath $taskLicenses -Destination $sourcePackage -Recurse -Force
# The included build script reuses binaries/font from ../_internal to avoid duplicate payloads.
& $taskPython '.\scripts\verify_portable.py'
if ($LASTEXITCODE -ne 0) { throw 'Native portable media verification failed; ZIP stopped' }
& $taskPython '.\scripts\verify_moved.py'
if ($LASTEXITCODE -ne 0) { throw 'Relocated portable verification failed; ZIP stopped' }
# Remove only the confirmed legacy generated executable, after the replacement passes.
$legacyExecutable=Join-Path $portableFolder '媒体工坊.exe'
if ($taskProduct.exe -ne '媒体工坊.exe' -and (Test-Path -LiteralPath $legacyExecutable)) {
    Remove-Item -LiteralPath $legacyExecutable
}
if ($taskClassified) {
    $taskLauncherLines=@('@echo off','chcp 65001 >nul','cd /d "%~dp0"',('start "" "%~dp0软件程序\MediaForge\'+$taskProduct.exe+'"'))
    [IO.File]::WriteAllText((Join-Path $taskProject $taskProduct.launcher),($taskLauncherLines -join "`r`n")+"`r`n",[Text.UTF8Encoding]::new($false))
    $legacyLauncher=Join-Path $taskProject '启动媒体工坊.cmd'
    if (Test-Path -LiteralPath $legacyLauncher) { Remove-Item -LiteralPath $legacyLauncher }
}
# Include the report generated by the actual EXE, not a source-only report.
Copy-Item -LiteralPath (Join-Path $taskDocs '成品启动验证.json'),(Join-Path $taskDocs '移动目录验证.json'),(Join-Path $taskDocs '成品界面.png'),(Join-Path $taskDocs '成品小猫设置.png'),(Join-Path $taskDocs '成品信息模式.png') -Destination (Join-Path $sourcePackage 'docs') -Force
Get-ChildItem -LiteralPath $taskDocs -Filter '成品*二维码*.png' | Copy-Item -Destination (Join-Path $sourcePackage 'docs') -Force
Get-ChildItem -LiteralPath $taskDocs -Filter '成品收款码_*.png' | Copy-Item -Destination (Join-Path $sourcePackage 'docs') -Force
Copy-Item -LiteralPath (Join-Path $taskDocs '成品作者与打赏.png') -Destination (Join-Path $sourcePackage 'docs') -Force
foreach ($taskShot in @('成品声音设置.png','成品逗猫棒.png','成品抛接球.png')) {
    Copy-Item -LiteralPath (Join-Path $taskDocs $taskShot) -Destination (Join-Path $sourcePackage 'docs') -Force
}
& $taskPython '.\scripts\archive.py' $portableFolder (Join-Path $taskRelease $taskProduct.archive)
if ($LASTEXITCODE -ne 0) { throw 'ZIP creation failed' }
$zipHash = (Get-FileHash -LiteralPath (Join-Path $taskRelease $taskProduct.archive) -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $taskRelease ([IO.Path]::ChangeExtension($taskProduct.archive,'.sha256'))) -Value ($zipHash + '  '+$taskProduct.archive) -Encoding utf8
if ($taskProduct.archive -ne 'MediaForge-Windows-x64.zip') {
    foreach ($legacyRelease in @('MediaForge-Windows-x64.zip','MediaForge-Windows-x64.sha256')) {
        $legacyReleasePath=Join-Path $taskRelease $legacyRelease
        if (Test-Path -LiteralPath $legacyReleasePath) { Remove-Item -LiteralPath $legacyReleasePath }
    }
}
Write-Host ('Build ready: '+(Join-Path $portableFolder $taskProduct.exe))
