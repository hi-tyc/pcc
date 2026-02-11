param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root   = Resolve-Path $PSScriptRoot
$TestPS = Join-Path $Root "scripts\run_tests.ps1"

function Help {
  Write-Host "usage:"
  Write-Host "  pcc file.py [-o out.exe]"
  Write-Host "  pcc file.py -S        (emit C only)"
  Write-Host "  pcc file.py -c        (keep C)"
  Write-Host "  pcc --test            (run tests)"
  exit 0
}

$input=$null; $out=""; $S=$false; $c=$false; $test=$false
for ($i=0;$i -lt $Args.Count;$i++){
  switch ($Args[$i]){
    "--help" { Help }
    "--test" { $test=$true }
    "-S" { $S=$true; $c=$true }
    "-c" { $c=$true }
    "-o" { $i++; $out=$Args[$i] }
    default { if ($Args[$i].EndsWith(".py")) { $input=$Args[$i] } else { throw "unknown arg $($Args[$i])" } }
  }
}

if ($test) { & $TestPS; exit $LASTEXITCODE }
if (-not $input) { Help }

$input = (Resolve-Path $input).Path
$name  = [IO.Path]::GetFileNameWithoutExtension($input)
$cwd   = (Get-Location).Path
if ([string]::IsNullOrWhiteSpace($out)) {
  $exe = Join-Path $cwd ($name+".exe")
} else {
  $exe = Join-Path $cwd $out
}
$cfile = Join-Path $cwd ($name+".c")

& python -m pcc build $input -o $exe --toolchain auto
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$emitted = Join-Path $Root ("build\pcc_"+$name+"\main.c")
if (Test-Path $emitted) { Copy-Item -Force $emitted $cfile }

if ($S) { exit 0 }
if (-not $c) { Remove-Item -Force -ErrorAction SilentlyContinue $cfile | Out-Null }

Write-Host "[pcc] done -> $exe"