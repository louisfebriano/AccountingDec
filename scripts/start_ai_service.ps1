<#
.SYNOPSIS
  Menjalankan layanan CatatKas lokal (API + Llama + Whisper + OCR) dan
  Cloudflare Tunnel agar server Render dapat memanggilnya.

.DESCRIPTION
  Skrip ini hanya untuk LAPTOP, bukan untuk Render.
  - Uvicorn di-bind ke 127.0.0.1 agar tidak terbuka ke jaringan lokal.
  - cloudflared membuat koneksi keluar ke Cloudflare, jadi laptop tidak perlu
    port forwarding atau IP publik.
  - Tanpa -TunnelName, skrip memakai quick tunnel (URL acak *.trycloudflare.com
    yang berubah setiap kali dijalankan).

.EXAMPLE
  .\scripts\start_ai_service.ps1 -TunnelName catatkas-ai

.EXAMPLE
  .\scripts\start_ai_service.ps1 -NoWarmup
#>
[CmdletBinding()]
param(
    [string]$TunnelName = "",
    [int]$Port = 8000,
    [switch]$NoWarmup,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Assert-Ready {
    param([bool]$Condition, [string]$Message, [string]$Fix)
    if (-not $Condition) {
        Write-Host "GAGAL: $Message" -ForegroundColor Red
        if ($Fix) { Write-Host "  Perbaikan: $Fix" -ForegroundColor Yellow }
        exit 1
    }
}

function Test-Interpreter {
    # True bila interpreter ada dan dapat mengimpor uvicorn + fastapi.
    param([string]$Exe)
    if (-not $Exe -or -not (Test-Path $Exe)) { return $false }
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Exe -c "import uvicorn, fastapi" *> $null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousEap
    return ($exitCode -eq 0)
}

function Get-TorchStatus {
    # 0 = CUDA siap, 2 = torch belum terpasang, 3 = torch tanpa CUDA, 1 = gagal lain.
    param([string]$Exe)
    $probe = @'
import sys
try:
    import torch
except ImportError:
    sys.exit(2)
sys.exit(0 if torch.cuda.is_available() else 3)
'@
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Exe -c $probe *> $null
    $status = $LASTEXITCODE
    $ErrorActionPreference = $previousEap
    if ($null -eq $status) { return 1 }
    return $status
}

function Resolve-RealPython {
    # Windows menyajikan python.exe sebagai alias; ambil path interpreter sebenarnya.
    param([string]$Exe)
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $resolved = (& $Exe -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
    $ErrorActionPreference = $previousEap
    if ($resolved) { return $resolved.Trim() }
    return $Exe
}

function Find-PythonInterpreters {
    # Kumpulkan kandidat interpreter di mesin ini. Penting: saat .venv aktif,
    # "python" di PATH menunjuk ke .venv, jadi PATH saja tidak cukup.
    $paths = [System.Collections.Generic.List[string]]::new()
    $add = {
        param($candidate)
        if (-not $candidate) { return }
        $candidate = $candidate.Trim().Trim('"')
        if (-not $candidate) { return }
        if (-not (Test-Path -LiteralPath $candidate)) { return }
        $resolved = Resolve-RealPython $candidate
        if ($paths -notcontains $resolved) { $paths.Add($resolved) }
    }

    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    # 1. Python Launcher: daftar semua instalasi terdaftar (paling akurat).
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($line in (& py -0p 2>$null)) {
            if ($line -match '([A-Za-z]:\\.*?python\.exe)\s*$') { & $add $matches[1] }
        }
    }

    # 2. Semua python di PATH (where mengembalikan lebih dari satu).
    foreach ($line in (& where.exe python 2>$null)) {
        if ($line -and $line -notmatch '^INFO:') { & $add $line }
    }

    # 3. Lokasi instalasi umum di Windows.
    $roots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        "C:\Python3",
        "C:\Program Files\Python3"
    )
    foreach ($root in $roots) {
        if (-not $root -or -not (Test-Path $root)) { continue }
        foreach ($directory in (Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue)) {
            & $add (Join-Path $directory.FullName "python.exe")
        }
        & $add (Join-Path $root "python.exe")
    }

    $ErrorActionPreference = $previousEap
    return $paths
}

