# BrowserSkill 命令参考

`bsk` CLI 完整命令速查与示例。Agent 会自动调用，以下供手动调试参考。

## 基本流程

```bash
# 1. 创建会话（返回 session-id）
bsk session start

# 2. 打开网页
bsk navigate --session <id> "https://example.com"

# 3. 获取页面结构（返回带 @eN 引用的 aria 快照）
bsk snapshot --session <id>

# 4. 读取原始 HTML
bsk get-html --session <id>

# 5. 截图保存
bsk screenshot --session <id> --out "screenshot.png"

# 6. 结束会话
bsk session stop
```

## 交互操作

先用 `bsk snapshot` 获取元素引用 `@eN`，再操作：

```bash
bsk click --session <id> --ref @e3          # 点击元素
bsk fill --session <id> --ref @e5 --value "内容"  # 填写输入框
bsk press --session <id> "Enter"            # 按键
bsk wait-ms 2000                            # 等待页面加载
```

## 实测示例：百度搜索

```bash
bsk session start                          # → rjos
bsk navigate --session rjos "https://www.baidu.com"
bsk snapshot --session rjos                # 找到搜索框 @e33
bsk fill --session rjos --ref @e33 --value "BrowserSkill 腾讯开源"
bsk press --session rjos "Enter"
bsk wait-ms 2000
bsk snapshot --session rjos                # 读取搜索结果
```

## 命令速查

| 命令 | 用途 |
|------|------|
| `bsk daemon` | 管理后台进程 |
| `bsk doctor` | 诊断所有组件状态 |
| `bsk session start/stop/list` | 会话管理 |
| `bsk navigate` | 打开 URL |
| `bsk navigate-back/forward` | 前进/后退 |
| `bsk reload` | 刷新页面 |
| `bsk snapshot` | 获取页面结构（aria 快照 + 元素引用） |
| `bsk get-html` | 获取原始 HTML |
| `bsk screenshot` | 截图 |
| `bsk click` | 点击元素 |
| `bsk fill` | 填写表单 |
| `bsk press` | 按键 |
| `bsk select` | 设置下拉框选项 |
| `bsk console` | 读取控制台日志 |
| `bsk evaluate` | 执行 JavaScript |
| `bsk request-help` | 遇验证码时请求人工处理 |
| `bsk wait-for-navigation` | 等待页面加载事件 |
| `bsk wait-ms` | 等待指定毫秒 |