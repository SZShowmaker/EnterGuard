@echo off
REM build_exe.bat - 打包 EnterGuard 为单 exe (在 Windows 上运行)
REM 前置: pip install pyinstaller pywin32 comtypes uiautomation
REM 产物: dist\EnterGuard.exe
REM
REM 原理: main.py 用 try/except 兼容 "from config import" 和 "from .config import".
REM       PyInstaller 打包时 src 目录的模块会被自动分析收集, 无需手动 --add-data.
REM       为保证 src 在 sys.path 顶部, 用 --paths src 指定.

echo === EnterGuard 打包脚本 ===
echo.

REM 检查 pyinstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [!] 未安装 PyInstaller, 正在安装...
    pip install pyinstaller
)

REM 清理旧产物
echo [1/3] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist EnterGuard.spec del EnterGuard.spec

REM 打包
echo [2/3] 开始打包 (单文件, 无控制台窗口)...
pyinstaller --onefile --windowed ^
    --name "EnterGuard" ^
    --paths "src" ^
    --hidden-import "win32api" ^
    --hidden-import "win32con" ^
    --hidden-import "comtypes" ^
    --hidden-import "comtypes.client" ^
    --hidden-import "uiautomation" ^
    --collect-submodules "uiautomation" ^
    --collect-submodules "comtypes" ^
    src\main.py

if errorlevel 1 (
    echo.
    echo [X] 打包失败, 请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo [3/3] 打包成功!
echo 产物: dist\EnterGuard.exe
echo.
echo 使用: 双击 dist\EnterGuard.exe 即可运行
echo config.json 会在 exe 同目录自动生成
echo.
pause
