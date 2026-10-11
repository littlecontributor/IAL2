<#
==============================================================================
 IA LOCALE - VERIFICATION COMPLETE V2 (clé en main)
==============================================================================
 Nouveau flux :
   1. Diagnostic initial (preflight --json + texte)
   2. Verification venv / Python
   3. Verification dependances (vrai import)
   4. Ollama binaire + serveur + modeles
   5. Port
   6. Test de demarrage reel (import modules + HTTP 200)
   7. [Option -IA] Test IA locale, modèles, voix et images
   8. Re-diagnostic final + BILAN

 Options :
   .\TEST.ps1           # verification complete
   .\TEST.ps1 -Fast     # sans test HTTP
   .\TEST.ps1 -IA       # + simulation IA
   .\TEST.ps1 -Fix      # tente auto-fix des dépendances (sans téléchargement automatique de modèle)

 ASCII only.
==============================================================================
#>

[CmdletBinding()]
param([switch]$Fast, [switch]$IA, [switch]$Fix)

$PROJECT_DIR = $PSScriptRoot
$VENV_PY     = Join-Path $PROJECT_DIR ".venv\Scripts\python.exe"
$CONFIG_FILE = Join-Path $PROJECT_DIR "config\config.yaml"
$TEMP_DIR = if ($env:TEMP) { $env:TEMP } elseif ($env:TMP) { $env:TMP } else { [System.IO.Path]::GetTempPath() }

function Get-TempFile { param([string]$Name) try { $p=Join-Path $TEMP_DIR $Name; [void][System.IO.Path]::GetFullPath($p); return $p } catch { return Join-Path $PROJECT_DIR $Name } }

$script:Fails=0; $script:Warns=0
function Step($m) { Write-Host "`n[$m]" -ForegroundColor Cyan }
function OK($m)   { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]    $m" -ForegroundColor Yellow; $script:Warns++ }
function Fail($m) { Write-Host "  [ERR]  $m" -ForegroundColor Red; $script:Fails++ }

Clear-Host
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   IA LOCALE - VERIFICATION COMPLETE V2" -ForegroundColor White
Write-Host "   Diagnostic -> Test reel -> Re-diagnostic" -ForegroundColor Gray
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   Projet : $PROJECT_DIR"

# 1. Fichiers
Step "1/8 - Fichiers du projet"
$files = @("ui\futuristic_app.py","ui\futuristic_theme.py","config\config.yaml","scripts\llm.py","scripts\model_catalog.py","scripts\hardware_profile.py","scripts\ai_model_manager.py","tests\test_hardware_profile.py","tests\test_rag_embeddings.py","scripts\tts.py","scripts\stt.py","scripts\rag.py","scripts\project_paths.py","preflight.py","auto_install.py","requirements.txt","install_all_ai.py","GUIDE_CODE_LOCAL.md","scripts\create_python_app.py","templates\python_desktop_app\main.py","templates\python_desktop_app\build_exe.py","templates\python_desktop_app\requirements-build.txt","tests\test_app_scaffold.py")
foreach ($f in $files) { if (Test-Path (Join-Path $PROJECT_DIR $f)) { OK $f } else { Fail "$f introuvable" } }

# 2. Python
Step "2/8 - Python"
$PY=$null
if (Test-Path $VENV_PY) { $PY=$VENV_PY; OK "venv : .venv\Scripts\python.exe" }
else {
    Warn "venv absent (lancez .\INSTALL.ps1)"
    $sys=Get-Command python -ErrorAction SilentlyContinue
    if ($sys) { $PY=$sys.Source; OK "Python systeme : $($sys.Source)" } else { Fail "Aucun Python" }
}
if ($PY) {
    $pyver=& $PY -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
    if ($pyver) {
        if ([version]$pyver -ge [version]"3.11.0") { OK "Version Python : $pyver" }
        elseif ([version]$pyver -ge [version]"3.10.0") { Warn "Python $pyver (3.11+ recommande)" }
        else { Fail "Python $pyver trop ancien" }
    }
}

