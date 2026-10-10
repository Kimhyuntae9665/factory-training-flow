param([switch]$ImportOnly,[string]$InstallDir,[string]$RunDir)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
$taskRuntime=if($RunDir){[System.IO.Path]::GetFullPath($RunDir)}else{Join-Path $taskRoot 'work/wonik-v3-runtime'}
$taskInstall=if($InstallDir){[System.IO.Path]::GetFullPath($InstallDir)}else{Join-Path $taskRoot 'work/n8n-runtime'}
$taskNodeDir=Join-Path $taskInstall 'node-v24.21.0-win-x64'
$taskNodeExe=Join-Path $taskNodeDir 'node.exe'
$taskN8nBin=Join-Path $taskInstall 'app/node_modules/n8n/bin/n8n'
$taskWorkflow=Join-Path (Split-Path $PSScriptRoot -Parent) 'workflow-learning.json'
$taskState=Join-Path $taskRuntime 'n8n-state'
New-Item -ItemType Directory -Path $taskState -Force | Out-Null
if(Get-NetTCPConnection -LocalPort 5697 -State Listen -ErrorAction SilentlyContinue){throw 'Port 5697 is already in use. Preserve the existing process.'}
if(Get-NetTCPConnection -LocalPort 5698 -State Listen -ErrorAction SilentlyContinue){throw 'Port 5698 is already in use. Preserve the existing process.'}
$env:Path="$taskNodeDir;$env:Path"
$env:N8N_USER_FOLDER=$taskState
$env:N8N_LISTEN_ADDRESS='127.0.0.1'
$env:N8N_HOST='127.0.0.1'
$env:N8N_PORT='5697'
$env:N8N_PROTOCOL='http'
$env:WEBHOOK_URL='http://127.0.0.1:5697/'
$env:N8N_EDITOR_BASE_URL='http://127.0.0.1:5697/'
$env:N8N_RUNNERS_BROKER_PORT='5698'
$env:N8N_DIAGNOSTICS_ENABLED='false'
$env:N8N_VERSION_NOTIFICATIONS_ENABLED='false'
$env:N8N_TEMPLATES_ENABLED='false'
$env:N8N_PERSONALIZATION_ENABLED='false'
$env:N8N_SECURE_COOKIE='true'
& $taskNodeExe $taskN8nBin import:workflow "--input=$taskWorkflow" *> (Join-Path $taskRuntime 'n8n-import.log')
if($LASTEXITCODE -ne 0){throw 'n8n workflow import failed; see the task import log.'}
& $taskNodeExe $taskN8nBin publish:workflow --id=WonikLearningV3Local *> (Join-Path $taskRuntime 'n8n-publish.log')
if($LASTEXITCODE -ne 0){throw 'n8n local workflow publish failed; see the task publish log.'}
if($ImportOnly){Write-Output 'Imported and locally published WonikLearningV3Local.';return}
$taskProcess=Start-Process -FilePath $taskNodeExe -ArgumentList @($taskN8nBin,'start') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskRuntime 'n8n-out.log') -RedirectStandardError (Join-Path $taskRuntime 'n8n-error.log')
$taskProcess.Id | Set-Content -LiteralPath (Join-Path $taskRuntime 'n8n.pid')
Write-Output "n8n localhost process started: PID $($taskProcess.Id), port 5697, task state $taskState"
