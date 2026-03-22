@echo off
setlocal enabledelayedexpansion

if not exist .env (
    echo ERROR: .env file not found in root
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    set "line=%%a"
    if not "!line:~0,1!"=="#" (
        if not "%%a"=="" set "%%a=%%b"
    )
)

if "%DTKT_GCP_PROJECT%"=="" (
    echo ERROR: DTKT_GCP_PROJECT not set in .env
    exit /b 1
)
if "%DTKT_DOPPLER_TOKEN%"=="" (
    echo ERROR: DTKT_DOPPLER_TOKEN not set in .env
    exit /b 1
)
if "%DTKT_SCANNER_DOPPLER_TOKEN%"=="" (
    echo ERROR: DTKT_SCANNER_DOPPLER_TOKEN not set in .env
    exit /b 1
)

set "DTKT_POLLER_IMAGE=gcr.io/%DTKT_GCP_PROJECT%/dtkt-poller:latest"
set "DTKT_SCANNER_IMAGE=gcr.io/%DTKT_GCP_PROJECT%/dtkt-scanner:latest"

echo === Building poller image ===
docker build -t %DTKT_POLLER_IMAGE% detekt_poller\
if errorlevel 1 exit /b 1

echo === Building scanner image ===
docker build -t %DTKT_SCANNER_IMAGE% detekt_scanner\
if errorlevel 1 exit /b 1

echo === Pushing poller image ===
docker push %DTKT_POLLER_IMAGE%
if errorlevel 1 exit /b 1

echo === Pushing scanner image ===
docker push %DTKT_SCANNER_IMAGE%
if errorlevel 1 exit /b 1

echo === Running terraform ===
pushd terraform

terraform init

terraform apply ^
    -var="dtkt_gcp_project=%DTKT_GCP_PROJECT%" ^
    -var="dtkt_doppler_token=%DTKT_DOPPLER_TOKEN%" ^
    -var="dtkt_scanner_doppler_token=%DTKT_SCANNER_DOPPLER_TOKEN%" ^
    -auto-approve

if errorlevel 1 (
    popd
    exit /b 1
)

popd

echo === Deploy complete ===
endlocal
