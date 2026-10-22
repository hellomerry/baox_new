# Windows 打包指南

> 用 `build.py` 在 Windows 上产出 `.exe` 的完整步骤。

---

## 一、build.py 已经跨平台

`build.py` 用 `sys.executable` + `os.pathsep`，同一份代码 Linux/Windows/macOS 都能跑：

```python
cmd = [sys.executable, '-m', 'PyInstaller', ...]   # 不写死 python/python.exe
'--add-data', f'templates{os.pathsep}templates'    # Windows=; Linux=:
```

我已经把 `--name` 改成英文（`reimbursement_finance` 等），避免 Windows bootloader 中文路径 bug。

---

## 二、Windows 打包步骤

### 1. 准备 Python 环境

```cmd
REM 安装 Python 3.11（勾选 "Add Python to PATH"）
REM https://www.python.org/downloads/windows/

REM 安装 Git（可选，便于克隆仓库）
REM https://git-scm.com/download/win

REM 推荐用 PowerShell
```

### 2. 安装项目依赖

```cmd
cd C:\projects\reimbursement-app

REM 用国内源（如果公司内网）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

REM 或
pip install -r requirements.txt
```

### 3.（可选）准备图标和版本信息

```cmd
mkdir resources
```

- **图标**：`resources/finance.ico`（256x256，多分辨率 .ico 文件）
- **版本信息**：`resources/finance_version.txt`（见下方模板）

如果这两个文件不存在，build.py 会跳过对应参数，**不会报错**。

### version.txt 模板

```python
# resources/finance_version.txt
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'080404B0',
          [
            StringStruct(u'CompanyName', u'XXX 单位'),
            StringStruct(u'FileDescription', u'报销稽核系统 - 财务版'),
            StringStruct(u'FileVersion', u'1.0.0.0'),
            StringStruct(u'InternalName', u'reimbursement_finance'),
            StringStruct(u'OriginalFilename', u'reimbursement_finance.exe'),
            StringStruct(u'ProductName', u'报销稽核系统'),
            StringStruct(u'ProductVersion', u'1.0.0.0')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
```

### 4. 打包

```cmd
python build.py all
```

### 5. 产物

```
dist\
├── reimbursement_finance\              ← 财务版目录
│   ├── reimbursement_finance.exe       ← 双击运行这个
│   ├── _internal\                      ← Python + 依赖
│   │   ├── python311.dll
│   │   ├── _cffi_backend.cp311-win_amd64.pyd
│   │   ├── ...
│   │   └── webview\
│   ├── templates\                      ← Flask 模板
│   └── static\                         ← JS/CSS
├── reimbursement_auditor\
│   ├── reimbursement_auditor.exe
│   └── _internal\
└── reimbursement_reimburser\
    ├── reimbursement_reimburser.exe
    └── _internal\
```

总大小：~120 MB / 客户端（Windows 比 Linux 大约多 20MB，主要是 .dll 和 webview-edge 的 .node 资源）。

---

## 三、首次运行 & 验证

```cmd
cd dist\reimbursement_finance
reimbursement_finance.exe
```

预期输出（控制台隐藏，但首次会写日志）：
- 进程锁获取成功
- 数据库完整性检查
- 自动备份
- TLS 检查
- Flask 启动
- PyWebView 窗口打开

**首次启动后**：
- 数据库：`%APPDATA%\reimbursement-app\reimbursement.db`
- 备份：`%APPDATA%\reimbursement-app\backup\`
- 日志：`%APPDATA%\reimbursement-app\logs\`

---

## 四、签名（生产推荐）

**没有代码签名**会被 Windows SmartScreen 拦截（"未识别的应用"弹窗）。

### 4.1 自签名测试证书

```powershell
# 用 makecert（VS 自带）或 New-SelfSignedCertificate
New-SelfSignedCertificate `
  -Type CodeSigningCert `
  -Subject "CN=报销稽核系统开发测试" `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -NotAfter (Get-Date).AddYears(5)
```

