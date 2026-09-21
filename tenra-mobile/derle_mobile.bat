@echo off
chcp 65001 > nul
title TENRA Mobile - Build & Sync
echo ========================================================
echo       TENRA Mobile (React + Capacitor Sync)
echo ========================================================
echo.
echo [1/2] React / Vite Projesi Derleniyor...
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo [X] Derleme hatasi olustu!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/2] Capacitor Android Projesine Senkronize Ediliyor...
call npx cap sync android
if %ERRORLEVEL% NEQ 0 (
    echo [X] Capacitor sync hatasi!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [✓] Tamamlandi! Android projesi guncellendi: tenra-mobile/android/
pause
