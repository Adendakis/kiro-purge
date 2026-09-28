@echo off
REM install.bat - Install Kiro Cleaner from source (non-editable) on Windows.
REM
REM Performs a regular install (a copy into site-packages), unlike
REM `pip install -e .` which links back to the source tree.
REM
REM Usage:
REM   install.bat              Build a wheel and install it
REM   install.bat --dev        Include dev dependencies (pytest, hypothesis)
REM   install.bat --uninstall  Uninstall kiro-cleaner

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PACKAGE_NAME=kiro-cleaner"
set "INSTALL_EXTRAS="
set "DO_UNINSTALL=0"

:parse
if "%~1"=="" goto after_parse
if /I "%~1"=="--dev" set "INSTALL_EXTRAS=[dev]"
if /I "%~1"=="--uninstall" set "DO_UNINSTALL=1"
shift
goto parse
:after_parse

REM Pick a Python launcher.
where py >nul 2>&1 && (set "PYTHON=py -3") || (set "PYTHON=python")

if "%DO_UNINSTALL%"=="1" (
    echo Uninstalling %PACKAGE_NAME% ...
    %PYTHON% -m pip uninstall -y %PACKAGE_NAME%
    echo Done.
    exit /b 0
)

echo Ensuring 'build' is available ...
%PYTHON% -m pip install --quiet --upgrade build || exit /b 1

echo Building distribution artifacts into .\dist ...
if exist dist rmdir /s /q dist
%PYTHON% -m build || exit /b 1

REM Find the newest wheel in dist.
set "WHEEL="
for /f "delims=" %%f in ('dir /b /o-d dist\*.whl 2^>nul') do (
    if not defined WHEEL set "WHEEL=dist\%%f"
)
if not defined WHEEL (
    echo Error: no wheel was produced in .\dist.
    exit /b 1
)

echo Installing %WHEEL%%INSTALL_EXTRAS% ...
%PYTHON% -m pip install --force-reinstall "%WHEEL%%INSTALL_EXTRAS%" || exit /b 1

echo.
echo Installed %PACKAGE_NAME%. Verify with:
echo     kiro-cleaner --version
echo     kiro-cleaner scan --help
endlocal