### 4.2 给 .exe 签名

```cmd
:: signtool 在 Windows SDK 或 VS 自带
signtool sign /f certificate.pfx /p password /tr http://timestamp.digicert.com /td sha256 /fd sha256 reimbursement_finance.exe
```

### 4.3 生产签名

购买**代码签名证书**（DigiCert / GlobalSign / CFCA 等），提交给 CA 申请 .pfx，签名后 SmartScreen 不再拦截。

---

## 五、安装包（可选：NSIS 制作 .msi / .exe 安装器）

### 5.1 准备 NSIS

下载安装 [NSIS](https://nsis.sourceforge.io/)。

### 5.2 写 install.nsi

```nsi
!include "MUI2.nsh"

Name "报销稽核系统 - 财务版"
OutFile "reimbursement_finance_setup.exe"
InstallDir "$PROGRAMFILES64\reimbursement\finance"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "dist\reimbursement_finance\*"
  
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  
  CreateDirectory "$SMPROGRAMS\报销稽核系统"
  CreateShortcut "$SMPROGRAMS\报销稽核系统\财务版.lnk" "$INSTDIR\reimbursement_finance.exe"
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\报销稽核系统\财务版.lnk"
SectionEnd
```

### 5.3 编译

```cmd
"C:\Program Files (x86)\NSIS\makensis.exe" install.nsi
```

产物：`reimbursement_finance_setup.exe`（约 50 MB，含 NSIS 自解压）。

---

## 六、跨架构构建

| 目标 | 在什么机器上打包 | 备注 |
|------|------------------|------|
| Windows x64 | Windows x64 | ✅ 默认 |
| Windows ARM64 | Windows ARM64 | `python -m PyInstaller ... --target-arch=arm64`（PyInstaller 6 实验性） |
| Windows x86 (32 位) | Windows x86 | 不推荐（pywebview 需要 64 位 Edge） |

**ARM64 暂时需要源码拉一份在 ARM64 机器上打包**（PyInstaller 不支持交叉编译）。

---

## 七、常见问题

### 7.1 "Failed to load Python shared library"

缺 `_internal\`。重新跑 `python build.py finance`，不要手动复制。

### 7.2 "PyInstaller does not include ctypes DLLs"

```cmd
pip install --upgrade pyinstaller
```

### 7.3 "ModuleNotFoundError: No module named 'webview'"

打包机器没装 pywebview：
```cmd
pip install pywebview
```

### 7.4 中文界面乱码

- 控制台：`chcp 65001` 后再运行
- WebView：检查 `static/style.css` 字体设置，加 `font-family: "Microsoft YaHei", "微软雅黑", sans-serif;`

### 7.5 杀毒软件误报

PyInstaller 产物常被 360 / 火绒 / Defener 误报。解决方案：
1. 提交样本给杀毒厂商加白
2. 用代码签名证书签名
3. 改用 `--onedir` + 压缩工具（7z SFX）分发

### 7.6 .exe 太大（>150MB）

```cmd
REM 用 UPX 压缩（可选）
pip install upx
REM build.py 里加：
REM   cmd.extend(['--upx-dir', r'C:\upx'])
```

可以减小 30-50%。

---

## 八、CI/CD（GitHub Actions 示例）

`.github/workflows/build-windows.yml`：

```yaml
name: Build Windows
on: [push, tag]
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python build.py all
      - uses: actions/upload-artifact@v4
        with:
          name: windows-clients
          path: dist/
```

产物自动上传到 GitHub Releases。

---

## 九、目录约定

| 路径 | 内容 |
|------|------|
| `dist/reimbursement_<client>/` | 打包产物 |
| `%APPDATA%\reimbursement-app\` | 用户数据（数据库/备份/日志） |
| `%LOCALAPPDATA%\reimbursement-app\` | 缓存 |

多用户场景：每个 Windows 用户独立的工作目录，互不影响。
