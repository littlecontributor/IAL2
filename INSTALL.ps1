<#
==============================================================================
 IA LOCALE - INSTALLATION CLE EN MAIN V2
==============================================================================
 Correction demandée :
   "je préférerais que le diagnostique se lance, télécharge tout les
    composant, llm et prérequis, les installe, puis refasse un diagnostique
    afin que tout soit ok car la c'est brouillon"

 Nouveau flux PROPRE en 8 étapes :
   1. Diagnostic initial (preflight.py --json)
   2. Détection / création venv Python 3.11
   3. Installation des dépendances (core + vocal + RAG + génération d'images)
   4. Vérification VRAI import (détection wheels cassés + réinstall auto)
   5. Installation binaire Ollama (winget si dispo)
   6. Démarrage serveur Ollama
   7. Téléchargement d'un LLM uniquement si un modèle est explicitement choisi
   8. Re-diagnostic final -> BILAN VERT si tout OK

 Utilisation :
   .\INSTALL.ps1                 # installation complète clé en main
   .\INSTALL.ps1 -Core           # core uniquement (rapide)
   .\INSTALL.ps1 -Recreate       # recrée le venv de zéro
   .\INSTALL.ps1 -NoModels       # sans modèles LLM
   .\INSTALL.ps1 -Model qwen3.8:27b # choisir un autre modèle
   .\INSTALL.ps1 -DiagOnly       # diagnostic seul

 NOTE : ASCII uniquement pour éviter problèmes d'encodage PowerShell.
==============================================================================
#>

[CmdletBinding()]
param(
    [switch]$Core,
    [switch]$Recreate,
    [switch]$NoModels,
    [switch]$DiagOnly,
    [string[]]$Model = @()
)

$ErrorActionPreference = "Continue"
$PROJECT_DIR = $PSScriptRoot
$VENV_DIR    = Join-Path $PROJECT_DIR ".venv"

function Get-VenvPython {
    $win = Join-Path $VENV_DIR "Scripts\python.exe"
    if (Test-Path $win) { return $win }
    $nix = Join-Path $VENV_DIR "bin/python"
    if (Test-Path $nix) { return $nix }
    return $win
}
$VENV_PY = Get-VenvPython

function Write-Step($m)  { Write-Host "`n[$m]" -ForegroundColor Cyan }
function Write-OK($m)    { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Warn($m)  { Write-Host "  [!]    $m" -ForegroundColor Yellow }
function Write-Err($m)   { Write-Host "  [ERR]  $m" -ForegroundColor Red }
function Write-Info($m)  { Write-Host "         $m" -ForegroundColor Gray }

Clear-Host
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   IA LOCALE - INSTALLATION CLE EN MAIN V2" -ForegroundColor White
Write-Host "   Flux : Diagnostic -> Install tout -> Re-diagnostic" -ForegroundColor Gray
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   Dossier : $PROJECT_DIR"

# ------------------------------------------------------------------
# 0. Recherche Python 3.11
# ------------------------------------------------------------------
Write-Step "0/8 - Detection Python 3.11+"

function Find-Python311 {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python312\python.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($tag in @("-3.11","-3.12","-3")) {
            try {
                $out = & py $tag -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
            } catch { }
        }
    }
    $sys = Get-Command python -ErrorAction SilentlyContinue
    if ($sys) { return $sys.Source }
    return $null
}

$PY_BASE = Find-Python311
if (-not $PY_BASE) {
    Write-Err "Python introuvable."
    Write-Host "  Installez Python 3.11 : https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    Write-Host "  Cochez 'Add python.exe to PATH'" -ForegroundColor Yellow
    exit 1
}
Write-OK "Python detecte : $PY_BASE"
& $PY_BASE -c "import sys; print('  Version :', sys.version.split()[0])"

# ------------------------------------------------------------------
# 1. DIAGNOSTIC INITIAL (la nouveauté demandée)
# ------------------------------------------------------------------
Write-Step "1/8 - Diagnostic initial (preflight.py)"

$preflight = Join-Path $PROJECT_DIR "preflight.py"
$autoInstaller = Join-Path $PROJECT_DIR "auto_install.py"

if (-not (Test-Path $preflight)) {
    Write-Err "preflight.py introuvable"
    exit 1
}

# On lance le diagnostic avec le python systeme (venv peut ne pas exister encore)
& $PY_BASE $preflight
Write-Info "Diagnostic initial termine (voir ci-dessus les manques)"

if ($DiagOnly) {
    Write-Host "`n  Mode -DiagOnly : arret apres diagnostic" -ForegroundColor Yellow
    exit 0
}

# ------------------------------------------------------------------
# 2. VENV
# ------------------------------------------------------------------
Write-Step "2/8 - Environnement virtuel (.venv)"

if (Test-Path $autoInstaller) {
    # auto_install.py orchestre déjà le venv et toutes les étapes suivantes.
    # Ne pas créer un venv ici puis le supprimer/recréer une seconde fois.
    Write-Info "La creation, la verification et la reparation du .venv seront gerees une seule fois par auto_install.py."
} else {
    if ($Recreate -and (Test-Path $VENV_DIR)) {
        Write-Warn "Suppression ancien venv (-Recreate)..."
        Remove-Item $VENV_DIR -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path $VENV_PY)) {
        Write-Host "  Creation du venv..." -ForegroundColor Gray
        & $PY_BASE -m venv $VENV_DIR
        $VENV_PY = Get-VenvPython
        if (-not (Test-Path $VENV_PY)) {
            Write-Err "Echec creation venv"
            exit 1
        }
        Write-OK "venv cree : .venv"
    } else {
        Write-OK "venv deja present"
    }

    Write-Host "  Mise a jour pip..." -ForegroundColor Gray
    & $VENV_PY -m pip install --upgrade pip setuptools wheel --quiet
    Write-OK "pip a jour"
    $VPY = $VENV_PY
}

