---
name: MY-QA
description: moomoo MY WhatsApp 客服质检助手。当用户提到"跑质检"、"运行质检"、"QC"、"质检报告"、"检查客服对话"、"WhatsApp 质检"、"MY-QA"、"质检某日"、"cookie 过期"、"重新质检"、"查看质检结果"时，必须使用此 skill。即使用户没有说明"质检"字样，但涉及 moomoo MY 客服对话审核、违规检查、投诉风险分析，也应触发。
allowed-tools: Bash Read Write Edit
---

# MY-QA — moomoo MY WhatsApp 质检助手

## 项目位置

```
C:\Users\irisding\whatsapp_qc\
```

Python 路径：`C:\Users\irisding\AppData\Local\Programs\Python\Python314\python.exe`

所有命令从项目目录执行：
```bash
cd /c/Users/irisding/whatsapp_qc
```

## 快速启动

### 质检今天
```bash
PYTHONIOENCODING=utf-8 python main.py
```

### 质检指定日期
```bash
PYTHONIOENCODING=utf-8 python main.py --date 2026-05-19
```

### 跳过抓取，直接分析已有原始数据
```bash
PYTHONIOENCODING=utf-8 python main.py --from-file output/raw_2026-05-19.json
```

### 只分析前 N 条（测试用）
```bash
PYTHONIOENCODING=utf-8 python main.py --date 2026-05-19 --limit 10
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `output/质检日报_YYYY-MM-DD.html` | 主报告，直接用浏览器打开 |
| `output/qc_results_YYYY-MM-DD.json` | 原始质检结果（含所有字段）|
| `output/raw_YYYY-MM-DD.json` | 抓取的原始对话数据（下次可跳过抓取） |

打开报告：
```bash
start output/质检日报_2026-05-19.html
```

## Cookie 管理

Cookie 存储在 `cookies.txt`，约 **7-14 天**过期。过期后 API 会返回 HTML 登录页（不是 JSON），日志会出现 `无法从响应中提取列表` 或 `JSONDecodeError`。

### 更新 Cookie 步骤

1. 浏览器打开 `https://mycm.futuoa.com`
2. 登录后，F12 → Network 面板
3. 找任意一个 API 请求（如 `customer/list-v2`）
4. 复制请求头中的 `Cookie:` 整行字符串
5. 粘贴到 `cookies.txt`（覆盖原内容）

Cookie 必须包含 `EGG_SESS`，否则系统启动时报错。

## 质检范围

固定 7 名客服（`config.py` 中的 `TARGET_AGENTS`）：

```
jordanliow, jackshenlee, emelinlee,
mikilee, alexfoong, vaashini, zhenconglim
```

每人最多分析 50 条对话，防止超量。

## 报告解读

### 违规级别

| 级别 | 颜色 | 说明 |
|------|------|------|
| A级 | 红色 | 最严重：弄虚作假、泄露客户信息、态度恶劣 |
| B级 | 橙色 | 较严重：超8h未回复、承诺未履行(投诉)、不合理应对(投诉) |
| C级 | 黄色 | 一般：超4h未回复、未解答直接转单、承诺未履行 |

### 常见简述含义

| 简述 | 违规代码 |
|------|---------|
| 超4h未回复 | C3 |
| 超8h未回复 | B6 |
| 未解答直接转单 | C1/B4 |
| 承诺未履行 | C2/B5 |
| 不合理应对 | C6/B7 |
| 服务态度恶劣 | A3 |
| 引导套奖/弄虚作假 | A1 |
| 投诉信号 | 无违规但有风险词 |

### 投诉风险

- **高**：客户明确说"complaint"、"report"、"投诉"等，或情绪极度激动
- **中**：客户不满但未明确投诉，或问题未解决
- **低**：正常对话

HTML 报告只显示**高/中风险**或**有违规**的对话，低风险无违规不展示。

## 常见问题

### API 返回空列表 / 无对话

- Cookie 过期 → 更新 Cookie
- 日期无数据 → 换日期试试（周末可能很少）
- 检查日志中 `客户列表：共 0 条`

### 质检速度

约 350 条对话需 **25-35 分钟**（受 API 速率限制：25 req/min，3 并发）。

进度从日志看：
```
[12/350] 质检 customer=XXXXX agent=mikilee ...
```

### JSON 解析失败

少量失败是正常的（模型偶发输出错误格式），系统会自动用 `json-repair` 修复。若大量失败，检查 Anthropic API 是否可访问。

### 重新跑（跳过抓取）

如果 `raw_YYYY-MM-DD.json` 已存在，系统自动跳过抓取直接分析。若想强制重新抓取，删除该文件再运行。

## 修改配置

所有配置在 `config.py`：

- `TARGET_AGENTS`：修改目标客服名单
- `ANTHROPIC_MODEL`：切换模型
- `OUTPUT_DIR`：修改输出目录

每人条数上限在 `main.py` 第 169 行（`if agent_counts[agent] < 50`）。

## 完整流程示例

用户说"跑一下今天的质检"：

```bash
cd /c/Users/irisding/whatsapp_qc
PYTHONIOENCODING=utf-8 python main.py
# 等待完成...
start output/质检日报_$(date +%Y-%m-%d).html
```

用户说"质检 5月19日的数据"：

```bash
cd /c/Users/irisding/whatsapp_qc
PYTHONIOENCODING=utf-8 python main.py --date 2026-05-19
start output/质检日报_2026-05-19.html
```
