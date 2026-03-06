# 全球互联网合规动态监控

> 面向互联网企业合规团队的自动化法规情报工具，持续追踪全球主要市场的数据隐私、AI监管、平台竞争、未成年人保护等核心领域的监管动态。

---

## 功能概览

- **自动抓取**：覆盖 FTC、UK Gov、EFF、GDPR.eu、TechCrunch、The Verge 等 RSS 源；同时通过 Google News 多语言搜索（英、日、韩、越、印尼、德、法、葡、西、泰、阿拉伯语等 20+ 语种）获取本地语种监管动态
- **AI 深度分析**：基于硅基流动 Qwen3-8B 批量处理，每条动态生成规范中文标题、30-50 字摘要、120-200 字正文分析（含背景/监管细节/影响/走向）以及 1-2 句合规提示
- **智能分类**：按地区（东南亚 / 亚太 / 欧洲 / 北美 / 日韩台 等）和合规类别（数据隐私 / AI合规 / 平台与竞争合规 / 未成年人保护 等 9 大类）自动归类
- **三重去重**：URL 精确匹配 → Bigram 语义相似度（阈值 0.45）→ LLM 批量核验，有效过滤跨来源的同主题重复报道
- **交互式 HTML 报告**：支持按地区、分类、状态筛选和关键词搜索；区域内按时间倒序排列；点击条目可展开正文分析和合规提示
- **PDF 报告**：每周自动生成 PDF 版本，方便分发存档

---

## 自动化调度

| 任务 | 触发时间（北京/新加坡时间） | 说明 |
|------|---------------------------|------|
| 每日数据更新 | 周一至周五 09:33 | 抓取 + 翻译最新数据，写入数据库 |
| 每周月报生成 | 每周一 09:47 | 读取已更新 DB，生成 HTML + PDF 报告并提交归档 |

> 周一 09:33 的日常抓取会先完成数据更新，09:47 的周报直接读取最新 DB，无需重复抓取。

---

## 覆盖地区与来源

| 显示分组 | 涵盖地区 | 代表监管来源 |
|----------|----------|-------------|
| 东南亚 | 越南、印尼、泰国、菲律宾、马来西亚、新加坡 | 越南信息通信部、印尼 Kominfo、泰国 PDPA、新加坡 IMDA |
| 亚太 | 印度、巴基斯坦、孟加拉国、澳大利亚、新西兰 | 印度 MeitY / DPDPA、澳大利亚 eSafety、OAIC |
| 欧洲 | 欧盟、英国、德国、法国、荷兰、西班牙等 | GDPR / EDPB 执法、ICO、CNIL、CMA、Ofcom、DSA / DMA |
| 北美 | 美国、加拿大 | FTC、联邦公报、CCPA / CPRA、COPPA 执法、加拿大 PIPEDA |
| 南美 | 巴西、墨西哥、阿根廷等 | LGPD / ANPD（巴西）、SENACON |
| 日韩台 | 日本、韩国、台湾、香港、澳门 | 日本个人信息保护委员会、韩国 KISA、台湾数位部 |
| 中东 | 沙特、阿联酋、土耳其、尼日利亚、南非 | 沙特通信部、土耳其 KVKK、南非 POPIA |
| 其他 | 全球综合 | EFF Deeplinks、TechCrunch、The Verge |

---

## 合规分类

| 分类 | 典型议题 |
|------|----------|
| 数据隐私 | GDPR / CCPA 执法、跨境数据传输、数据本地化、Cookie 合规、数据泄露通报 |
| AI合规 | EU AI Act 实施、AI 训练数据版权、生成式 AI 治理、深度伪造监管、LLM 责任 |
| 未成年人保护 | 年龄验证、社交媒体禁令、COPPA / KOSA 执法、家长控制、未成年人数据收集 |
| 平台与竞争合规 | DSA / DMA 执法、App Store 反垄断、第三方支付开放、平台透明度义务 |
| 广告营销合规 | 虚假广告、KOL 披露义务、暗黑模式、定向广告限制 |
| 消费者保护 | 订阅自动续费、退款政策、Loot Box / Gacha 随机付费机制、消费者权益诉讼 |
| 知识产权 | AI 训练数据版权诉讼、平台版权责任、内容抓取法律边界、流媒体版权 |
| 内容监管 | 违法内容下架义务、仇恨言论监管、虚假信息治理、内容分级 |
| 经营合规 | 本地代理 / 代表处要求、数字服务税、平台注册许可、外资限制 |

