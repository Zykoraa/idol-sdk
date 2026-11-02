@echo off
setlocal
cd /d "%~dp0"
echo === Idol 3D installer ===
echo.

python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 (
    echo Python 3.10 or newer is required. Get it from https://www.python.org/downloads/
    echo During setup, tick "Add python.exe to PATH".
    goto :fail
)

echo [1/5] Checking PyTorch...
python -c "import torch, sys; sys.exit(0 if torch.version.cuda else 1)" >nul 2>&1
if errorlevel 1 (
    echo Installing PyTorch with NVIDIA GPU support. This is a large download...
    python -m pip uninstall -y torch torchvision >nul 2>&1
    python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 || goto :fail
) else (
    echo GPU PyTorch already installed.
)

echo [2/5] Installing the Idol SDK...
python -m pip install -e . || goto :fail

echo [3/5] Installing GUI extras...
python -m pip install scipy || goto :fail

echo [4/5] Hugging Face login...
hf auth whoami >nul 2>&1
if errorlevel 1 (
    hf auth login || goto :fail
) else (
    echo Already logged in.
)

echo [5/5] Creating desktop shortcut...
for /f "delims=" %%P in ('python -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"') do set "PYW=%%P"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Idol 3D.lnk'); $s.TargetPath = '%PYW%'; $s.Arguments = '\"%~dp0idol_gui.py\"'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = 'C:\Windows\System32\imageres.dll,190'; $s.Save()" || goto :fail

echo.
echo Done! Before the first run, make sure your Hugging Face account has access to:
echo   https://huggingface.co/facebook/dinov3-vith16plus-pretrain-lvd1689m
echo   https://huggingface.co/black-forest-labs/FLUX.2-dev
echo Then open "Idol 3D" from your desktop.
pause
exit /b 0

:fail
echo.
echo Install failed. See the message above.
pause
exit /b 1