# Pilih interpreter yang punya uvicorn + fastapi DAN PyTorch CUDA.
# Urutan: -Python eksplisit, .venv, lalu interpreter lain yang ditemukan.
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$candidates = [System.Collections.Generic.List[string]]::new()

if ($Python) {
    Assert-Ready (Test-Path $Python) "Interpreter tidak ditemukan: $Python" "Periksa kembali nilai -Python"
    $candidates.Add((Resolve-Path $Python).Path)
} else {
    if (Test-Path $venvPython) { $candidates.Add($venvPython) }
    foreach ($found in (Find-PythonInterpreters)) {
        if ($found -and $candidates -notcontains $found) { $candidates.Add($found) }
    }
}

$pythonExe = $null
$rejected = @()
foreach ($candidate in $candidates) {
    Write-Host "Memeriksa interpreter: $candidate" -ForegroundColor DarkGray
    if (-not (Test-Interpreter $candidate)) {
        $rejected += "$candidate : uvicorn/fastapi tidak terpasang"
        continue
    }
    $torchStatus = Get-TorchStatus $candidate
    if ($torchStatus -eq 2) {
        $rejected += "$candidate : PyTorch belum terpasang"
        continue
    }
    if ($torchStatus -ne 0) {
        $rejected += "$candidate : PyTorch tanpa CUDA (model 4-bit butuh GPU)"
        continue
    }
    $pythonExe = $candidate
    break
}

if (-not $pythonExe) {
    Write-Host "GAGAL: tidak ada interpreter Python yang siap menjalankan model 4-bit." -ForegroundColor Red
    foreach ($reason in $rejected) { Write-Host "  - $reason" -ForegroundColor Yellow }
    Write-Host "  Perbaikan A - pasang PyTorch versi CUDA pada .venv:" -ForegroundColor Yellow
    Write-Host "    .\.venv\Scripts\python.exe -m pip install --force-reinstall --index-url https://download.pytorch.org/whl/cu121 torch" -ForegroundColor Yellow
    Write-Host "  Perbaikan B - tunjuk interpreter yang sudah punya CUDA:" -ForegroundColor Yellow
    Write-Host "    .\scripts\start_ai_service.ps1 -Python C:\path\ke\python.exe" -ForegroundColor Yellow
    exit 1
}

if (-not $Python -and $pythonExe -ne $venvPython) {
    Write-Host "PERINGATAN: .venv dilewati (dependensi kurang atau PyTorch tanpa CUDA)." -ForegroundColor Yellow
    Write-Host "  Memakai: $pythonExe" -ForegroundColor Yellow
}
Write-Host "Interpreter siap: $pythonExe (PyTorch CUDA aktif)" -ForegroundColor DarkGray

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
Assert-Ready ($null -ne $cloudflared) "cloudflared tidak ditemukan di PATH." "winget install --id Cloudflare.cloudflared"

$envPath = Join-Path $projectRoot ".env"
Assert-Ready (Test-Path $envPath) "File .env belum ada." "Copy-Item .env.example .env lalu isi nilainya"

$envText = Get-Content $envPath -Raw
# python-dotenv menerima "KEY = nilai" (spasi di sekitar '='), jadi validasi di sini
# juga harus toleran spasi agar tidak salah menolak konfigurasi yang sah.
Assert-Ready `
    ($envText -match "(?m)^\s*AI_TRUST_INTERNAL_TOKEN\s*=\s*\S+") `
    "AI_TRUST_INTERNAL_TOKEN kosong di .env." `
    "Isi dengan token acak yang sama seperti AI_INTERNAL_TOKEN di Render."

Assert-Ready `
    ($envText -match "(?m)^\s*HF_TOKEN\s*=\s*\S+") `
    "HF_TOKEN kosong di .env." `
    "Isi token HuggingFace agar Llama bisa dimuat."

