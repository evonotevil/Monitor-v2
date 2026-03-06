#!/usr/bin/env python3
"""
飞书机器人通知 - 每周合规简报卡片
发送内容: 本周统计 + 区域分布 + HTML/PDF 链接按钮

必需环境变量:
    FEISHU_WEBHOOK_URL   飞书自定义机器人的 Webhook 地址

可选环境变量:
    REPORT_HTML_URL      HTML 简报的公开访问 URL
    REPORT_PDF_URL       PDF 报告的公开访问/下载 URL

本地调试:
    FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx \
    REPORT_HTML_URL=https://... \
    python feishu_notify.py
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

DB_PATH = Path(__file__).parent / "data" / "monitor.db"

# ── 区域分组配置（统一从 utils 导入，禁止在此重复定义）──────────────
from utils import _REGION_GROUP_MAP, _GROUP_ORDER, _GROUP_EMOJI, _get_region_group, normalize_status


def _select_diverse_highlights(candidates: list, max_items: int = 5) -> list:
    """
    从候选重点条目中选出地区和分类多样化的列表，避免同一区域或同一分类扎堆。

    规则：
    - 同一区域分组最多出现 2 条
    - 同一 category_l1 最多出现 1 条
    - 标题 Bigram 相似度 > 60% 视为重复，只保留优先级更高的那条
    """
    def _bigram_sim(a: str, b: str) -> float:
        if not a or not b or len(a) < 2 or len(b) < 2:
            return 0.0
        bg_a = {a[i:i + 2] for i in range(len(a) - 1)}
        bg_b = {b[i:i + 2] for i in range(len(b) - 1)}
        union = bg_a | bg_b
        return len(bg_a & bg_b) / len(union) if union else 0.0

    selected: list = []
    region_count: dict = {}
    category_seen: set = set()

    for item in candidates:
        group = _get_region_group(item.get("region", "其他"))
        cat = item.get("category_l1", "")

        # 同一区域分组上限 2 条
        if region_count.get(group, 0) >= 2:
            continue
        # 同一分类只保留 1 条
        if cat in category_seen:
            continue
        # 标题 Bigram 去重（与已选条目过于相似则跳过）
        title = (item.get("title_zh") or item.get("title") or "")
        if any(
            _bigram_sim(title, (s.get("title_zh") or s.get("title") or "")) > 0.60
            for s in selected
        ):
            continue

        selected.append(item)
        region_count[group] = region_count.get(group, 0) + 1
        category_seen.add(cat)

        if len(selected) >= max_items:
            break

    return selected


# ── 状态 / 分类 emoji ────────────────────────────────────────────────

STATUS_EMOJI = {
    "执法动态":     "🔴",
    "已生效":       "🟢",
    "即将生效":     "🟡",
    "草案/征求意见": "🔵",
    "立法进行中":   "🔵",
    "已提案":       "⚪",
    "修订变更":      "🟠",
    "已废止":       "⬜",
    "立法动态":     "🟡",
}

CAT_EMOJI = {
    "数据隐私":    "🔒",
    "玩法合规":    "🎲",
    "未成年人保护": "🧒",
    "广告营销合规": "📣",
    "消费者保护":  "🛡️",
    "经营合规":    "🏢",
    "平台政策":    "📱",
    "内容监管":    "📋",
}


# ── 数据库查询 ────────────────────────────────────────────────────────

def get_weekly_data():
    if not DB_PATH.exists():
        print(f"⚠️  数据库不存在: {DB_PATH}")
        return 0, [], {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    total = conn.execute(
        "SELECT COUNT(*) FROM legislation WHERE date >= ?", (week_ago,)
    ).fetchone()[0]

    by_cat = conn.execute(
        """SELECT category_l1, COUNT(*) AS cnt
           FROM legislation WHERE date >= ?
           GROUP BY category_l1 ORDER BY cnt DESC""",
        (week_ago,),
    ).fetchall()

    # 按实际区域统计，再汇总到分组
    by_region_raw = conn.execute(
        """SELECT region, COUNT(*) AS cnt
           FROM legislation WHERE date >= ?
           GROUP BY region ORDER BY cnt DESC""",
        (week_ago,),
    ).fetchall()

    # 重点条目候选：取更多条目，再通过多样性算法筛选（避免同区域/同分类扎堆）
    highlight_candidates = conn.execute(
        """SELECT title, title_zh, summary_zh, summary, region, status, category_l1,
                  source_url, date
           FROM legislation WHERE date >= ?
           ORDER BY
             CASE status
               WHEN '执法动态'      THEN 0
               WHEN '已生效'        THEN 1
               WHEN '即将生效'      THEN 2
               WHEN '草案/征求意见'  THEN 3
               WHEN '立法进行中'    THEN 4
               ELSE 5 END,
             impact_score DESC
           LIMIT 20""",
        (week_ago,),
    ).fetchall()

    conn.close()

    # 汇总到 8 大分组
    by_region_group: dict = {}
    for row in by_region_raw:
        group = _get_region_group(row["region"])
        by_region_group[group] = by_region_group.get(group, 0) + row["cnt"]

    highlights = _select_diverse_highlights([dict(r) for r in highlight_candidates])
    return total, [dict(r) for r in by_cat], by_region_group, highlights


# ── 构建飞书卡片 ──────────────────────────────────────────────────────

def build_card(total, by_cat, by_region_group, highlights, html_url, pdf_url):
    today    = datetime.now()
    week_ago = today - timedelta(days=7)
    date_range = f"{week_ago.strftime('%Y/%m/%d')} – {today.strftime('%m/%d')}"

    # 分类统计行
    cat_parts = [
        f"{CAT_EMOJI.get(r['category_l1'], '•')} {r['category_l1']} **{r['cnt']}**"
        for r in by_cat
    ]
    cat_line = "　".join(cat_parts) if cat_parts else "暂无数据"

    # 区域分组统计行
    region_parts = []
    for group in _GROUP_ORDER:
        cnt = by_region_group.get(group, 0)
        if cnt > 0:
            emoji = _GROUP_EMOJI.get(group, "•")
            region_parts.append(f"{emoji} {group} **{cnt}**")
    region_line = "　".join(region_parts) if region_parts else "暂无数据"

    # 重点条目 elements
    hl_elements = []
    for item in highlights:
        emoji   = STATUS_EMOJI.get(normalize_status(item["status"]), "•")
        cat_em  = CAT_EMOJI.get(item["category_l1"], "")
        summary = (item.get("summary_zh") or item.get("summary") or "")[:80]
        if len(summary) >= 80:
            summary += "…"
        title_text = item["title"][:65] + ("…" if len(item["title"]) > 65 else "")
        url = item.get("source_url", "")
        title_md = f"[{title_text}]({url})" if url else title_text

        # 日期格式「YYYY-MM-DD」
        raw_date = item.get("date", "")
        date_tag = f"「{raw_date}」" if raw_date else ""

        hl_elements.append({
            "tag": "markdown",
            "content": (
                f"{emoji} **[{item['region']}]** {item['status']} "
                f"· {cat_em} {item['category_l1']}\n"
                f"{date_tag} {title_md}\n"
                f"_{summary}_"
            ),
        })

    # 组装 elements
    elements = [
        {
            "tag": "markdown",
            "content": (
                f"上周共监测到 **{total}** 条立法 / 执法动态\n\n"
                f"**📂 按分类**\n{cat_line}\n\n"
                f"**🗺️ 按地区**\n{region_line}"
            ),
        },
    ]

    if hl_elements:
        elements += [
            {"tag": "hr"},
            {"tag": "markdown", "content": "**📌 上周重点关注**"},
            *hl_elements,
        ]

    elements.append({"tag": "hr"})

    # 操作按钮
    actions = []
    if html_url:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "🌐 查看 HTML 简报"},
            "type": "primary",
            "url": html_url,
        })
    if pdf_url:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "📄 下载 PDF 报告"},
            "type": "default",
            "url": pdf_url,
        })
    if actions:
        elements.append({"tag": "action", "actions": actions})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"🌍 Lilith Legal 全球游戏合规周报 · {date_range}",
            },
        },
        "elements": elements,
    }


# ── 发送 ─────────────────────────────────────────────────────────────

def send_card(webhook_url: str, card: dict) -> None:
    payload = {"msg_type": "interactive", "card": card}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        code = result.get("code", result.get("StatusCode", -1))
        if code == 0:
            print("✅ 飞书通知发送成功")
        else:
            print(f"⚠️  飞书返回异常: {result}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        sys.exit(1)


# ── 入口 ─────────────────────────────────────────────────────────────

def main():
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    html_url    = os.environ.get("REPORT_HTML_URL", "")
    pdf_url     = os.environ.get("REPORT_PDF_URL", "")

    if not webhook_url:
        print("❌ 未设置 FEISHU_WEBHOOK_URL 环境变量")
        sys.exit(1)

    total, by_cat, by_region_group, highlights = get_weekly_data()
    print(f"本周数据: {total} 条，区域分布: {by_region_group}，重点: {len(highlights)} 条")

    card = build_card(total, by_cat, by_region_group, highlights, html_url, pdf_url)
    send_card(webhook_url, card)


if __name__ == "__main__":
    main()
