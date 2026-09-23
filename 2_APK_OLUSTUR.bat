@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0tenra-mobile"
call "%~dp0tenra-mobile\derle_mobile.bat"
