# 🌐 Lilith Legal · 全球游戏立法动态监控

> 面向中资手游出海合规团队的自动化法规情报工具，每日追踪全球主要市场的游戏监管动态。

---

## 功能概览

- **自动抓取**：从 30+ 个官方监管机构、法律媒体、行业资讯 RSS 源实时获取法规动态；同时通过 Google News 多语言搜索（英、日、韩、越、印尼、德、法、葡、西、泰、阿拉伯语等）覆盖本地语种媒体
- **AI 翻译与提炼**：基于硅基流动 Qwen3-8B 批量处理，将英文原文转化为规范中文标题和合规摘要；专有名词（Loot Box、GDPR、FTC 等）自动保留英文；每批 3 条并发处理，效率比逐条提升 3 倍
- **智能分类**：按地区（东南亚 / 亚太 / 欧洲 / 北美 / 日韩台 等）和合规类别（数据隐私 / 未成年人保护 / 玩法合规 / 广告营销 等）自动归类
- **三重去重**：URL 精确匹配 → Bigram 语义相似度（阈值 0.45）→ LLM 批量核验，有效过滤跨来源的同主题重复报道
- **HTML 报告**：生成可交互的 HTML 报告，支持按地区、分类、状态筛选和关键词搜索；区域内按官方 > 法律 > 行业 > 媒体信源优先级排列
- **PDF 报告**：每周自动生成带 Lilith Legal 品牌的 PDF 版本，方便分发存档
- **飞书通知**：
  - 每日日报：有新动态时自动推送飞书卡片，含中文标题、摘要和原文链接（最多展示 8 条）
  - 每周周报：生成过去 7 天汇总，含分类统计、区域分布、5 条多样化精选重点
- **周报存档**：每周报告自动归档至 `reports/archive/YYYY-WXX/`，支持后续趋势分析

---

## 自动化调度

| 任务 | 触发时间（北京/新加坡时间） | 说明 |
|------|---------------------------|------|
| 每日日报 | 周一至周五 09:33 | 抓取 + 翻译最新数据，有新增则推送飞书 |
| 每周周报 | 每周一 09:47 | 读取已更新 DB，生成 HTML + PDF 报告，发飞书并存档 |

> 周一 09:33 的日报会先完成数据抓取，09:47 的周报直接读取最新 DB，无需重复抓取。

---

## 覆盖地区与来源

| 显示分组 | 涵盖地区 | 代表监管来源 |
|----------|----------|-------------|
| 东南亚 🌏 | 越南、印尼、泰国、菲律宾、马来西亚、新加坡 | 越南信息通信部 (MIC)、印尼 Kominfo、泰国 NBTC、新加坡 IMDA |
| 亚太 🌏 | 印度、巴基斯坦、孟加拉国、澳大利亚、新西兰 | 印度 MeitY、IT 规则动态、澳大利亚 eSafety、Privacy Act |
| 欧洲 🌍 | 欧盟、英国、德国、法国、荷兰、比利时等 | GDPR 执法动态、ASA（英国）、Ofcom、ICO、CNIL、PEGI |
| 北美 🌎 | 美国、加拿大 | FTC、联邦公报、纽约州 AG、加拿大竞争局 |
| 南美 🌎 | 巴西、墨西哥、阿根廷等 | SENACON（巴西）、LGPD 动态 |
| 日韩台 🌸 | 日本、韩国、台湾、香港、澳门 | GRAC（韩国）、日本消费者厅 / CERO、台湾数位部 |
| 中东 🕌 | 沙特、阿联酋、土耳其、尼日利亚、南非 | 沙特通信部、阿联酋监管机构 |
| 其他 🌐 | 全球综合 | GamesIndustry.biz、GamesBeat、Pocket Gamer |

---

## 合规分类

| 分类 | 典型议题 |
|------|----------|
| 🔒 数据隐私 | GDPR / CCPA 执法、儿童隐私 (COPPA)、跨境数据传输、数据本地化 |
| 🎲 玩法合规 | Loot Box / 抽卡监管、概率公示、虚拟货币、涉赌认定 |
| 🧒 未成年人保护 | 年龄验证、未成年消费限制、游戏时长管控、家长控制 |
| 📣 广告营销合规 | 虚假广告、KOL 披露义务、暗黑模式、价格透明度 |
| 🛡️ 消费者保护 | 退款政策、订阅自动续费、消费者权益诉讼 |
| 🏢 经营合规 | 本地代理 / 代表处、游戏许可证、税务合规、外资限制 |
| 📱 平台政策 | App Store / Google Play 政策、第三方支付、DMA 合规 |
| 📋 内容监管 | 内容审查、AI 生成内容、版权合规、游戏分级 |

---

## 项目架构

