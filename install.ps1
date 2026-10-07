$ErrorActionPreference='Stop'
$taskRuntime=Join-Path $PSScriptRoot '.runtime'
New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null
$taskArchive=Join-Path $taskRuntime 'node-v24.21.0-win-x64.zip'
$taskNode=Join-Path $taskRuntime 'node-v24.21.0-win-x64'
if(!(Test-Path -LiteralPath (Join-Path $taskNode 'node.exe'))){
 Invoke-WebRequest -Uri 'https://nodejs.org/dist/v24.21.0/node-v24.21.0-win-x64.zip' -OutFile $taskArchive
 $taskHash=(Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256).Hash.ToLowerInvariant()
 if($taskHash -ne '158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541'){throw 'Node official archive hash mismatch.'}
 Expand-Archive -LiteralPath $taskArchive -DestinationPath $taskRuntime -Force
}
$env:Path="$taskNode;$env:Path"
& (Join-Path $taskNode 'npm.cmd') install --prefix (Join-Path $taskRuntime 'app') n8n@2.42.3 --no-audit --no-fund
if($LASTEXITCODE -ne 0){throw 'n8n installation failed.'}
& python -m venv (Join-Path $PSScriptRoot '.venv')
if($LASTEXITCODE -ne 0){throw 'Python environment creation failed.'}
$taskPython=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $taskPython -m pip install -r (Join-Path $PSScriptRoot 'simulator/requirements.txt') 'huggingface-hub==0.29.1'
if($LASTEXITCODE -ne 0){throw 'Python dependencies installation failed.'}
