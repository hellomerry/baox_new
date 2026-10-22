# PyInstaller 打包指南

## 目标
把 `reimbursement-app` 项目打成 **3 个独立 .exe**，每个 ~150-200MB，**自带 Python 解释器 + 所有依赖**，双击即跑。

Win7 / Win10 / Win11 通用（因为 Python 解释器嵌在 .exe 里了，**不依赖系统 Python**）。

## 前置条件

- **有 v2100d.zip 绿色版**（Python 3.7.9 + 所有 wheel 都已装好）
- **联网**（首次需要下 PyInstaller 80MB）

## 步骤

### 1. 解压 v2100d.zip
```
unzip reimbursement-app-windows-green-v2100d.zip
cd windows_green
```

### 2. 双击 `build_exe.bat`
（也可以 cmd 跑 `build_exe.bat`）

脚本会：
1. `pip install pyinstaller`（~80MB）
2. 打包 `Finance.exe` / `Auditor.exe` / `Reimburser.exe`（3 个，每个 150-200MB）
3. 输出到 `workspace\reimbursement-app\dist\`

预计 5-15 分钟。

### 3. 分发 3 个 .exe
```
dist/
  Finance.exe     → 财务版
  Auditor.exe     → 稽核员版
  Reimburser.exe  → 报销员版
```

每个 .exe 是**完全自包含**的：
- 内嵌 Python 3.7.9 解释器
- 内嵌所有依赖（flask, webview, pythonnet, cv2, numpy, ...）
- 内嵌整个项目代码 + 资源

用户**双击即跑**，**无需装任何东西**。

## 系统要求（.exe 目标机器）

- Windows 7 SP1 / 10 / 11 (任意版本)
- **不需要** .NET 6（pythonnet 2.5.2 走 .NET Framework 4）
- **不需要** Python
- **不需要** Edge WebView2
- .NET Framework 4.0+（Win7+ 自带）

## 故障排除

### pip install 失败
- 检查网络
- 或手动 `python\python.exe -m pip install pyinstaller` 单独装

### PyInstaller 报 hidden import
- 编辑 `build_exe.bat` 的 `--hidden-import` 行加上缺的模块
- 常见缺的：numpy.core._methods, scipy, PIL, opencv

### .exe 启动后黑屏
- 删 `--windowed` 参数（让 cmd 窗口显示，便于看错误）
- 或用 `Finance.exe` 同目录生成的 `_internal/` 里的 debug log

## 重新打包

如果改了代码想重新打包：
1. 双击 `build_exe.bat`（会重新装 PyInstaller + 重新打包）
2. 或只跑 PyInstaller 部分（跳过 pip install）

## 高级

手动调 PyInstaller 参数：

```cmd
python\python.exe -m PyInstaller --onefile --windowed ^
    --name "Finance" ^
    --icon "workspace\reimbursement-app\static\img\finance.ico" ^
    --add-data "workspace\reimbursement-app\templates;templates" ^
    --add-data "workspace\reimbursement-app\static;static" ^
    --hidden-import flask_sqlalchemy ^
    --hidden-import webview ^
    --hidden-import pythonnet ^
    --collect-all pywebview ^
    --collect-all pythonnet ^
    --noconfirm ^
    workspace\reimbursement-app\launcher_finance.py
```

## 已知限制

- .exe 大小 150-200MB（包含 Python + 所有依赖）
- 启动稍慢（解压需要几秒）
- 第一次会被 Windows Defender 扫描（可能要 10-30 秒）
