<#
==============================================================================
 IA LOCALE - DEMARRAGE V2 (clé en main)
==============================================================================
 - Vérifie venv + dépendances via preflight --quiet
 - Démarre Ollama
 - Vérifie port
 - Lance l'interface Gradio
 - Si -Browser, ouvre le navigateur dès que HTTP 200

 Utilisation :
   .\START.ps1              # normal
   .\START.ps1 -Browser     # ouvre navigateur auto
   .\START.ps1 -Port 8080   # force port
   .\START.ps1 -SkipChecks  # ignore verifs

 ASCII only.
==============================================================================
#>

[CmdletBinding()]
param(
    [switch]$Browser,
    [int]$Port = 0,
    [switch]$SkipChecks
)

$PROJECT_DIR = $PSScriptRoot
function Get-VenvPython {
    $win = Join-Path $PROJECT_DIR ".venv\Scripts\python.exe"
    if (Test-Path $win) { return $win }
    $nix = Join-Path $PROJECT_DIR ".venv\bin/python"
    if (Test-Path $nix) { return $nix }
    return $win
}
$VENV_PY = Get-VenvPython
$APP_FILE = Join-Path $PROJECT_DIR "ui\futuristic_app.py"
$CONFIG_FILE = Join-Path $PROJECT_DIR "config\config.yaml"

function Say($m,$c="Gray") { Write-Host $m -ForegroundColor $c }
function Step($m) { Write-Host "`n[$m]" -ForegroundColor Cyan }
function OK($m)   { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]    $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  [ERR]  $m" -ForegroundColor Red }

Clear-Host
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   IA LOCALE - DEMARRAGE V2" -ForegroundColor White
Write-Host "==============================================================================" -ForegroundColor Magenta

# 1. Python
Step "1/5 - Environnement Python"
$PY = $null
if (Test-Path $VENV_PY) { $PY = $VENV_PY; OK "venv : .venv" }
else {
    Warn "venv absent, Python systeme"
    $sys = Get-Command python -ErrorAction SilentlyContinue
    if ($sys) { $PY = $sys.Source } else { Fail "Python introuvable. Lancez INSTALL.ps1"; Read-Host "Entree"; exit 1 }
}
& $PY -c "import sys; print('  Python', sys.version.split()[0], '-', sys.executable)"

# 2. Deps
if (-not $SkipChecks) {
    Step "2/5 - Verification dependances"
    $preflight = Join-Path $PROJECT_DIR "preflight.py"
    if (Test-Path $preflight) {
        & $PY $preflight --quiet
        if ($LASTEXITCODE -ne 0) {
            Fail "Dependances manquantes"
            Say ""; & $PY $preflight --fix; Say ""
            Say "  Corrigez : .\INSTALL.ps1" "Yellow"
            $ans = Read-Host "  Lancer INSTALL.ps1 maintenant ? (o/N)"
            if ($ans -match '^[oOyY]') {
                & (Join-Path $PROJECT_DIR "INSTALL.ps1")
                exit 0
            }
            Read-Host "Entree pour fermer"; exit 1
        }
        $gradioErr = & $PY -c "import gradio" 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Fail "gradio import impossible"
            $errLines = @($gradioErr -split "`r?`n" | Where-Object { $_.Trim() -ne "" })
            if ($errLines.Count -gt 0) { $errLines | Select-Object -Last 2 | ForEach-Object { Say "    $_" "Red" } }
            Say "  1) .\INSTALL.ps1 -Core" "Yellow"
            Say "  2) .\INSTALL.ps1 -Recreate -Core" "Yellow"
            Read-Host "Entree"; exit 1
        }
        OK "Dependances OK"
    } else { Warn "preflight.py introuvable" }
} else { Step "2/5 - Verifs ignorees" }

# 3. Ollama
Step "3/5 - Moteur LLM (Ollama)"
function Test-Ollama {
    try { $null = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 3; return $true } catch { return $false }
}
if (Test-Ollama) { OK "Ollama actif" }
elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
    Say "  Demarrage Ollama..." "Gray"
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    $up=$false; for ($i=0;$i -lt 20 -and -not $up;$i++) { Start-Sleep -Milliseconds 500; if (Test-Ollama) { $up=$true } }
    if ($up) { OK "Ollama demarre" } else { Warn "Ollama ne repond pas encore" }
} else { Warn "Ollama non installe : https://ollama.com/download" }

