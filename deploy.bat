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
if "%DTKT_TEMPORAL_HOST%"=="" (
    echo ERROR: DTKT_TEMPORAL_HOST not set in .env
    exit /b 1
)
if "%DTKT_TEMPORAL_API_KEY%"=="" (
    echo ERROR: DTKT_TEMPORAL_API_KEY not set in .env
    exit /b 1
)

set "DTKT_WORKER_IMAGE=gcr.io/%DTKT_GCP_PROJECT%/dtkt-worker:latest"

echo === Building worker image ===
docker build -t %DTKT_WORKER_IMAGE% detekt_worker\
if errorlevel 1 exit /b 1

echo === Pushing worker image ===
docker push %DTKT_WORKER_IMAGE%
if errorlevel 1 exit /b 1

echo === Running terraform ===
pushd terraform

terraform init

terraform apply ^
    -var="dtkt_gcp_project=%DTKT_GCP_PROJECT%" ^
    -var="dtkt_doppler_token=%DTKT_DOPPLER_TOKEN%" ^
    -var="dtkt_temporal_host=%DTKT_TEMPORAL_HOST%" ^
    -var="dtkt_temporal_api_key=%DTKT_TEMPORAL_API_KEY%" ^
    -auto-approve

if errorlevel 1 (
    popd
    exit /b 1
)

popd

echo === Deploy complete ===
endlocal