# 3. Diagnostic preflight JSON (nouveau)
Step "3/8 - Diagnostic preflight (JSON + texte)"
if ($PY -and (Test-Path (Join-Path $PROJECT_DIR "preflight.py"))) {
    Write-Host "  Lancement preflight.py --json ..." -ForegroundColor Gray
    $jsonOut = & $PY (Join-Path $PROJECT_DIR "preflight.py") --json 2>&1 | Out-String
    try {
        $report = $jsonOut | ConvertFrom-Json
        if ($report.ready) { OK "Preflight : pret a demarrer" } else { Warn "Preflight : corrections necessaires" }
        Write-Host "    Python : $($report.python.version) - $(if ($report.python.ok) {'OK'} else {'KO'})" -ForegroundColor Gray
        Write-Host "    Fichiers : $(if ($report.files.ok) {'OK'} else {'KO'})" -ForegroundColor Gray
        Write-Host "    Packages requis : $(if ($report.packages.ok) {'OK'} else {'MANQUE'})" -ForegroundColor Gray
        if ($report.packages.missing_required) { Warn "    Manquants requis : $($report.packages.missing_required -join ', ')" }
        if ($report.packages.broken_required) { Warn "    Casses : $($report.packages.broken_required -join ', ')" }
        Write-Host "    Ollama : $(if ($report.ollama.ok) {'OK'} else {'KO'}) - $($report.ollama.models.Count) modeles" -ForegroundColor Gray
        Write-Host "    Port $($report.port.port) : $(if ($report.port.free) {'libre'} else {'utilise'})" -ForegroundColor Gray
    } catch {
        Warn "Sortie JSON illisible, affichage texte :"
        & $PY (Join-Path $PROJECT_DIR "preflight.py")
    }

    if ($Fix) {
        Write-Host "`n  Mode -Fix : tentative auto-correction..." -ForegroundColor Yellow
        & $PY (Join-Path $PROJECT_DIR "preflight.py") --auto-fix
        if (Test-Path (Join-Path $PROJECT_DIR "auto_install.py")) {
            Write-Host "  Lancement auto_install.py --core ..." -ForegroundColor Gray
            & $PY (Join-Path $PROJECT_DIR "auto_install.py") --core
        }
    }
} else { Fail "Impossible de lancer preflight.py" }

# 4. Dependances via import
Step "4/8 - Dependances Python (import)"
if ($PY) {
    $mods = @(
        @{ n="Interface web (gradio)"; i="gradio"; req=$true },
        @{ n="Client Ollama (ollama)"; i="ollama"; req=$true },
        @{ n="Configuration (PyYAML)"; i="yaml"; req=$true },
        @{ n="Monitoring (psutil)"; i="psutil"; req=$true },
        @{ n="HTTP (requests)"; i="requests"; req=$true },
        @{ n="Upload (python-multipart)"; i="multipart"; req=$true },
        @{ n="Calcul (numpy)"; i="numpy"; req=$true },
        @{ n="Images (Pillow)"; i="PIL"; req=$false },
        @{ n="STT (faster-whisper)"; i="faster_whisper"; req=$false },
        @{ n="TTS (piper)"; i="piper"; req=$false },
        @{ n="TTS (coqui)"; i="TTS"; req=$false },
        @{ n="Audio (sounddevice)"; i="sounddevice"; req=$false },
        @{ n="IA (torch)"; i="torch"; req=$false },
        @{ n="IA (transformers)"; i="transformers"; req=$false },
        @{ n="RAG (chromadb)"; i="chromadb"; req=$false },
        @{ n="RAG (sentence-transformers)"; i="sentence_transformers"; req=$false }
    )
    foreach ($m in $mods) {
        & $PY -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$($m.i)') else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { OK $m.n } elseif ($m.req) { Fail "$($m.n) - REQUIS" } else { Warn "$($m.n) - optionnel" }
    }
}

# 5. Ollama
Step "5/8 - Ollama"
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) { OK "Binaire : $($ollamaCmd.Source)" } else { Warn "Binaire ollama absent" }
$serverUp=$false
try { $resp=Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 4; $serverUp=$true; OK "Serveur actif (http://127.0.0.1:11434)" } catch { Warn "Serveur injoignable (sera demarre par START.ps1)" }
if ($serverUp) {
    try {
        $data=$resp.Content | ConvertFrom-Json; $count=@($data.models).Count
        if ($count -gt 0) { OK "$count modele(s)"; foreach ($m in $data.models) { Write-Host "         - $($m.name)" -ForegroundColor Gray } }
        else { Warn "Aucun modele : choisissez-en un dans IA Locale > Modeles IA ou via auto_install.py --models-only --model" }
    } catch { Warn "Reponse Ollama illisible" }
}