# ------------------------------------------------------------------
# 3. INSTALLATION DEPENDANCES - TOUT LES COMPOSANTS (demande utilisateur)
# ------------------------------------------------------------------
Write-Step "3/8 - Installation de TOUS les composants, prerequis et LLM"

# On delegue a auto_install.py qui fait tout proprement
if (Test-Path $autoInstaller) {
    Write-Host "  Lancement de l'orchestrateur Python (auto_install.py)..." -ForegroundColor Gray
    Write-Host "  Celui-ci va :" -ForegroundColor Gray
    Write-Host "    - Installer core + vocal + RAG + generation d'images" -ForegroundColor Gray
    Write-Host "    - Installer Ollama + un LLM si vous passez explicitement -Model" -ForegroundColor Gray
    Write-Host "    - Verifier les vrais imports" -ForegroundColor Gray
    Write-Host ""

    $argsList = @()
    if ($Core) { $argsList += "--core" }
    if ($NoModels) { $argsList += "--no-models" }
    if ($Recreate) { $argsList += "--recreate" }
    foreach ($modelName in $Model) { $argsList += @("--model", $modelName) }

    # Le script Python realise déjà l'installation complète, ses vrais imports
    # et le re-diagnostic final. Le lancer avec Python système lui permet aussi
    # de créer lui-même le venv lorsqu'il n'existe pas encore.
    & $PY_BASE $autoInstaller @argsList
    $autoInstallExitCode = $LASTEXITCODE

    if ($autoInstallExitCode -ne 0) {
        Write-Err "auto_install.py a echoue (code $autoInstallExitCode); consultez le diagnostic ci-dessus."
    }
    Write-Info "Installation et re-diagnostic termines par auto_install.py; aucune seconde passe PowerShell ne sera lancee."
    exit $autoInstallExitCode
} else {
    Write-Warn "auto_install.py introuvable, installation manuelle de secours"

    $GROUPS = @{
        Core    = @("gradio>=4.44.0,<6.0.0","gradio_client>=1.3.0","ollama>=0.4.0","PyYAML>=6.0.1","psutil>=5.9.0","requests>=2.31.0","python-multipart>=0.0.9","numpy>=1.26.0,<3.0.0","Pillow>=10.0.0")
        Vocal   = @("faster-whisper>=1.0.0","sounddevice>=0.4.6","soundfile>=0.12.1","pydub>=0.25.1","webrtcvad-wheels>=2.0.14","playsound>=1.2.2","piper-tts>=1.2.0")
        Rag     = @("chromadb>=0.4.24","sentence-transformers>=2.7.0","langchain>=0.2.0","langchain-community>=0.2.0","langchain-text-splitters>=0.2.0","pypdf>=4.2.0","docx2txt>=0.8")
        IA      = @("torch>=2.2.0","torchvision>=0.17.0","torchaudio>=2.2.0","transformers>=4.41.0","diffusers>=0.29.0","accelerate>=0.30.0")
    }

    function Install-Group($Name, $Pkgs) {
        Write-Host "`n  -- $Name --" -ForegroundColor Gray
        foreach ($pkg in $Pkgs) {
            Write-Host "     $pkg ..." -NoNewline -ForegroundColor Gray
            & $VPY -m pip install --prefer-binary --quiet $pkg 2>$null
            if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green } else { Write-Host " ECHEC (ignore)" -ForegroundColor Yellow }
        }
    }
    Install-Group "Core (obligatoire)" $GROUPS.Core
    if (-not $Core) {
        Install-Group "Vocal" $GROUPS.Vocal
        Install-Group "RAG" $GROUPS.Rag
        Install-Group "IA" $GROUPS.IA
    }
}