```
Monitor/
├── monitor.py          # 主入口：run / report / query / stats / retranslate
├── fetcher.py          # RSS + Google News 多语言抓取，去重写入 DB
├── classifier.py       # 分类打标（地区 / 类别 / 状态 / 影响分值 / 信源层级）
├── translator.py       # AI 批量翻译 + 术语修正 + LLM 重复对核验
├── reporter.py         # HTML 报告生成（含区域推断、三重去重、信源排序）
├── models.py           # 数据模型（LegislationItem）+ SQLite 数据库操作
├── config.py           # 搜索关键词库、RSS 源、分类标签、输出配置
├── utils.py            # 共享工具：区域分组映射（单一修改源，各模块统一引用）
├── daily_check.py      # 日报脚本：查询昨日新增 → 构建飞书卡片 → 推送
├── feishu_notify.py    # 周报脚本：查询本周数据 → 构建飞书卡片 → 推送
├── generate_pdf.py     # Playwright 截图：HTML 报告 → PDF
├── requirements.txt    # Python 依赖
├── data/
│   └── monitor.db      # SQLite 数据库（法规条目 + 去重索引）
├── reports/
│   ├── latest.html     # 最新 HTML 报告
│   ├── latest.pdf      # 最新 PDF 报告
│   └── archive/        # 历史周报（YYYY-WXX/weekly.html）
└── assets/
    └── lilith-logo.png # PDF 品牌 Logo
```

---

## 一次性部署（GitHub）

### 1. Fork / 克隆本仓库

```bash
git clone https://github.com/evonotevil/Monitor.git
cd Monitor
```

### 2. 配置 GitHub Secrets

在仓库页面进入 **Settings → Secrets and variables → Actions → New repository secret**，添加以下 Secrets：

| Secret 名称 | 说明 | 是否必填 |
|-------------|------|---------|
| `LLM_API_KEY` | 硅基流动 API Key（[免费申请](https://cloud.siliconflow.cn)） | ✅ 必填 |
| `FEISHU_WEBHOOK_URL` | 飞书自定义机器人 Webhook 地址 | ✅ 必填（否则通知不发送） |

### 3. 启用 GitHub Actions

进入 **Actions** 标签页，确认两个 workflow 已启用：
- `每日合规动态检查`（`daily_check.yml`）：周一至周五 09:33 SGT 自动运行
- `全球游戏合规周报`（`weekly_report.yml`）：每周一 09:47 SGT 自动运行

首次测试可点击 **Run workflow** 手动触发。

---

## 本地调试

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium      # 仅 PDF 生成需要

# 设置环境变量
export LLM_API_KEY=sk-xxx
export FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 抓取最新数据并生成 HTML 报告（过去 7 天）
python monitor.py run --period week

# 仅生成报告（不抓取新数据）
python monitor.py report --format html --period week

# 仅生成 PDF（需先生成 HTML）
python generate_pdf.py

# 发送日报飞书通知（本地测试）
python daily_check.py

# 发送周报飞书通知（本地测试）
REPORT_HTML_URL=https://... python feishu_notify.py

# 关键词搜索数据库
python monitor.py query --keyword "loot box"

# 查看数据库统计
python monitor.py stats

# 重新翻译历史条目（更新 Prompt 后使用）
python monitor.py retranslate
```

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | 硅基流动 API Key | 必填 |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | 使用的模型 | `Qwen/Qwen3-8B` |
| `FEISHU_WEBHOOK_URL` | 飞书 Webhook 地址 | 必填（通知功能） |
| `REPORT_HTML_URL` | 周报 HTML 公开链接（飞书卡片按钮用） | 可选 |
| `REPORT_PDF_URL` | 周报 PDF 公开链接（飞书卡片按钮用） | 可选 |

---

## 报告访问

| 文件 | 说明 |
|------|------|
| [`reports/latest.html`](reports/latest.html) | 最新 HTML 交互报告（可在浏览器中打开） |
| [`reports/latest.pdf`](reports/latest.pdf) | 最新 PDF 报告（可直接下载分发） |
| [`reports/archive/`](reports/archive/) | 历史周报存档（按 ISO 周号归档） |

> HTML 报告可通过 [htmlpreview.github.io](https://htmlpreview.github.io) 直接在线预览：
> `https://htmlpreview.github.io/?https://raw.githubusercontent.com/evonotevil/Monitor/main/reports/latest.html`

---

## 技术说明

- **LLM**：硅基流动免费层 `Qwen/Qwen3-8B`，每批 3 条并行处理，批间 4 秒冷却（遵守免费层限速）
- **数据库**：SQLite，存储在 `data/monitor.db`，每次 CI 运行后自动提交回仓库
- **PDF 生成**：Playwright Chromium（GitHub Actions 已配置缓存，缓存命中时安装时间从 90 秒降至 5 秒）
- **Git 优化**：所有 workflow 使用 `fetch-depth: 1` 浅克隆，避免拉取含完整 DB 历史的大体积仓库

---

*Lilith Legal · 仅供内部参考*
