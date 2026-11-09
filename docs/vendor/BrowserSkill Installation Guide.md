# BrowserSkill 安装指南

腾讯开源浏览器桥接工具，让 AI Agent 操作你已登录的真实浏览器。

项目：[github.com/Tencent/BrowserSkill](https://github.com/Tencent/BrowserSkill)

## 1. 安装 CLI

```powershell
# PowerShell
irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 | iex
```

若执行策略拦截，改用手动安装：

```bash
# 1. 下载
curl -fSL -o "$TEMP/bsk.zip" "https://github.com/Tencent/BrowserSkill/releases/latest/download/bsk-v0.1.7-x86_64-pc-windows-msvc.zip"
# 2. 解压
unzip "$TEMP/bsk.zip" -d "$TEMP/bsk-extracted"
# 3. 安装
mkdir -p ~/.local/bin && cp "$TEMP/bsk-extracted/bsk.exe" ~/.local/bin/
# 4. 加 PATH（写入 ~/.bashrc）
echo 'export PATH="/c/Users/$USER/.local/bin:$PATH"' >> ~/.bashrc
```

验证：`bsk --version` → `bsk 0.1.7`

## 2. 安装浏览器扩展

Chrome/Edge 打开：[Chrome Web Store - BrowserSkill](https://chromewebstore.google.com/detail/hhcmgoofomhgciiibhipgmgkgnoenaoi)

点击「添加至 Chrome」，扩展图标变绿即连接成功。

## 3. 安装 Skill（WorkBuddy）

```bash
bsk install-skill --harness workbuddy -y
```

## 4. 检查

```bash
bsk doctor
```

全部 ✅ 即可使用。
![[4ef81def40bfb1daf2d39c0cd9cc53d1_MD5.jpg]]
