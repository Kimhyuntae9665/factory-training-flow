param([string]$RuntimeDir=(Join-Path $PSScriptRoot '.runtime'))
$ErrorActionPreference='Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
 . ./scripts/runtime.ps1 -RuntimeDir $RuntimeDir
 & $taskNodeExe $taskN8nBin import:workflow --input=workflow.json
 if($LASTEXITCODE -ne 0){throw 'Workflow import failed.'}
 & $taskNodeExe $taskN8nBin publish:workflow --id=FactoryTrainingLocal01
 if($LASTEXITCODE -ne 0){throw 'Local workflow activation failed.'}
}finally{Pop-Location}