# ------------------------------------------------------------------
# 4. VERIFICATION VRAI IMPORT (anti-brouillon)
# ------------------------------------------------------------------
Write-Step "4/8 - Verification des imports reels (anti-brouillon)"

$corePkgs = @(
    @{ label="gradio"; pip="gradio>=4.44.0,<6.0.0"; imp="gradio" },
    @{ label="ollama"; pip="ollama"; imp="ollama" },
    @{ label="yaml"; pip="PyYAML"; imp="yaml" },
    @{ label="psutil"; pip="psutil"; imp="psutil" },
    @{ label="requests"; pip="requests"; imp="requests" },
    @{ label="multipart"; pip="python-multipart"; imp="multipart" },
    @{ label="numpy"; pip="numpy"; imp="numpy" },
    @{ label="PIL"; pip="Pillow"; imp="PIL" }
)

$broken = @()
foreach ($p in $corePkgs) {
    $importOutput = & $VPY -c "import $($p.imp); print('IMPORT_OK')" 2>&1
    $importExitCode = $LASTEXITCODE
    if ($importExitCode -eq 0) {
        Write-OK "$($p.label) importable"
        continue
    }

    Write-Warn "$($p.label) present mais import echoue; diagnostic avant reparation :"
    foreach ($line in @($importOutput | Select-Object -Last 8)) { Write-Info "$line" }
    Write-Host "  Reinstallation de $($p.pip) avec la contrainte du projet..." -ForegroundColor Gray
    & $VPY -m pip install --force-reinstall --no-cache-dir --prefer-binary $p.pip
    $repairExitCode = $LASTEXITCODE
    if ($repairExitCode -ne 0) { Write-Warn "pip a echoue pendant la reinstallation de $($p.label) (code $repairExitCode)." }

    $verifyOutput = & $VPY -c "import $($p.imp); print('IMPORT_OK')" 2>&1
    $verifyExitCode = $LASTEXITCODE
    if ($verifyExitCode -eq 0) {
        Write-OK "$($p.label) repare"
    } else {
        $broken += $p.label
        Write-Err "$($p.label) toujours casse apres reinstallation; diagnostic :"
        foreach ($line in @($verifyOutput | Select-Object -Last 8)) { Write-Info "$line" }
    }
}
if ($broken.Count -eq 0) { Write-OK "Tous les imports coeur OK" } else { Write-Err "Modules casses : $($broken -join ', ')" }

# ------------------------------------------------------------------
# 5. OLLAMA BINAIRE
# ------------------------------------------------------------------
Write-Step "5/8 - Ollama binaire"

