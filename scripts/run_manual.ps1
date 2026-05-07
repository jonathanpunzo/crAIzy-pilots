param(
    [int]$Port = 3001,
    [int]$Steps = 100000
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
Set-Location $root

py .\src\manual_control.py --port $Port --steps $Steps

