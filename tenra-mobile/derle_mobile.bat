@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title TENRA Mobile - APK Derleme

echo ========================================================
echo   TENRA Mobile - React + Capacitor + APK
echo ========================================================
echo.

REM --- [1/4] React build ---
echo [1/4] React / Vite derleniyor...
call npm run build
if errorlevel 1 (
    echo [X] React derleme hatasi!
    pause
    exit /b 1
)
echo [OK] dist/ guncellendi.
echo.

REM --- [2/4] Capacitor sync ---
echo [2/4] Capacitor Android senkronize ediliyor...
call npx cap sync android
if errorlevel 1 (
    echo [X] Capacitor sync hatasi!
    pause
    exit /b 1
)
echo [OK] android/ guncellendi.
echo.

REM --- [3/4] Gradle debug APK ---
echo [3/4] Android APK derleniyor - bu biraz surer...
cd /d "%~dp0android"
call gradlew.bat assembleDebug --quiet
if errorlevel 1 (
    echo [X] Gradle APK derleme hatasi!
    cd /d "%~dp0"
    pause
    exit /b 1
)
cd /d "%~dp0"
echo [OK] APK derlendi.
echo.

REM --- [4/4] APK'yi proje kokune kopyala - /apk indirme linki ---
set "APK_SRC=%~dp0android\app\build\outputs\apk\debug\app-debug.apk"
set "APK_DST=%~dp0..\app-debug.apk"

if not exist "%APK_SRC%" (
    echo [X] APK bulunamadi: %APK_SRC%
    pause
    exit /b 1
)

copy /Y "%APK_SRC%" "%APK_DST%" >nul
if errorlevel 1 (
    echo [X] APK kopyalanamadi.
    pause
    exit /b 1
)

echo ========================================================
echo   [OK] APK HAZIR - yol haritasi duzeltmeleri dahil
echo.
echo   Dosya: %APK_DST%
echo.
echo   Telefondan indir - sunucu acikken:
echo     http://192.168.1.100:8008/apk
echo     http://100.93.198.21:8008/apk
echo     http://localhost:8008/apk
echo ========================================================
echo.
pause
endlocal