# Laptop tidak boleh meneruskan ke dirinya sendiri (loop tak berujung).
Assert-Ready `
    (-not ($envText -match "(?m)^\s*AI_SERVICE_URL\s*=\s*\S+") -and -not $env:AI_SERVICE_URL) `
    "AI_SERVICE_URL terisi pada laptop." `
    "Hapus/kosongkan AI_SERVICE_URL di .env laptop; variabel itu hanya untuk Render."

if ($TunnelName) {
    # Gagal cepat dengan instruksi jelas bila tunnel belum dibuat atau belum login.
    # EAP diturunkan sementara karena stderr cloudflared dianggap terminating error.
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & cloudflared tunnel info $TunnelName *> $null
    $tunnelExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousEap
    Assert-Ready `
        ($tunnelExitCode -eq 0) `
        "Named tunnel '$TunnelName' tidak ditemukan atau cloudflared belum login." `
        "Jalankan: cloudflared tunnel login; cloudflared tunnel create $TunnelName; cloudflared tunnel route dns $TunnelName ai.<domain-anda>.com"
}

if (-not $NoWarmup) {
    # Muat model saat start agar demo tidak menunggu pada request pertama.
    $env:MODEL_WARMUP_ON_STARTUP = "true"
} else {
    # Override .env: variabel proses menang atas nilai di .env.
    $env:MODEL_WARMUP_ON_STARTUP = "false"
}

$adapterTransaksi = Join-Path $projectRoot "adapters\soft-prompt-transaksi"
if (-not (Test-Path $adapterTransaksi)) {
    Write-Host "PERINGATAN: $adapterTransaksi tidak ada. Ekstraksi teks akan gagal." -ForegroundColor Yellow
}
$adapterNota = Join-Path $projectRoot "adapters\soft-prompt-nota"
if (-not (Test-Path $adapterNota)) {
    Write-Host "PERINGATAN: $adapterNota tidak ada. Scan Nota memakai fallback aturan." -ForegroundColor Yellow
}

Write-Host "Menjalankan layanan AI lokal di http://127.0.0.1:$Port ..." -ForegroundColor Cyan
if ($NoWarmup) {
    Write-Host "  Warmup dimatikan: request pertama akan memuat Llama (lambat)." -ForegroundColor DarkGray
} else {
    Write-Host "  Warmup aktif: menunggu Llama selesai dimuat sebelum melayani." -ForegroundColor DarkGray
}

$server = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList @("-m", "uvicorn", "src.api:app", "--host", "127.0.0.1", "--port", "$Port") `
    -PassThru `
    -NoNewWindow

try {
    $deadline = (Get-Date).AddMinutes(6)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        if ($server.HasExited) {
            # ExitCode Start-Process -PassThru sering kosong di PowerShell 5.1;
            # penyebab sebenarnya sudah tampil pada log uvicorn di atas.
            throw "Uvicorn berhenti sebelum siap. Periksa pesan error di atas."
        }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3 -UseBasicParsing
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch {
            # Server belum menerima koneksi; ulangi sampai batas waktu.
        }
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) { throw "Layanan lokal tidak siap dalam 6 menit." }

    Write-Host "Layanan AI lokal siap." -ForegroundColor Green
    if ($TunnelName) {
        Write-Host "Membuka named tunnel '$TunnelName'. Tekan Ctrl+C untuk berhenti." -ForegroundColor Cyan
        Write-Host "Pastikan AI_SERVICE_URL di Render menunjuk hostname tunnel ini." -ForegroundColor Cyan
        # --url membuat aturan ingress lokal, jadi config.yml tidak wajib.
        # Bila config.yml berisi ingress, aturan di file itulah yang dipakai.
        & cloudflared tunnel run --url "http://127.0.0.1:$Port" $TunnelName
    } else {
        Write-Host "Membuka quick tunnel. Salin URL https://*.trycloudflare.com yang muncul" -ForegroundColor Cyan
        Write-Host "ke AI_SERVICE_URL di Render. Tekan Ctrl+C untuk berhenti." -ForegroundColor Cyan
        & cloudflared tunnel --url "http://127.0.0.1:$Port"
    }
} finally {
    if (-not $server.HasExited) {
        Write-Host "Menghentikan layanan AI lokal..." -ForegroundColor DarkGray
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
}
