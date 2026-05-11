<#
.SYNOPSIS
  Append a row to the LinkedIn software-mining workbook.

.DESCRIPTION
  Thin PowerShell wrapper over tools\fill_mining_log.py. Uses native
  PowerShell parameter syntax so you do not have to deal with -- flags,
  caret continuation, or markdown-paste mangling.

.EXAMPLE
  .\tools\Fill-MiningLog.ps1 -Operator "Acme Resources" `
                             -Software Greasebook `
                             -Url "https://www.linkedin.com/in/jane-doe-12345" `
                             -Role "Production Superintendent" `
                             -Confidence high `
                             -Notes "quoted Greasebook in 2024 Permian post"

.EXAMPLE
  # Batch mode -- a JSON file of leads
  .\tools\Fill-MiningLog.ps1 -Batch .\leads.json
#>
param(
    [string]$Operator,

    [ValidateSet("Greasebook","WolfePak","Quorum","Enverus","PakEnergy","Spreadsheet","Other","Unknown")]
    [string]$Software,

    [string]$Url,
    [string]$Role,

    [ValidateSet("high","med","low")]
    [string]$Confidence,

    [string]$Notes,
    [string]$Date,
    [string]$Batch
)

$pyArgs = @()

if ($Batch) {
    $pyArgs += @("--batch", $Batch)
} else {
    if (-not $Operator) {
        Write-Error "Either -Operator or -Batch is required."
        exit 1
    }
    $pyArgs += @("--operator", $Operator)
    if ($Software)   { $pyArgs += @("--software",   $Software) }
    if ($Url)        { $pyArgs += @("--url",        $Url) }
    if ($Role)       { $pyArgs += @("--role",       $Role) }
    if ($Confidence) { $pyArgs += @("--confidence", $Confidence) }
    if ($Notes)      { $pyArgs += @("--notes",      $Notes) }
    if ($Date)       { $pyArgs += @("--date",       $Date) }
}

$script = Join-Path $PSScriptRoot "fill_mining_log.py"
& python $script @pyArgs
