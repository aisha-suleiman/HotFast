@echo off
rem Zapusk bota odnim faylom: proveryaet okruzhenie, primenyaet migratsii, startuet bota
rem i podnimaet ego zanovo, esli on upal.
rem
rem Format .bat, a ne .ps1, namerenno: PowerShell po umolchaniyu zapreshchaet zapusk
rem skriptov, a .bat rabotaet vsegda, v tom chisle po dvoynomu kliku.
rem
rem Teksty tut tolko latinitsey: cmd chitaet .bat v kodirovke konsoli, i kirillitsa
rem lomaet razbor samogo fayla. Logi bota pri etom ostayutsya russkimi.
cd /d "%~dp0"

if not exist ".env" (
    echo [!] No .env file.
    echo     Copy .env.example to .env and fill in BOT_TOKEN.
    goto :end
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment...
    py -m venv .venv
    if errorlevel 1 goto :error
    .venv\Scripts\python.exe -m pip install --upgrade pip -q
    echo [1/3] Installing dependencies, this takes a minute...
    .venv\Scripts\python.exe -m pip install -q -r requirements.txt
    if errorlevel 1 goto :error
)

echo [2/3] Applying database migrations...
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 goto :error

echo [3/3] Starting the bot. Press Ctrl+C to stop.
echo.

:run
.venv\Scripts\python.exe -m bot
rem Vykhod 0 - eto Ctrl+C ili fatalnaya oshibka nastroek: perezapuskat ne nado.
rem Lyuboy drugoy kod - padenie, podnimaem zanovo cherez 10 sekund.
if errorlevel 1 (
    echo.
    echo [!] Bot stopped unexpectedly. Restarting in 10 seconds... Ctrl+C to cancel.
    timeout /t 10 /nobreak >nul
    goto :run
)
goto :end

:error
echo.
echo [!] Failed. See the message above.

:end
echo.
pause
