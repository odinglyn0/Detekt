param(
    [ValidateSet("all", "worker", "replier")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Write-Error ".env file not found in root"
    exit 1
}

Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        Set-Variable -Name $matches[1].Trim() -Value $matches[2].Trim() -Scope Script
    }
}

if (-not $DTKT_GCP_PROJECT)          { Write-Error "DTKT_GCP_PROJECT not set in .env"; exit 1 }
if (-not $DTKT_WORKER_DOPPLER_TOKEN) { Write-Error "DTKT_WORKER_DOPPLER_TOKEN not set in .env"; exit 1 }
if (-not $DTKT_REPLIER_DOPPLER_TOKEN){ Write-Error "DTKT_REPLIER_DOPPLER_TOKEN not set in .env"; exit 1 }

function Build-Worker {
    $image = "gcr.io/$DTKT_GCP_PROJECT/dtkt-worker:latest"
    Write-Host "=== Building worker image ===" -ForegroundColor Cyan
    docker build -t $image detekt_worker/
    if ($LASTEXITCODE -ne 0) { exit 1 }
    Write-Host "=== Pushing worker image ===" -ForegroundColor Cyan
    docker push $image
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

function Build-Replier {
    $image = "gcr.io/$DTKT_GCP_PROJECT/dtkt-replier:latest"
    Write-Host "=== Building replier image ===" -ForegroundColor Cyan
    docker build -t $image detekt_replier/
    if ($LASTEXITCODE -ne 0) { exit 1 }
    Write-Host "=== Pushing replier image ===" -ForegroundColor Cyan
    docker push $image
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

function Run-Terraform {
    Write-Host "=== Running terraform ===" -ForegroundColor Cyan
    Push-Location terraform
    try {
        terraform init
        terraform apply `
            -var="dtkt_gcp_project=$DTKT_GCP_PROJECT" `
            -var="dtkt_worker_doppler_token=$DTKT_WORKER_DOPPLER_TOKEN" `
            -var="dtkt_replier_doppler_token=$DTKT_REPLIER_DOPPLER_TOKEN" `
            -auto-approve
        if ($LASTEXITCODE -ne 0) { exit 1 }
    } finally {
        Pop-Location
    }
}

switch ($Target) {
    "worker"  { Build-Worker }
    "replier" { Build-Replier }
    "all"     { Build-Worker; Build-Replier }
}

Run-Terraform

Write-Host "=== Deploy complete ===" -ForegroundColor Green
