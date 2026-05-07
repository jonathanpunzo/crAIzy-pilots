param(
    [string]$Config = "configs/best_lap.json",
    [int]$Port = 3001,
    [int]$Steps = 100000
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
Set-Location $root

py .\src\torcs_jm_par.py --config $Config --port $Port --steps $Steps