# 4. Port
Step "4/5 - Port interface"
$cfgPort = 7860
try {
    $line = Select-String -Path $CONFIG_FILE -Pattern '^\s+port:\s*(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($line) { $cfgPort = [int]$line.Matches[0].Groups[1].Value }
} catch { }
if ($Port -gt 0) {
    $cfgPort = $Port
    try {
        $content = Get-Content $CONFIG_FILE -Raw
        $content = [regex]::Replace($content, '(?m)^(\s+port:\s*)\d+', "`${1}$Port")
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText((Resolve-Path $CONFIG_FILE), $content, $utf8NoBom)
        OK "Port $Port ecrit dans config.yaml"
    } catch { Warn "Impossible modifier config.yaml" }
}
$inUse=$false
try { $c=New-Object System.Net.Sockets.TcpClient; $c.Connect("127.0.0.1",$cfgPort); $inUse=$c.Connected; $c.Close() } catch { $inUse=$false }
if ($inUse) {
    Warn "Port $cfgPort deja utilise"
    Say "  Interface existante : http://127.0.0.1:$cfgPort" "Cyan"
    $ans = Read-Host "  Lancer seconde instance ? (o/N)"
    if ($ans -notmatch '^[oOyY]') { exit 0 }
} else { OK "Port $cfgPort libre" }

try {
    netsh advfirewall firewall show rule name="IA Locale $cfgPort" | Out-Null
    if ($LASTEXITCODE -ne 0) { netsh advfirewall firewall add rule name="IA Locale $cfgPort" dir=in action=allow protocol=TCP localport=$cfgPort | Out-Null }
    if ($LASTEXITCODE -eq 0) { OK "Pare-feu port $cfgPort autorise" }
} catch { }

# 5. Lancement
Step "5/5 - Lancement interface"
if (-not (Test-Path $APP_FILE)) { Fail "ui\futuristic_app.py introuvable"; Read-Host "Entree"; exit 1 }
OK "Application : ui\futuristic_app.py"
Say ""
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   INTERFACE PRETE" -ForegroundColor Green
Write-Host "   URL : http://127.0.0.1:$cfgPort" -ForegroundColor Cyan
Write-Host "   (1ere requete 10-30s : chargement modeles)" -ForegroundColor Gray
Write-Host "   Arret : Ctrl+C" -ForegroundColor Gray
Write-Host "==============================================================================" -ForegroundColor Magenta
Say ""

$TEMP_DIR = if ($env:TEMP) { $env:TEMP } elseif ($env:TMP) { $env:TMP } else { [System.IO.Path]::GetTempPath() }
$readyFile = Join-Path $TEMP_DIR "local_ai_ready_$cfgPort.txt"
Remove-Item $readyFile -ErrorAction SilentlyContinue
$watchJob = Start-Job -ScriptBlock {
    param($p,$openBrowser,$readyFile)
    $ready=$false
    for ($i=0;$i -lt 150;$i++) {
        Start-Sleep -Seconds 2
        try {
            $r=Invoke-WebRequest -Uri "http://127.0.0.1:$p/" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) {
                if (-not $ready) { $ready=$true; Set-Content -Path $readyFile -Value "READY"; if ($openBrowser) { Start-Process "http://127.0.0.1:$p" } }
                continue
            }
        } catch { }
        if ($ready) { Set-Content -Path $readyFile -Value "GONE"; return }
    }
    if (-not $ready) { Set-Content -Path $readyFile -Value "TIMEOUT" }
} -ArgumentList $cfgPort, [bool]$Browser, $readyFile

$startTime = Get-Date
Push-Location (Split-Path $APP_FILE)
try { & $PY (Split-Path $APP_FILE -Leaf) }
finally { Pop-Location }
$elapsed = [int]((Get-Date)-$startTime).TotalSeconds

$watchJob | Stop-Job -ErrorAction SilentlyContinue | Out-Null
$watchJob | Remove-Job -Force -ErrorAction SilentlyContinue
$readyState="NO"
if (Test-Path $readyFile) { $readyState=(Get-Content $readyFile -Raw).Trim(); Remove-Item $readyFile -ErrorAction SilentlyContinue }

Say ""
if ($readyState -eq "READY") { Say "  Application arretee (page etait fonctionnelle)." "Yellow" }
elseif ($elapsed -lt 120) {
    Fail "Arret au bout de $elapsed s (demarrage echoue)."
    Say "  Diagnostic :" "Yellow"
    Say "   1. Voir erreurs console ci-dessus" "Yellow"
    Say "   2. .\INSTALL.ps1" "Yellow"
    Say "   3. .\TEST.ps1" "Yellow"
} else {
    Say "  Arretee apres $elapsed s sans reponse." "Yellow"
    Say "  1er lancement peut prendre 5 min (modeles lourds)." "Yellow"
}
Read-Host "Entree pour fermer"
