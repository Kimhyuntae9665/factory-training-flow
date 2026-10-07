param([ValidateSet('n8n','portal','factory')][string]$Service='portal',[string]$RuntimeDir=(Join-Path $PSScriptRoot '.runtime'),[string]$ModelDir=(Join-Path $PSScriptRoot 'models/qwen2.5-1.5b'))
$ErrorActionPreference='Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
 if($Service -eq 'n8n') {
  . ./scripts/runtime.ps1 -RuntimeDir $RuntimeDir
  & $taskNodeExe $taskN8nBin start
 } else {
  $env:FACTORY_MODEL_DIR=(Resolve-Path -LiteralPath $ModelDir).Path
  $taskPython=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
  if(!(Test-Path -LiteralPath $taskPython)){$taskPython='python'}
  if($Service -eq 'portal'){& $taskPython -X utf8 adapter.py --port 8770}
  else{& $taskPython -X utf8 simulator/server.py --port 8771}
 }
}finally{Pop-Location}
