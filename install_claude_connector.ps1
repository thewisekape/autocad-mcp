# install_claude_connector.ps1
# Installs the AutoCAD MCP server as a connector in Claude Desktop.
# Run this script once after cloning the repo.

param(
    [ValidateSet("autocad", "zwcad", "gcad", "bricscad", "ezdxf")]
    [string]$CadType = "autocad",

    [switch]$Headless,   # Force ezdxf backend (no live CAD required)
    [switch]$Force       # Overwrite existing config without prompting
)

$ErrorActionPreference = "Stop"

# ── Paths ────────────────────────────────────────────────────────────────────

$ProjectDir   = $PSScriptRoot
$ClaudeConfig = "$env:APPDATA\Claude\claude_desktop_config.json"
$UvExe        = (Get-Command uv -ErrorAction SilentlyContinue)?.Source

if (-not $UvExe) {
    # Fallback to known install location
    $UvExe = "$env:USERPROFILE\.local\bin\uv.exe"
}

if (-not (Test-Path $UvExe)) {
    Write-Error "uv not found. Install it from https://github.com/astral-sh/uv then re-run."
    exit 1
}

# ── Backend selection ─────────────────────────────────────────────────────────

$backend = if ($Headless) { "ezdxf" } else { "com" }

$serverEntry = @{
    command = $UvExe
    args    = @("--directory", $ProjectDir, "run", "python", "-m", "autocad_mcp")
    env     = @{
        AUTOCAD_MCP_BACKEND    = $backend
        AUTOCAD_MCP_IPC_TIMEOUT = "30.0"
        AUTOCAD_MCP_ONLY_TEXT  = "false"
    }
}

if ($backend -eq "com") {
    $serverEntry.env["AUTOCAD_MCP_CAD_TYPE"] = $CadType
}

$serverKey = if ($Headless) { "autocad-headless" } else { "autocad" }

# ── Load or create claude_desktop_config.json ─────────────────────────────────

$claudeDir = Split-Path $ClaudeConfig
if (-not (Test-Path $claudeDir)) {
    New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null
    Write-Host "Created Claude config directory: $claudeDir"
}

$config = if (Test-Path $ClaudeConfig) {
    Get-Content $ClaudeConfig -Raw | ConvertFrom-Json -AsHashtable
} else {
    @{}
}

if (-not $config.ContainsKey("mcpServers")) {
    $config["mcpServers"] = @{}
}

# ── Check for existing entry ───────────────────────────────────────────────────

if ($config["mcpServers"].ContainsKey($serverKey) -and -not $Force) {
    $answer = Read-Host "Server '$serverKey' already exists in Claude config. Overwrite? [y/N]"
    if ($answer -notmatch '^[Yy]') {
        Write-Host "Aborted. Use -Force to skip this prompt."
        exit 0
    }
}

$config["mcpServers"][$serverKey] = $serverEntry

# ── Write config ──────────────────────────────────────────────────────────────

$config | ConvertTo-Json -Depth 10 | Set-Content $ClaudeConfig -Encoding UTF8

Write-Host ""
Write-Host "✓ AutoCAD MCP connector installed successfully." -ForegroundColor Green
Write-Host ""
Write-Host "  Server key : $serverKey"
Write-Host "  Backend    : $backend"
if ($backend -eq "com") {
    Write-Host "  CAD type   : $CadType"
}
Write-Host "  Config     : $ClaudeConfig"
Write-Host ""
Write-Host "Restart Claude Desktop for changes to take effect."
Write-Host ""
Write-Host "Available -CadType values: autocad, zwcad, gcad, bricscad"
Write-Host "Use -Headless for DXF-only mode (no running CAD application needed)."
