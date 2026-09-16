@echo off
setlocal
cd /d "%~dp0"
echo Pasta atual: %CD%
if not exist app.py (
  echo ERRO: app.py nao encontrado nesta pasta.
  pause
  exit /b 1
)
if not exist .env (
  echo ERRO: .env nao encontrado nesta pasta.
  echo Copie .env.example para .env e preencha as configuracoes.
  echo Exemplo: copy .env.example .env
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERRO ao instalar dependencias.
  pause
  exit /b 1
)
python diagnostico_windows.py
if errorlevel 1 (
  echo Diagnostico falhou.
  pause
  exit /b 1
)
echo.
echo Iniciando KlikTech na pasta correta...
python app.py
pause
