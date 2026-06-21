@echo off
echo Iniciando Chrome com remote debugging na porta 9222...
echo.

REM Tenta localizar o Chrome nos caminhos mais comuns
set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if not exist %CHROME% (
  echo Chrome nao encontrado nos caminhos padrao.
  echo Edite este arquivo e coloque o caminho correto do chrome.exe
  pause
  exit /b 1
)

start "" %CHROME% ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%USERPROFILE%\shopee_chrome_profile"

echo Chrome iniciado!
echo.
echo Passos:
echo   1. Faca login em affiliate.shopee.com.br
echo   2. Faca login em shopee.com.br
echo   3. Execute o bot: python -m scraper.bot_cdp
echo.
pause