# 6. Port
Step "6/8 - Port interface"
$port=7860
try { $match=Select-String -Path $CONFIG_FILE -Pattern '^\s+port:\s*(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1; if ($match) { $port=[int]$match.Matches[0].Groups[1].Value } } catch { }
Write-Host "  Port configure : $port" -ForegroundColor Gray
$inUse=$false
try { $c=New-Object System.Net.Sockets.TcpClient; $c.Connect("127.0.0.1",$port); $inUse=$c.Connected; $c.Close() } catch { $inUse=$false }
if ($inUse) { Warn "Port deja utilise" } else { OK "Port $port libre" }

# 7. Test demarrage reel
Step "7/8 - Test demarrage reel de l'application"
if ($Fast) { Warn "Test ignore (-Fast)" }
elseif (-not $PY) { Fail "Sans Python impossible" }
else {
    Write-Host "  Import modules..." -ForegroundColor Gray
    $testScript = Get-TempFile "ia_locale_import_test.py"
    @'
import sys, os
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts"))
sys.path.insert(0, str(root / "ui"))
sys.path.insert(0, str(root))
errors=[]
for mod,label in [("stt","STT"),("tts","TTS"),("llm","LLM"),("rag","RAG")]:
    try: __import__(mod); print(f"  [OK]   module {label}")
    except Exception as e: print(f"  [!]    module {label} : {type(e).__name__}"); errors.append(mod)
try: import futuristic_theme; print("  [OK]   module theme")
except Exception as e: print(f"  [ERR]  module theme : {e}"); errors.append("theme")
print("IMPORT_TEST_OK" if "theme" not in errors else "IMPORT_TEST_FAIL")
'@ | Set-Content -Path $testScript -Encoding UTF8
    & $PY $testScript $PROJECT_DIR
    $importOk = ($LASTEXITCODE -eq 0)

    Write-Host "`n  Lancement temporaire serveur (max 60s)..." -ForegroundColor Gray
    $appFile = Join-Path $PROJECT_DIR "ui\futuristic_app.py"
    $outLog = Get-TempFile "ia_locale_out.log"
    $errLog = Get-TempFile "ia_locale_err.log"
    $startArgs = @{ FilePath=$PY; ArgumentList="`"$appFile`""; PassThru=$true; RedirectStandardOutput=$outLog; RedirectStandardError=$errLog }
    if ($env:OS -eq "Windows_NT") { $startArgs["WindowStyle"]="Hidden" }
    $proc = Start-Process @startArgs
    $httpOk=$false
    for ($i=0;$i -lt 30;$i++) {
        Start-Sleep -Seconds 2
        if (-not $proc -or $proc.HasExited) { break }
        try { $r=Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { $httpOk=$true; break } } catch { }
    }
    if ($httpOk) { OK "Serveur repond http://127.0.0.1:$port (200)" }
    elseif (-not $proc -or $proc.HasExited) {
        Fail "Application arretee (code $($proc.ExitCode))"
        Write-Host "`n  --- Logs ---" -ForegroundColor Gray
        foreach ($log in @($errLog,$outLog)) { if ($log -and (Test-Path $log)) { Get-Content $log -Tail 25 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray } } }
    } else { Warn "Pas de reponse HTTP en 60s" }

    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; OK "Instance test arretee" }
    Remove-Item $testScript -ErrorAction SilentlyContinue
}

# 7b. Test IA simulation
if ($IA) {
    Step "7b/8 - TEST IA (SIMULATION)"
    $iaScript = Join-Path $PROJECT_DIR "tests\test_ia.py"
    if (Test-Path $iaScript) {
        $iaLog = Join-Path $TEMP_DIR "local_ai_test_ia.log"
        Write-Host "  (Test Ollama + modèles locaux ~1min)" -ForegroundColor DarkGray
        & $PY $iaScript 2>&1 | Tee-Object -FilePath $iaLog
        if ($LASTEXITCODE -eq 0) { OK "Test IA : OK" } else { Fail "Test IA : echecs voir $iaLog" }
    } else { Warn "tests\test_ia.py introuvable" }
}

# 8. Re-diagnostic final
Step "8/8 - Re-diagnostic final"
if ($PY -and (Test-Path (Join-Path $PROJECT_DIR "preflight.py"))) {
    & $PY (Join-Path $PROJECT_DIR "preflight.py")
} else { Warn "preflight.py introuvable pour re-diag" }

# Bilan
Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   BILAN FINAL" -ForegroundColor White
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   Echecs : $script:Fails" -ForegroundColor $(if ($script:Fails -gt 0) { "Red" } else { "Green" })
Write-Host "   Avertissements : $script:Warns" -ForegroundColor $(if ($script:Warns -gt 0) { "Yellow" } else { "Green" })
Write-Host ""
if ($script:Fails -eq 0) { Write-Host "   RESULTAT : PRET A DEMARRER -> .\START.ps1" -ForegroundColor Green }
else { Write-Host "   RESULTAT : CORRECTIONS NECESSAIRES -> .\INSTALL.ps1 -Fix ou .\INSTALL.ps1 -Recreate" -ForegroundColor Red }
Write-Host ""
Read-Host "Entree pour fermer"
