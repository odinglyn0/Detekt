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
if "%DTKT_WORKER_DOPPLER_TOKEN%"=="" (
    echo ERROR: DTKT_WORKER_DOPPLER_TOKEN not set in .env
    exit /b 1
)
if "%DTKT_REPLIER_DOPPLER_TOKEN%"=="" (
    echo ERROR: DTKT_REPLIER_DOPPLER_TOKEN not set in .env
    exit /b 1
)

set "TARGET=%~1"

if "%TARGET%"=="" set "TARGET=all"
if "%TARGET%"=="all"    goto :build_all
if "%TARGET%"=="worker" goto :build_worker
if "%TARGET%"=="replier" goto :build_replier
echo ERROR: Unknown target "%TARGET%". Use: all, worker, or replier
exit /b 1

:build_all
call :build_worker
if errorlevel 1 exit /b 1
call :build_replier
if errorlevel 1 exit /b 1
goto :terraform

:build_worker
set "DTKT_WORKER_IMAGE=gcr.io/%DTKT_GCP_PROJECT%/dtkt-worker:latest"
echo === Building worker image ===
docker build -t %DTKT_WORKER_IMAGE% detekt_worker\
if errorlevel 1 exit /b 1
echo === Pushing worker image ===
docker push %DTKT_WORKER_IMAGE%
if errorlevel 1 exit /b 1
if "%TARGET%"=="worker" goto :terraform
exit /b 0

:build_replier
set "DTKT_REPLIER_IMAGE=gcr.io/%DTKT_GCP_PROJECT%/dtkt-replier:latest"
echo === Building replier image ===
docker build -t %DTKT_REPLIER_IMAGE% detekt_replier\
if errorlevel 1 exit /b 1
echo === Pushing replier image ===
docker push %DTKT_REPLIER_IMAGE%
if errorlevel 1 exit /b 1
if "%TARGET%"=="replier" goto :terraform
exit /b 0

:terraform
echo === Running terraform ===
pushd terraform

terraform init

terraform apply ^
    -var="dtkt_gcp_project=%DTKT_GCP_PROJECT%" ^
    -var="dtkt_worker_doppler_token=%DTKT_WORKER_DOPPLER_TOKEN%" ^
    -var="dtkt_replier_doppler_token=%DTKT_REPLIER_DOPPLER_TOKEN%" ^
    -auto-approve

if errorlevel 1 (
    popd
    exit /b 1
)

popd

echo === Deploy complete ===
endlocal
