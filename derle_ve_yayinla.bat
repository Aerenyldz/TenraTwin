@echo off
chcp 65001 >nul 2>&1
title TENRA - Derle ve Yayinla
echo ========================================================
echo   TENRA - React Uygulamasini Derle ve Sunucuyu Baslat
echo ========================================================
echo.

REM 1. React Uygulamasini Derle
echo [1/3] React mobil uygulamasi derleniyor...
cd /d "%~dp0tenra-mobile"
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo [HATA] React build basarisiz! Hata kodunu kontrol edin.
    pause
    exit /b 1
)
echo [OK] React build basarili - dist/ klasoru guncellendi.
echo.

REM 2. Mevcut sunucu surecini durdur (varsa)
echo [2/3] Mevcut sunucu sureci kontrol ediliyor...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8008 " ^| findstr "LISTENING"') do (
    echo    Port 8008 uzerinde calisan surec sonlandiriliyor (PID: %%p)...
    taskkill /F /PID %%p >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo.

REM 3. Sunucuyu yeniden baslat
echo [3/3] Sunucu yeniden baslatiliyor...
cd /d "%~dp0"
start "TENRA Server" cmd /k "python -m uvicorn server.api:app --host 0.0.0.0 --port 8008"
echo.
echo ========================================================
echo   [OK] Tamamlandi! Sunucu http://0.0.0.0:8008 uzerinde aktif.
echo   Mobil: http://SUNUCU_IP:8008/mobile/
echo ========================================================
echo.
timeout /t 5