---

## 项目架构

```
Monitor-v2/
├── monitor.py          # 主入口：run / report / query / stats / retranslate
├── fetcher.py          # RSS + Google News 多语言抓取，过滤写入 DB
├── classifier.py       # 分类打标（地区 / 类别 / 状态 / 影响分值 / 信源层级）
├── translator.py       # AI 批量翻译 + 正文分析 + 合规提示生成 + 去重核验
├── reporter.py         # HTML 报告生成（交互筛选、展开正文、三重去重）
├── models.py           # 数据模型（LegislationItem）+ SQLite 数据库操作
├── config.py           # 搜索关键词库、RSS 源、分类标签、输出配置
├── utils.py            # 共享工具：区域分组映射
├── generate_pdf.py     # Playwright 截图：HTML 报告 → PDF
├── requirements.txt    # Python 依赖
├── data/
│   └── monitor.db      # SQLite 数据库（自动提交回仓库）
├── reports/
│   ├── latest.html     # 最新 HTML 交互报告
│   ├── latest.pdf      # 最新 PDF 报告
│   └── archive/        # 历史周报（YYYY-WXX/weekly.html）
├── assets/
│   └── logo.png        # 品牌 Logo（替换此文件即可更换报告头部图标）
└── .github/workflows/
    ├── daily_check.yml     # 每日数据抓取 workflow
    └── weekly_report.yml   # 每周报告生成 workflow
```

---

## 部署（GitHub Actions）

### 1. 克隆仓库

```bash
git clone https://github.com/evonotevil/Monitor-v2.git
cd Monitor-v2
```

### 2. 配置 GitHub Secret

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret 名称 | 说明 | 是否必填 |
|-------------|------|---------|
| `LLM_API_KEY` | 硅基流动 API Key（[免费申请](https://cloud.siliconflow.cn)） | 必填 |

### 3. 启用 GitHub Actions

进入 **Actions** 标签页，确认两个 workflow 已启用：
- `每日合规动态检查`（`daily_check.yml`）：周一至周五 09:33 SGT 自动运行
- `全球互联网合规周报`（`weekly_report.yml`）：每周一 09:47 SGT 自动运行

首次测试可点击 **Run workflow** 手动触发。

> **注意**：GitHub 对超过 60 天未有代码提交的仓库会自动暂停 Actions 计划任务。如遇停止，进入 Actions 页面重新启用即可。

---

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium      # 仅 PDF 生成需要

# 设置环境变量
export LLM_API_KEY=sk-xxx

# 抓取数据并生成月报（从上月1日至今）
python3 monitor.py run --period month

# 仅从数据库生成报告（不重新抓取）
python3 monitor.py report --format html --period month

# 生成 PDF（需先有 HTML 报告）
python3 generate_pdf.py

# 关键词搜索
python3 monitor.py query --keyword "GDPR"

# 查看数据库统计
python3 monitor.py stats

# 重新翻译历史条目（更新 AI Prompt 后使用）
python3 monitor.py retranslate
```

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | 硅基流动 API Key | 必填 |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | 使用的模型 | `Qwen/Qwen3-8B` |

---

## 报告访问

| 文件 | 说明 |
|------|------|
| [`reports/latest.html`](reports/latest.html) | 最新 HTML 交互报告 |
| [`reports/latest.pdf`](reports/latest.pdf) | 最新 PDF 报告 |
| [`reports/archive/`](reports/archive/) | 历史周报存档（按 ISO 周号归档） |

HTML 报告可通过 htmlpreview.github.io 在线预览：

```
https://htmlpreview.github.io/?https://raw.githubusercontent.com/evonotevil/Monitor-v2/main/reports/latest.html
```

---

## 技术说明

- **LLM**：硅基流动 `Qwen/Qwen3-8B`，每批最多 3 条并行处理，批间 4 秒冷却（符合免费层限速）
- **AI 输出字段**：每条动态生成 `title_zh`（标题）、`summary_zh`（摘要）、`detail_zh`（正文分析）、`compliance_note`（合规提示）
- **数据库**：SQLite，存储在 `data/monitor.db`，每次 CI 运行后自动提交回仓库
- **PDF 生成**：Playwright Chromium（GitHub Actions 已配置缓存，命中时安装时间从 90 秒降至 5 秒）
- **Git 优化**：所有 workflow 使用 `fetch-depth: 1` 浅克隆，避免拉取含完整 DB 历史的大体积仓库

---

*Bilibili Legal · 仅供内部参考*
