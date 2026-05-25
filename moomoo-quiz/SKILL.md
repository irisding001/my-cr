---
name: moomoo-quiz
version: 1.2.0
description: "启动 Moomoo MY 内部考试系统服务器，显示考试和管理员链接。当用户想开始考试、查看成绩、启动 quiz 服务器、分析题目分布、查看客经历史成绩或错题时使用。"
---

# Moomoo MY Quiz — 启动指引

当用户调用此 skill 时，执行以下步骤：

## 1. 检查服务器是否已在运行

```bash
curl -s http://localhost:8888 > /dev/null 2>&1 && echo "running" || echo "not running"
```

## 2. 若未运行，在后台启动服务器

```bash
cd C:\Users\irisding\moomoo-quiz && py server.py
```

以 **background** 方式运行，启动后无需等待。

## 3. 向用户展示以下链接

启动成功后，告诉用户：

---

**🦊 Moomoo MY 考试系统已启动！**

| 用途 | 链接 |
|------|------|
| 📝 考试入口（本机） | http://localhost:8888 |
| 📝 考试入口（局域网） | 运行后从终端输出获取 LAN IP |
| 📊 管理员后台 | http://localhost:8888/admin |

**考试说明：**
- 共 100 题（MCQ / 填空 / 判断），从 319 题题库中随机抽取
- 时间限制：60 分钟
- 及格线：90 / 100 分
- 组员可通过同一 WiFi 的局域网地址访问

**停止服务器：** 在终端按 `Ctrl+C`

---

## 题库概览（319 题）

| 主题 | 总计 | MCQ | 填空 | 判断 |
|------|-----:|----:|-----:|-----:|
| 📊 Trading Rules | 155 | 38 | 74 | 43 |
| 💳 Funding | 49 | 15 | 19 | 15 |
| 💰 Fees | 39 | 11 | 22 | 6 |
| 🎁 Promotions | 37 | 8 | 20 | 9 |
| 📚 Financial Basics | 30 | 10 | 10 | 10 |
| ⭐ Membership | 9 | 3 | 4 | 2 |

**Financial Basics 包含：** IPO 定义与流程、Cash Plus 产品特性、SmartSave 运作、期权 Buy/Sell Call/Put、Breakeven、Covered Call、Protective Put、CS 操作知识（Direct CDS-IPO 账户、融资认购规则、A 股激活时效、SG 市场结算等）

## Admin Dashboard 功能

- **人员筛选**：顶部按钮动态列出所有考试人员，点击即可筛选
- **个人报告**：选中某人后展开——左侧历史成绩（每次得分 + 进度条 + 详情按钮），右侧高频错题 Top 15（跨所有考试汇总）
- **答题详情**：点击任意记录的「详情」按钮，查看每道题的对错标注、正确答案及解析
- **汇总统计**：参与人数 / 通过率 / 平均分（随人员筛选联动）

## 注意事项

- 服务器必须运行，成绩才会被保存到 `results.json`
- 直接打开 `index.html` 也能考试，但**成绩不会被记录**
- 如果端口 8888 被占用，检查是否有已运行的实例
- 题库文件：`C:\Users\irisding\moomoo-quiz\index.html`
- 服务器文件：`C:\Users\irisding\moomoo-quiz\server.py`