$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    Write-OK "Ollama detecte : $($ollamaCmd.Source)"
} else {
    Write-Warn "Ollama absent, tentative installation via winget..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
        Start-Sleep -Seconds 5
        $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
        if ($ollamaCmd) { Write-OK "Ollama installe via winget" } else { Write-Warn "Echec winget, installez manuellement https://ollama.com/download" }
    } else {
        Write-Warn "winget absent, installez manuellement https://ollama.com/download"
    }
}

# ------------------------------------------------------------------
# 6. OLLAMA SERVEUR
# ------------------------------------------------------------------
Write-Step "6/8 - Ollama serveur"

function Test-Ollama {
    try { $null = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 3; return $true } catch { return $false }
}

if (Test-Ollama) {
    Write-OK "Serveur Ollama deja actif"
} elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "  Demarrage serveur Ollama..." -ForegroundColor Gray
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    $up = $false
    for ($i=0; $i -lt 20 -and -not $up; $i++) { Start-Sleep -Milliseconds 500; if (Test-Ollama) { $up = $true } }
    if ($up) { Write-OK "Serveur Ollama demarre" } else { Write-Warn "Ollama ne repond pas encore" }
} else {
    Write-Warn "Ollama non installe : chat LLM indisponible"
}

# ------------------------------------------------------------------
# 7. MODELE LLM (le pull principal est géré par auto_install.py)
# ------------------------------------------------------------------
Write-Step "7/8 - Modele local (telechargement sur choix explicite)"

if ($NoModels) {
    Write-Warn "Modeles ignores (-NoModels)"
} elseif ($Core -and $Model.Count -eq 0) {
    Write-Info "Mode -Core : aucun modele telecharge (installation rapide)"
} elseif (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Warn "Ollama absent : installez-le depuis https://ollama.com/download"
} elseif ($Model.Count -eq 0) {
    Write-Info "Aucun LLM telecharge automatiquement. Choisissez un modele dans l'onglet Modeles IA ou utilisez -Model."
} else {
    $safeInstall = "from scripts.ai_model_manager import install_ollama_model; import sys; raise SystemExit(0 if install_ollama_model(sys.argv[1]) else 1)"
    Push-Location $PROJECT_DIR
    foreach ($modelName in $Model) {
        Write-Host "  Installation explicite de $modelName via le gestionnaire materiel..." -ForegroundColor Gray
        & $VPY -c $safeInstall $modelName
        if ($LASTEXITCODE -eq 0) { Write-OK "Modele installe : $modelName" } else { Write-Warn "Modele ignore ou echec (catalogue/materiel/telechargement) : $modelName" }
    }
    Pop-Location
}

# ------------------------------------------------------------------
# 8. RE-DIAGNOSTIC FINAL (la correction la plus importante)
# ------------------------------------------------------------------
Write-Step "8/8 - Re-diagnostic final (validation que tout est OK)"

if (Test-Path $preflight) {
    Write-Host ""
    & $VPY $preflight
    $finalCode = $LASTEXITCODE

    Write-Host ""
    Write-Host "==============================================================================" -ForegroundColor Magenta
    if ($finalCode -eq 0) {
        Write-Host "   INSTALLATION 100% OK - PRET A DEMARRER" -ForegroundColor Green
        Write-Host "   Lancez : .\START.ps1  (ou double-clic START.bat)" -ForegroundColor Cyan
        Write-Host "   Interface : http://127.0.0.1:7860" -ForegroundColor Cyan
    } else {
        Write-Host "   INSTALLATION PARTIELLE - CORRECTIONS NECESSAIRES" -ForegroundColor Yellow
        Write-Host "   Relancez : .\INSTALL.ps1 -Recreate" -ForegroundColor Yellow
        Write-Host "   Diagnostic detaille : .\TEST.ps1" -ForegroundColor Yellow
    }
    Write-Host "==============================================================================" -ForegroundColor Magenta
} else {
    Write-Warn "preflight.py introuvable pour re-diagnostic"
}

Write-Host ""
Read-Host "Appuyez sur Entree pour fermer"
