@echo off
setlocal

:: Set the working directory to the script's location to ensure relative paths work correctly.
pushd "%~dp0"

echo.
echo ^> Starting NotebookLM Automation Services...
echo.

REM --- Pre-flight check for the gcloud credentials directory ---
IF NOT EXIST ".gcloud" (
    echo [ERROR] The gcloud credentials directory was not found at: %CD%\.gcloud
    echo [ERROR] Please ensure you have created the '.gcloud' directory in your project root.
    popd
    pause
    exit /b 1
)

IF NOT EXIST ".gcloud\application_default_credentials.json" (
    echo [ERROR] The 'application_default_credentials.json' file was not found inside the '.gcloud' directory.
    echo [ERROR] Please copy your Application Default Credentials from your system's gcloud config folder.
    echo [INFO]  1. Run 'gcloud auth application-default login' in your terminal to refresh credentials.
    echo [INFO]  2. On Windows, the credentials folder is usually located at: %APPDATA%\gcloud
    echo [INFO]  3. Copy the 'application_default_credentials.json' file from that folder into your project's '.gcloud' directory.
    popd
    pause
    exit /b 1
)

REM --- Check for quota project in ADC file ---
findstr /C:"quota_project_id" ".gcloud\application_default_credentials.json" >nul
if %errorlevel% neq 0 (
    echo [WARNING] Your Google ADC file is missing a quota project.
    echo [INFO]    This is required for accessing Google Cloud services like GCS.
    echo [ACTION]  Run this command, replacing 'your-gcp-project-id' with your project ID:
    echo           gcloud auth application-default set-quota-project your-gcp-project-id
    echo [INFO]    Then, copy the updated 'application_default_credentials.json' file into the '.gcloud' directory.
    echo.
)

echo [SUCCESS] All pre-flight checks passed.
echo.
echo ^> Building and starting services in the background...
docker-compose up --build -d

popd
endlocal