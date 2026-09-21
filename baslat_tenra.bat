@echo off
chcp 65001 >nul 2>&1
title TENRA Voice Twin Server
echo ========================================================
echo       TENRA - AHMET EREN SESLI ASISTAN SISTEMI
echo       Otomatik Baslatma ve Healthcheck Destekli
echo ========================================================
echo.

REM [1/3] Ollama Kontrol
echo [1/3] Ollama Kontrol Ediliyor...
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe" >NUL
if "%ERRORLEVEL%"=="0" (
    echo [OK] Ollama zaten calisiyor.
) else (
    echo [!!] Ollama baslatiliyor...
    start "" "ollama" serve
    timeout /t 4 /nobreak >nul
)

REM [2/3] Cloudflare Tunnel
echo [2/3] Cloudflare Tunnel Kontrol Ediliyor...
if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" (
    tasklist /FI "IMAGENAME eq cloudflared.exe" 2>NUL | find /I /N "cloudflared.exe" >NUL
    if not errorlevel 1 (
        echo [OK] Cloudflare Tunnel zaten calisiyor.
    ) else (
        start "Cloudflare Tunnel" /min "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8008
        echo [OK] Cloudflare HTTPS Tuneli baslatildi.
    )
) else (
    echo [--] Cloudflare kurulu degil, atlaniyor.
)

REM [3/3] TENRA Sunucusu - Otomatik Restart Dongusu
echo [3/3] TENRA Sunucusu Baslatiliyor (Port 8008)...
echo.
echo   Tailscale Erisim : http://100.93.198.21:8008/
echo   Ev Ici Wi-Fi     : http://192.168.1.100:8008/
echo   Yerel            : http://localhost:8008/
echo.
echo   Sunucu cokerse otomatik yeniden baslatilacak.
echo ========================================================

:restart_loop
echo.
echo [%TIME%] Port 8008 kontrol ediliyor...

REM Port 8008 mesgulse eski sureci sonlandir ve soketin bosalmasini bekle
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr ":8008 " ^| findstr "LISTENING"') do (
    echo [%TIME%] Port 8008 mesgul - PID %%p kapatiliyor...
    taskkill /F /T /PID %%p >nul 2>&1
    ping 127.0.0.1 -n 3 >nul
)

echo [%TIME%] Sunucu baslatiliyor...
python -m uvicorn server.api:app --host 0.0.0.0 --port 8008

REM Buraya gelirse sunucu durmus veya cokmustur
echo.
echo [%TIME%] UYARI: Sunucu durdu! 3 saniye sonra yeniden baslatilacak...
echo   Kapatmak icin Ctrl+C basin veya pencereyi kapatin.
ping 127.0.0.1 -n 4 >nul
goto restart_loop
