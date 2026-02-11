@echo off
REM pcc launcher (Windows)
REM Put this folder in PATH, then you can run: pcc <args>

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pcc.ps1" %*