---
name: moomoo-quiz
version: 1.0.0
description: "启动 Moomoo MY 内部考试系统服务器，显示考试和管理员链接。当用户想开始考试、查看成绩、或启动 quiz 服务器时使用。"
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
- 共 100 题（MCQ / 填空 / 判断）
- 时间限制：60 分钟
- 及格线：90 / 100 分
- 组员可通过同一 WiFi 的局域网地址访问

**停止服务器：** 在终端按 `Ctrl+C`

---

## 注意事项

- 服务器必须运行，成绩才会被保存到 `results.json`
- 直接打开 `index.html` 也能考试，但**成绩不会被记录**
- 如果端口 8888 被占用，检查是否有已运行的实例
