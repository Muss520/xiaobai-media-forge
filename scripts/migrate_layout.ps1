$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'project.marker'))) { throw 'Missing project marker' }
$taskDev=Join-Path $taskRoot '开发资料'
if (Test-Path -LiteralPath $taskDev) { throw 'Layout already exists; inspect migration report before retrying' }
function Assert-TaskPath([string]$Path) {
    $resolved=[IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($taskRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw ('Path outside project: '+$resolved) }
    return $resolved
}
$taskMap=[ordered]@{}
foreach ($name in @('src','tests','assets','tools','runtime','.venv','downloads','build','scripts','requirements.lock.txt','pytest.ini','build.ps1')) { $taskMap[$name]='开发资料\'+$name }
foreach ($name in @('data','logs','temp')) { $taskMap[$name]='运行数据\'+$name }
$taskMap['成品\MediaForge']='软件程序\MediaForge'
$taskMap['成品\媒体工坊']='开发资料\build\staging\媒体工坊'
$taskMap['docs']='文档'
$taskMap['licenses']='文档\licenses'
$taskMap['LICENSE.txt']='文档\LICENSE.txt'
$taskMap['使用说明.txt']='文档\使用说明.txt'
$taskMap['MediaForge-Windows-x64.zip']='发布包\MediaForge-Windows-x64.zip'
$taskMap['MediaForge-Windows-x64.sha256']='发布包\MediaForge-Windows-x64.sha256'
$taskRecords=[Collections.Generic.List[object]]::new()
$taskUnreadable=@()
foreach ($entry in $taskMap.GetEnumerator()) {
    $source=Assert-TaskPath (Join-Path $taskRoot $entry.Key)
    if (-not (Test-Path -LiteralPath $source)) { continue }
    $files=if ((Get-Item -LiteralPath $source).PSIsContainer) {
        if ($entry.Key -in @('temp','build','downloads','.venv','成品\媒体工坊','成品\MediaForge')) { Get-ChildItem -LiteralPath $source -Recurse -File -Force -ErrorAction SilentlyContinue -ErrorVariable +taskUnreadable }
        else { Get-ChildItem -LiteralPath $source -Recurse -File -Force }
    } else { Get-Item -LiteralPath $source }
    foreach ($file in $files) {
        $suffix=$file.FullName.Substring($source.Length)
        $hash=$null
        if ($entry.Key -in @('src','tests','assets','data','output') -or ($entry.Key -eq 'tools' -and $file.Name -match '^(ffmpeg|ffprobe|exiftool)\.exe$') -or -not $file.PSIsContainer -and $file.Length -lt 400000 -and $entry.Key -notin @('.venv','temp','downloads','build','成品\媒体工坊','成品\MediaForge')) { $hash=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash }
        $taskRecords.Add([pscustomobject]@{source=$entry.Key+$suffix;target=$entry.Value+$suffix;bytes=$file.Length;sha256=$hash})
    }
}
$taskOutputs=@(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'output') -File -Recurse -Force | ForEach-Object { [pscustomobject]@{path=$_.FullName;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash} })
$manifest=Join-Path $taskRoot 'docs\3.6_迁移清单.json'
@{files=$taskRecords;outputs=$taskOutputs;unreadable_cache=@($taskUnreadable | ForEach-Object {$_.TargetObject.ToString()});phase='before'} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifest -Encoding utf8
foreach ($entry in $taskMap.GetEnumerator()) {
    $source=Assert-TaskPath (Join-Path $taskRoot $entry.Key);$target=Assert-TaskPath (Join-Path $taskRoot $entry.Value)
    if (-not (Test-Path -LiteralPath $source)) { continue }
    if (Test-Path -LiteralPath $target) { throw ('Unexpected existing target: '+$target) }
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($target)) | Out-Null
    if ((Get-Item -LiteralPath $source).PSIsContainer) { [IO.Directory]::Move($source,$target) }
    else { Move-Item -LiteralPath $source -Destination $target }
}
foreach ($record in $taskRecords) {
    $target=Assert-TaskPath (Join-Path $taskRoot $record.target)
    if ((Get-Item -LiteralPath $target).Length -ne $record.bytes) { throw ('File length mismatch: '+$target) }
    if ($record.sha256 -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $record.sha256) { throw ('Hash mismatch: '+$target) }
}
foreach ($file in $taskOutputs) { if ((Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash -ne $file.sha256) { throw 'Existing output changed' } }
$emptyOld=Assert-TaskPath (Join-Path $taskRoot '成品')
if ((Test-Path -LiteralPath $emptyOld) -and -not (Get-ChildItem -LiteralPath $emptyOld -Force)) { Remove-Item -LiteralPath $emptyOld }
@{passed=$true;files=$taskRecords.Count;hashed=@($taskRecords | Where-Object sha256).Count;outputs_unchanged=$true;phase='moved_before_venv_rebuild'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot '文档\3.6_目录迁移验证.json') -Encoding utf8
Write-Host ('Layout migration verified: '+$taskRecords.Count+' files')
