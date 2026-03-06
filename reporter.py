"""
报告生成器 - 支持终端表格、Markdown、HTML 输出
HTML 报告支持:
  - 一级分类颜色区分
  - 区域分组展示（东南亚/亚太/中东/欧洲/北美/南美/日韩台/其他）
  - 时间列展示立法动态发布时间
  - Lilith Legal 品牌标识
"""

import base64
import os
import re
import html as html_mod
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import OUTPUT_DIR, REGION_DISPLAY_ORDER
from classifier import get_source_tier
from utils import _REGION_GROUP_MAP, _GROUP_ORDER, _GROUP_EMOJI, _get_region_group, normalize_status


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─── 工具函数 ──────────────────────────────────────────────────────

def _truncate(s: str, max_len: int) -> str:
    if not s:
        return ""
    if len(s) <= max_len:
        return s
    return s[:max_len - 1] + "…"


def _get_display_title(item: dict) -> str:
    """标题显示原文（不使用中文翻译）"""
    return item.get("title", "")


def _get_summary_zh(item: dict) -> str:
    """摘要优先返回中文翻译，没有则返回原文"""
    return item.get("summary_zh") or item.get("summary", "")


# ─── 基于标题文本的分组推断（修复 region='其他' 条目）────────────────────

_TEXT_GROUP_PATTERNS = [
    # 顺序很重要：先匹配更具体的地区
    ("欧洲",   r'(?i)\b(uk\b|britain|british|ofcom|ico\b|england|scotland|wales'
               r'|germany|german|deutschland|bfdi'
               r'|france|french|cnil'
               r'|netherlands|dutch|kansspel'
               r'|belgi(?:um|an|sch)?'
               r'|austria[n]?|österreich'
               r'|italy|italian|agcm'
               r'|spain|spanish|aepd'
               r'|poland|polish'
               r'|sweden|swedish'
               r'|norway|norwegian'
               r'|eu\b|european union|european commission|european parliament'
               r'|gdpr\b|dsa\b|dma\b|ai act|asa\b)\b'
               r'|英国|德国|法国|荷兰|比利时|奥地利|意大利|西班牙|波兰|瑞典|挪威|欧盟|欧洲'),
    ("北美",   r'(?i)\b(usa\b|united states|american?|ftc\b|federal trade commission'
               r'|congress\b|senate\b|california|new york|virginia|texas|florida'
               r'|connecticut|nevada|pennsylvania|attorney general'
               r'|canada|canadian|pipeda\b'
               r'|ccpa\b|cpra\b|coppa\b|kids act)\b'
               r'|美国|加拿大|纽约|加利福尼亚|德克萨斯'),
    # 亚太：原南亚 + 大洋洲合并
    ("亚太",   r'(?i)\b(india[n]?|dpdpa\b|meity\b|vaishnaw|pakistan|bangladesh'
               r'|australia[n]?|new zealand|esafety\b|accc\b)\b'
               r'|印度|巴基斯坦|孟加拉|澳大利亚|新西兰'),
    ("日韩台", r'(?i)\b(japan[ese]?|korea[n]?|south korea|grac\b|kca\b|cero\b'
               r'|nintendo\b)\b'
               r'|台湾|韓[国國]?|日本|韩国|ゲーム|게임|확률형'),
    ("东南亚", r'(?i)\b(vietnam[ese]?|việt|indonesi[a]?[n]?|kominfo\b|igac\b'
               r'|thailand|thai\b|pdpa\b'
               r'|philippine[s]?|malaysia[n]?|mcmc\b'
               r'|singapore|imda\b)\b'
               r'|越南|印度尼西亚|印尼|泰国|菲律宾|马来西亚|新加坡'),
    ("中东",   r'(?i)\b(saudi|uae\b|united arab emirates|turkey|turkish|türkiye'
               r'|nigeria[n]?|south africa)\b'
               r'|沙特|阿联酋|土耳其|尼日利亚|南非'),
    ("南美",   r'(?i)\b(brazil[ian]?|lgpd\b|mexico|mexican|argentina[n]?'
               r'|chile[an]?|colombia[n]?)\b'
               r'|巴西|墨西哥|阿根廷|智利|哥伦比亚'),
]


def _infer_group_from_text(title: str, title_zh: str) -> str:
    """
    从标题文本（英文原文 + 中文译文）推断显示分组。
    用于修复 region='其他' 或 '全球' 的条目，使其出现在正确的地区组。
    """
    text = f"{title} {title_zh}"
    for group, pattern in _TEXT_GROUP_PATTERNS:
        if re.search(pattern, text):
            return group
    return "其他"


def _resolve_group(item: dict) -> str:
    """解析条目的最终显示分组（含文本推断兜底）"""
    group = _get_region_group(item.get("region", "其他"))
    if group == "其他":
        group = _infer_group_from_text(
            item.get("title", ""),
            item.get("title_zh", ""),
        )
    return group


# ─── 报告渲染前去重 ───────────────────────────────────────────────────

def _dedup_for_display(items: List[dict]) -> List[dict]:
    """
    报告渲染前内容去重（三阶段）：
    1. URL 精确去重：同一 source_url → 保留优先级最高的条目
    2. Bigram 相似度 > 0.45 → 确定为同一事件，合并
    3. Bigram 相似度 0.25-0.45 → 送 LLM 批量验证，准确判断是否同一事件
    优先级：impact_score > source_tier（官方>法律>行业>媒体）> 发布日期
    """
    import time as _time
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    TIER_PRIORITY = {"official": 4, "legal": 3, "industry": 2, "news": 1}

    def _bigram_sim(a: str, b: str) -> float:
        a, b = (a or "").lower(), (b or "").lower()
        if len(a) < 2 or len(b) < 2:
            return 0.0
        bg_a = {a[i:i + 2] for i in range(len(a) - 1)}
        bg_b = {b[i:i + 2] for i in range(len(b) - 1)}
        union = bg_a | bg_b
        return len(bg_a & bg_b) / len(union) if union else 0.0

    def _priority(item: dict) -> tuple:
        impact = int(item.get("impact_score", 1))
        tier   = TIER_PRIORITY.get(get_source_tier(item.get("source_name", "")), 1)
        date   = item.get("date", "")
        return (impact, tier, date)

    # 按优先级降序排序 → 先处理高质量条目
    sorted_idx = sorted(range(len(items)), key=lambda i: _priority(items[i]), reverse=True)

    kept_idx: list  = []   # 已保留条目的原始索引
    extra: dict     = {}   # 原始索引 → 被合并的重复条目数
    borderline: list = []  # [(kidx, idx)] 需 LLM 验证的模糊重复对

    for idx in sorted_idx:
        item    = items[idx]
        group   = _resolve_group(item)
        t_item  = (item.get("title_zh") or item.get("title") or "")
        url_item = (item.get("source_url") or "").strip()
        is_dup  = False

        for kidx in kept_idx:
            kitem = items[kidx]
            if _resolve_group(kitem) != group:
                continue

            # ① URL 精确去重
            url_kept = (kitem.get("source_url") or "").strip()
            if url_item and url_kept and url_item == url_kept:
                extra[kidx] = extra.get(kidx, 0) + 1
                is_dup = True
                break

            # ② Bigram 相似度
            t_kept = (kitem.get("title_zh") or kitem.get("title") or "")
            sim = _bigram_sim(t_item, t_kept)
            if sim > 0.45:          # 确定重复
                extra[kidx] = extra.get(kidx, 0) + 1
                is_dup = True
                break
            if sim > 0.25:          # 模糊，记录待 LLM 验证
                borderline.append((kidx, idx))

        if not is_dup:
            kept_idx.append(idx)

    # ③ LLM 批量验证模糊重复对
    if borderline:
        try:
            from translator import verify_duplicate_pairs
            kept_set_now = set(kept_idx)
            pairs_to_verify = []
            valid_bl = []
            for kidx, idx in borderline:
                # 两者都仍在保留集中才验证
                if kidx in kept_set_now and idx in kept_set_now:
                    t_kept = (items[kidx].get("title_zh") or items[kidx].get("title") or "")
                    t_item = (items[idx].get("title_zh")  or items[idx].get("title")  or "")
                    pairs_to_verify.append((t_kept, t_item))
                    valid_bl.append((kidx, idx))
            if pairs_to_verify:
                _time.sleep(4)
                llm_results = verify_duplicate_pairs(pairs_to_verify)
                for (kidx, idx), is_same in zip(valid_bl, llm_results):
                    if is_same and idx in kept_idx:
                        kept_idx.remove(idx)
                        extra[kidx] = extra.get(kidx, 0) + 1
                        _logger.info(f"[dedup LLM] 合并重复: {items[idx].get('title_zh','')[:40]}")
        except Exception as e:
            _logger.warning(f"[dedup LLM] 批量验证失败，跳过: {e}")

    kept_set = set(kept_idx)
    result   = []
    for idx, item in enumerate(items):
        if idx not in kept_set:
            continue
        if idx in extra:
            item = dict(item)   # 浅拷贝，避免污染原始数据
            cnt  = extra[idx]
            sz   = (item.get("summary_zh") or item.get("summary") or "")
            if "另有" not in sz:
                item["summary_zh"] = (sz + f" [另有 {cnt} 篇同主题报道]").strip()
        result.append(item)

    return result


# ─── Lilith Legal Logo 嵌入 ─────────────────────────────────────────

_LOGO_PATH = Path(__file__).parent / "assets" / "lilith-logo.png"


def _get_logo_html() -> str:
    """返回 base64 内联 logo img 标签；文件不存在时返回空字符串"""
    if _LOGO_PATH.exists():
        with open(_LOGO_PATH, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        suffix = _LOGO_PATH.suffix.lower().lstrip(".")
        mime = "image/png" if suffix == "png" else f"image/{suffix}"
        return f'<img src="data:{mime};base64,{b64}" alt="Lilith Games" class="header-logo">'
    return ""


# ─── 分类颜色配置（舒适色系） ──────────────────────────────────────────

CATEGORY_STYLE = {
    "数据隐私":    {"row": "#F0F4FF", "bg": "#DBEAFE", "text": "#1E40AF", "border": "#93C5FD"},
    "玩法合规":    {"row": "#F5F0FF", "bg": "#EDE9FE", "text": "#5B21B6", "border": "#C4B5FD"},
    "未成年人保护": {"row": "#F0FDF4", "bg": "#D1FAE5", "text": "#065F46", "border": "#6EE7B7"},
    "广告营销合规": {"row": "#FFFBF0", "bg": "#FEF3C7", "text": "#92400E", "border": "#FCD34D"},
    "消费者保护":   {"row": "#F0FDFA", "bg": "#CCFBF1", "text": "#134E4A", "border": "#5EEAD4"},
    "经营合规":    {"row": "#FFF7ED", "bg": "#FFEDD5", "text": "#9A3412", "border": "#FCA369"},
    "平台政策":    {"row": "#FFF1F2", "bg": "#FFE4E6", "text": "#9F1239", "border": "#FDA4AF"},
    "内容监管":    {"row": "#F8FAFC", "bg": "#E2E8F0", "text": "#334155", "border": "#94A3B8"},
    "市场准入":    {"row": "#FFF7ED", "bg": "#FFEDD5", "text": "#9A3412", "border": "#FCA369"},
}
DEFAULT_STYLE = {"row": "#FAFAFA", "bg": "#F1F5F9", "text": "#334155", "border": "#CBD5E1"}

STATUS_CSS = {
    "已生效":      "background:#DCFCE7;color:#166534;",
    "即将生效":     "background:#FEF9C3;color:#713F12;",
    "草案/征求意见": "background:#DBEAFE;color:#1E40AF;",
    "立法进行中":   "background:#E0E7FF;color:#3730A3;",
    "已提案":      "background:#E2E8F0;color:#334155;",
    "修订变更":     "background:#7C3AED;color:#FFFFFF;",
    "已废止":      "background:#F1F5F9;color:#475569;",
    "执法动态":    "background:#FEE2E2;color:#991B1B;",
    "立法动态":    "background:#D97706;color:#FFFFFF;",
}

IMPACT_CONFIG = {
    3: {"dots": "●●●", "label": "高优先",  "color": "#DC2626", "title": "高优先：已生效/即将生效/官方执法"},
    2: {"dots": "●●○", "label": "中优先",  "color": "#D97706", "title": "中优先：草案/立法中/执法动态"},
    1: {"dots": "●○○", "label": "低优先",  "color": "#16A34A", "title": "低优先：立法动态/背景信息"},
}

TIER_CONFIG = {
    "official": {"label": "官方",  "bg": "#EFF6FF", "text": "#1D4ED8", "border": "#BFDBFE"},
    "legal":    {"label": "法律",  "bg": "#F0FDF4", "text": "#166534", "border": "#BBF7D0"},
    "industry": {"label": "行业",  "bg": "#FFF7ED", "text": "#9A3412", "border": "#FED7AA"},
    "news":     {"label": "媒体",  "bg": "#F8FAFC", "text": "#475569", "border": "#E2E8F0"},
}


# ─── 终端彩色表格输出 ──────────────────────────────────────────────────

class C:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


TERMINAL_STATUS_COLORS = {
    "已生效": C.GREEN,
    "即将生效": C.YELLOW,
    "草案/征求意见": C.CYAN,
    "立法进行中": C.BLUE,
    "已提案": C.BLUE,
    "修订变更": C.YELLOW,
    "已废止": C.DIM,
    "执法动态": C.RED,
    "立法动态": C.DIM,
}


def print_table(items: List[dict], max_summary_len: int = 50):
    if not items:
        print(f"\n{C.YELLOW}暂无监控数据{C.RESET}\n")
        return

    print()
    print(f"{C.BOLD}{'='*140}{C.RESET}")
    print(f"{C.BOLD}  全球游戏行业立法动态监控报告  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}{C.RESET}")
    print(f"{C.BOLD}{'='*140}{C.RESET}")
    print()

    header = (
        f"{'区域':<8} | "
        f"{'类别':<12} | "
        f"{'标题(原文)':<50} | "
        f"{'发布时间':<12} | "
        f"{'状态':<12} | "
        f"摘要(中文)"
    )
    print(f"{C.BOLD}{header}{C.RESET}")
    print(f"{'-'*140}")

    for item in items:
        status = item.get("status", "立法动态")
        color = TERMINAL_STATUS_COLORS.get(status, C.RESET)
        title = _get_display_title(item)
        summary_zh = _get_summary_zh(item)

        row = (
            f"{_truncate(item.get('region', ''), 8):<8} | "
            f"{_truncate(item.get('category_l1', ''), 12):<12} | "
            f"{_truncate(title, 50):<50} | "
            f"{item.get('date', ''):<12} | "
            f"{color}{_truncate(status, 12):<12}{C.RESET} | "
            f"{_truncate(summary_zh, max_summary_len)}"
        )
        print(row)

    print(f"{'-'*140}")
    print(f"{C.DIM}共 {len(items)} 条记录{C.RESET}\n")


# ─── Markdown 报告 ────────────────────────────────────────────────────

def generate_markdown(items: List[dict], title: str = "全球游戏行业立法动态监控报告") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# {title}",
        "",
        f"> 生成时间: {now}  ",
        f"> 监控条目: {len(items)} 条",
        "",
        "---",
        "",
    ]

    if not items:
        lines.append("*暂无监控数据*")
        return "\n".join(lines)

    by_region = {}
    for item in items:
        region = item.get("region", "其他")
        by_region.setdefault(region, []).append(item)

    for region in REGION_DISPLAY_ORDER:
        region_items = by_region.pop(region, [])
        if not region_items:
            continue
        _append_region_md(lines, region, region_items)

    for region, region_items in by_region.items():
        if region_items:
            _append_region_md(lines, region, region_items)

    return "\n".join(lines)


def _append_region_md(lines: list, region: str, region_items: list):
    lines.append(f"## {region} ({len(region_items)} 条)")
    lines.append("")
    lines.append("| 类别 | 标题(原文) | 发布时间 | 状态 | 摘要(中文) |")
    lines.append("|------|------------|----------|------|------------|")

    for item in sorted(region_items, key=lambda x: x.get("date", ""), reverse=True):
        title_orig = (item.get("title", "") or "").replace("|", "\\|")
        summary_zh = _get_summary_zh(item).replace("|", "\\|")
        url = item.get("source_url", "")

        if url:
            title_cell = f"[{_truncate(title_orig, 50)}]({url})"
        else:
            title_cell = _truncate(title_orig, 50)

        lines.append(
            f"| {item.get('category_l1', '')} "
            f"| {title_cell} "
            f"| {item.get('date', '')} "
            f"| **{item.get('status', '')}** "
            f"| {_truncate(summary_zh, 80)} |"
        )

    lines.append("")


def save_markdown(items: List[dict], filename: Optional[str] = None) -> str:
    ensure_output_dir()
    if not filename:
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    content = generate_markdown(items)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# ─── HTML 报告 ─────────────────────────────────────────────────────────

def _build_legend_html() -> str:
    """构建分类颜色图例"""
    items_html = ""
    for cat, style in CATEGORY_STYLE.items():
        if cat == "市场准入":
            continue
        items_html += (
            f'<span class="legend-item" style="background:{style["bg"]};'
            f'color:{style["text"]};border:1px solid {style["border"]};'
            f'padding:3px 8px;border-radius:12px;font-size:11px;font-weight:500;">'
            f'{cat}</span>'
        )
    return f'<div class="legend">{items_html}</div>'


def generate_html(items: List[dict], title: str = "全球游戏行业立法动态监控报告",
                  period_label: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    logo_html = _get_logo_html()

    # ── 报告级去重（跨来源同事件合并）────────────────────────────
    items = _dedup_for_display(items)

    # ── 按区域分组（含文本推断兜底）──────────────────────────────
    grouped: dict = defaultdict(list)
    for item in items:
        group = _resolve_group(item)
        grouped[group].append(item)

    # ── 生成表格行（含分组 header）────────────────────────────────
    rows_html = ""
    for group in _GROUP_ORDER:
        group_items = grouped.get(group, [])
        if not group_items:
            continue
        emoji = _GROUP_EMOJI.get(group, "🌐")
        # 分组 header 行
        rows_html += (
            f'\n        <tr class="group-row" data-group="{html_mod.escape(group)}">'
            f'<td colspan="6" class="group-header">'
            f'{emoji} {html_mod.escape(group)}'
            f'<span class="group-count">{len(group_items)} 条</span>'
            f'</td></tr>'
        )
        # 条目行（按优先级排序：impact_score > source_tier（官方>行业>媒体）> 日期）
        _TIER_SORT = {"official": 4, "legal": 3, "industry": 2, "news": 1}
        for item in sorted(
            group_items,
            key=lambda x: (
                int(x.get("impact_score", 1)),
                _TIER_SORT.get(get_source_tier(x.get("source_name", "")), 1),
                x.get("date", ""),
            ),
            reverse=True,
        ):
            cat = item.get("category_l1", "")
            style = CATEGORY_STYLE.get(cat, DEFAULT_STYLE)
            status = normalize_status(item.get("status", ""))
            status_css = STATUS_CSS.get(status, "background:#F1F5F9;color:#475569;")
            impact = int(item.get("impact_score", 1))

            source_raw = item.get("source_name", "")
            tier = get_source_tier(source_raw)
            tier_cfg = TIER_CONFIG.get(tier, TIER_CONFIG["news"])

            title_orig = html_mod.escape(item.get("title", ""))
            summary_zh_raw = _get_summary_zh(item)
            summary_zh_full = html_mod.escape(summary_zh_raw)
            summary_zh = html_mod.escape(_truncate(summary_zh_raw, 200))
            url = item.get("source_url", "")
            item_date = item.get("date", "")
            region = html_mod.escape(item.get("region", ""))
            source_name = html_mod.escape(source_raw)

            # 中文主标题：优先 title_zh，回退到 summary_zh 前 80 字
            title_zh_raw = (item.get("title_zh") or "").strip()
            zh_headline = html_mod.escape(
                title_zh_raw if title_zh_raw else _truncate(summary_zh_raw, 80)
            )

            # 英文原标题作为次要链接
            if url:
                orig_link = (f'<a href="{html_mod.escape(url)}" target="_blank" '
                             f'rel="noopener" title="{summary_zh_full}">{title_orig}</a>')
            else:
                orig_link = f'<span title="{summary_zh_full}">{title_orig}</span>'

            cat_badge = (
                f'<span class="cat-badge" style="background:{style["bg"]};'
                f'color:{style["text"]};border:1px solid {style["border"]};">'
                f'{html_mod.escape(cat)}</span>'
            )
            status_badge = (
                f'<span class="status-badge" style="{status_css}">'
                f'{html_mod.escape(status)}</span>'
            )
            tier_badge = (
                f'<span class="tier-badge" style="background:{tier_cfg["bg"]};'
                f'color:{tier_cfg["text"]};border:1px solid {tier_cfg["border"]};">'
                f'{tier_cfg["label"]}</span>'
            )

            rows_html += (
                f'\n        <tr data-date="{html_mod.escape(item_date)}" '
                f'data-cat="{html_mod.escape(cat)}" data-region="{region}" '
                f'data-group="{html_mod.escape(group)}" '
                f'data-impact="{impact}" '
                f'style="border-left:3px solid {style["border"]};">'
                f'<td class="td-region">{region}</td>'
                f'<td class="td-cat">{cat_badge}</td>'
                f'<td class="td-title">'
                f'<span class="td-title-zh">{zh_headline}</span>'
                f'<span class="td-title-orig">{orig_link}</span>'
                f'{"<br><span class=td-source>" + tier_badge + " " + source_name + "</span>" if source_name else ""}'
                f'</td>'
                f'<td class="td-date">{html_mod.escape(item_date)}</td>'
                f'<td class="td-status">{status_badge}</td>'
                f'<td class="td-summary">{summary_zh}</td>'
                f'</tr>'
            )

    legend_html = _build_legend_html()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_mod.escape(title)}</title>
<style>
/* ── 基础 Reset ── */
* {{ margin:0; padding:0; box-sizing:border-box; }}

/* ── 全局：Instagram 风清爽配色 ── */
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Noto Sans SC", "PingFang SC", "Helvetica Neue", sans-serif;
    background: #F5F5F7;
    color: #1D1D1F;
    padding: 28px 24px;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 1700px; margin: 0 auto; }}

/* ── 头部（白底，logo 原色显示） ── */
.header {{
    background: #FFFFFF;
    border-radius: 16px;
    padding: 18px 24px;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    box-shadow: 0 1px 0 #E8E8ED, 0 2px 8px rgba(0,0,0,0.04);
}}
.header-left h1 {{
    font-size: 19px;
    font-weight: 700;
    color: #1D1D1F;
    letter-spacing: -0.2px;
}}
.header-left .meta {{
    font-size: 12px;
    color: #86868B;
    margin-top: 3px;
    letter-spacing: 0.1px;
}}
.header-brand {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}}
.header-logo {{
    height: 34px;
    width: auto;
    object-fit: contain;
}}
.brand-name {{
    font-size: 12px;
    font-weight: 700;
    color: #86868B;
    letter-spacing: 2px;
    text-transform: uppercase;
    border-left: 1px solid #E8E8ED;
    padding-left: 12px;
    white-space: nowrap;
}}

/* ── 卡片通用 ── */
.card {{
    background: #FFFFFF;
    border-radius: 12px;
    box-shadow: 0 1px 0 #E8E8ED, 0 2px 6px rgba(0,0,0,0.03);
    margin-bottom: 12px;
}}

/* ── 分类颜色图例 ── */
.legend {{
    padding: 12px 18px;
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    align-items: center;
}}
.legend::before {{
    content: "分类";
    font-size: 11px;
    color: #86868B;
    font-weight: 600;
    white-space: nowrap;
    margin-right: 4px;
}}
.legend-item {{
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
}}

/* ── 筛选栏 ── */
.toolbar {{
    padding: 12px 18px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
}}
.toolbar label {{
    font-size: 11px;
    color: #86868B;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
.toolbar select, .toolbar input {{
    padding: 6px 10px;
    border: 1px solid #E8E8ED;
    border-radius: 8px;
    font-size: 12px;
    color: #1D1D1F;
    background: #F5F5F7;
    outline: none;
    transition: border-color 0.15s, background 0.15s;
}}
.toolbar select:focus, .toolbar input:focus {{
    border-color: #6E6EF7;
    background: #FFFFFF;
    box-shadow: 0 0 0 3px rgba(110,110,247,0.08);
}}
.toolbar input {{ width: 210px; }}
.result-count {{ margin-left: auto; font-size: 11px; color: #86868B; }}

/* ── 表格 ── */
.table-wrap {{
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 1px 0 #E8E8ED, 0 2px 6px rgba(0,0,0,0.03);
}}
table {{ width: 100%; border-collapse: collapse; background: white; }}
thead tr {{ background: #F5F5F7; border-bottom: 1px solid #E8E8ED; }}
th {{
    padding: 10px 12px;
    text-align: left;
    font-size: 10.5px;
    font-weight: 700;
    color: #86868B;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    cursor: pointer;
    white-space: nowrap;
    user-select: none;
}}
th:hover {{ color: #1D1D1F; }}
th .sort-icon {{ opacity: 0.35; margin-left: 3px; font-size: 9px; }}
th.sorted .sort-icon {{ opacity: 0.9; color: #6E6EF7; }}

/* ── 分组 header 行（柔和紫蓝） ── */
.group-row td.group-header {{
    background: #F0F0FF;
    color: #3D3D9E;
    font-size: 11.5px;
    font-weight: 700;
    padding: 8px 14px;
    letter-spacing: 0.4px;
    border-left: 3px solid #6E6EF7;
}}
.group-count {{
    display: inline-block;
    background: rgba(110,110,247,0.12);
    color: #5757D9;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 8px;
    border-radius: 10px;
    margin-left: 8px;
    vertical-align: middle;
}}

/* ── 数据行 ── */
tbody tr:not(.group-row) {{
    border-bottom: 1px solid #F5F5F7;
    transition: background 0.12s;
}}
tbody tr:not(.group-row):hover {{ background: #FAFAFF; }}
td {{ padding: 9px 12px; font-size: 12px; vertical-align: top; }}

.td-region {{
    white-space: nowrap;
    font-weight: 600;
    color: #6E6EF7;
    font-size: 11px;
}}
.td-cat {{ white-space: nowrap; }}
.td-title {{ min-width: 200px; max-width: 340px; line-height: 1.55; }}
.td-title-zh {{
    display: block;
    font-weight: 600;
    color: #1D1D1F;
    font-size: 12.5px;
    line-height: 1.6;
    margin-bottom: 4px;
}}
.td-title-orig {{
    display: block;
    font-size: 10.5px;
    color: #AEAEB2;
    margin-top: 1px;
}}
.td-title-orig a {{ color: #AEAEB2; text-decoration: none; }}
.td-title-orig a:hover {{ text-decoration: underline; color: #636366; }}
.td-source {{
    font-size: 10px;
    color: #AEAEB2;
    margin-top: 3px;
    display: block;
}}
.td-date {{
    white-space: nowrap;
    font-size: 11.5px;
    color: #636366;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
}}
.td-status {{ white-space: nowrap; }}
.td-summary {{ max-width: 320px; color: #636366; line-height: 1.55; font-size: 11px; }}

/* ── 标签 badges ── */
.cat-badge {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
}}
.status-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
}}
.tier-badge {{
    display: inline-block;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    white-space: nowrap;
    vertical-align: middle;
}}

/* ── 无数据提示 ── */
.no-data {{
    text-align: center;
    padding: 56px;
    color: #AEAEB2;
    font-size: 13px;
    display: none;
}}

/* ── 页脚 ── */
.footer {{
    margin-top: 24px;
    text-align: center;
    font-size: 11px;
    color: #AEAEB2;
    padding-bottom: 8px;
    letter-spacing: 0.3px;
}}

/* ── 响应式 ── */
@media (max-width: 900px) {{
    .td-summary {{ display: none; }}
}}
</style>
</head>
<body>
<div class="container">

  <!-- 头部 -->
  <div class="header">
    <div class="header-left">
      <h1>{html_mod.escape(title)}</h1>
      <div class="meta">生成时间：{now}&nbsp;&nbsp;·&nbsp;&nbsp;共 {len(items)} 条动态</div>
    </div>
    <div class="header-brand">
      {logo_html}
      <span class="brand-name">Lilith Legal</span>
    </div>
  </div>

  <!-- 筛选栏 -->
  <div class="card">
  <div class="toolbar">
    <label>地区</label>
    <select id="fGroup" onchange="applyFilters()">
      <option value="">全部地区</option>
    </select>
    <label>分类</label>
    <select id="fCat" onchange="applyFilters()">
      <option value="">全部</option>
    </select>
    <label>状态</label>
    <select id="fStatus" onchange="applyFilters()">
      <option value="">全部</option>
    </select>
    <input type="search" id="fKeyword" placeholder="🔍 关键词搜索..." oninput="applyFilters()">
    <span class="result-count" id="resultCount"></span>
  </div>
  </div>

  <!-- 表格 -->
  <div class="table-wrap">
    <table id="mainTable">
      <thead>
        <tr>
          <th onclick="sortTable(0)">区域 <span class="sort-icon">⇅</span></th>
          <th onclick="sortTable(1)">类别 <span class="sort-icon">⇅</span></th>
          <th onclick="sortTable(2)">标题 <span class="sort-icon">⇅</span></th>
          <th onclick="sortTable(3)">发布时间 <span class="sort-icon">⇅</span></th>
          <th onclick="sortTable(4)">标签 <span class="sort-icon">⇅</span></th>
          <th>摘要(中文)</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>
    <div class="no-data" id="noData">暂无匹配数据</div>
  </div>

  <!-- 页脚 -->
  <div class="footer">Lilith Legal &nbsp;·&nbsp; 全球游戏合规监控 &nbsp;·&nbsp; 仅供内部参考</div>

</div>
<script>
(function() {{
  // 初始化地区分组下拉
  const rows = document.querySelectorAll('#mainTable tbody tr:not(.group-row)');
  const groups = new Set(), cats = new Set(), statuses = new Set();
  rows.forEach(r => {{
    if (r.dataset.group) groups.add(r.dataset.group);
    if (r.dataset.cat)   cats.add(r.dataset.cat);
    const badge = r.querySelector('.status-badge');
    if (badge) statuses.add(badge.textContent.trim());
  }});

  // 按预设顺序填充地区下拉
  const groupOrder = ["东南亚","亚太","中东","欧洲","北美","南美","日韩台","其他"];
  const fGroup = document.getElementById('fGroup');
  groupOrder.forEach(g => {{
    if (groups.has(g)) {{
      const o = document.createElement('option');
      o.value = g; o.textContent = g; fGroup.appendChild(o);
    }}
  }});

  const fill = (sel, vals) => {{
    [...vals].filter(Boolean).sort().forEach(v => {{
      const o = document.createElement('option');
      o.value = v; o.textContent = v; sel.appendChild(o);
    }});
  }};
  fill(document.getElementById('fCat'), cats);
  fill(document.getElementById('fStatus'), statuses);
  updateCount();
}})();

function applyFilters() {{
  const group  = document.getElementById('fGroup').value;
  const cat    = document.getElementById('fCat').value;
  const status = document.getElementById('fStatus').value;
  const kw     = document.getElementById('fKeyword').value.toLowerCase();

  const rows = document.querySelectorAll('#mainTable tbody tr:not(.group-row)');
  const groupVisible = {{}};
  let visible = 0;

  rows.forEach(r => {{
    let show = true;
    if (show && group  && r.dataset.group !== group) show = false;
    if (show && cat    && r.dataset.cat   !== cat)   show = false;
    if (show && status) {{
      const badge = r.querySelector('.status-badge');
      if (!badge || badge.textContent.trim() !== status) show = false;
    }}
    if (show && kw && !r.textContent.toLowerCase().includes(kw)) show = false;
    r.style.display = show ? '' : 'none';
    if (show) {{ visible++; groupVisible[r.dataset.group] = true; }}
  }});

  // 控制分组 header 显隐
  document.querySelectorAll('.group-row').forEach(r => {{
    r.style.display = groupVisible[r.dataset.group] ? '' : 'none';
  }});

  updateCount(visible);
}}

function updateCount(n) {{
  const total = document.querySelectorAll('#mainTable tbody tr:not(.group-row)').length;
  const cnt = (n === undefined) ? total : n;
  document.getElementById('resultCount').textContent = `显示 ${{cnt}} / ${{total}} 条`;
  document.getElementById('noData').style.display = cnt === 0 ? 'block' : 'none';
}}

let _sortDir = {{}};
function sortTable(col) {{
  const tbody = document.querySelector('#mainTable tbody');
  const dataRows = [...tbody.querySelectorAll('tr:not(.group-row)')];
  _sortDir[col] = !_sortDir[col];

  document.querySelectorAll('th').forEach((th, i) => {{
    th.classList.toggle('sorted', i === col);
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = (i === col) ? (_sortDir[col] ? '↑' : '↓') : '⇅';
  }});

  // 按列排序（忽略分组 header，排序后重新按分组插入）
  dataRows.sort((a, b) => {{
    let va = a.cells[col]?.textContent.trim() ?? '';
    let vb = b.cells[col]?.textContent.trim() ?? '';
    if (col === 3) return _sortDir[col] ? va.localeCompare(vb) : vb.localeCompare(va);
    return _sortDir[col] ? va.localeCompare(vb, 'zh') : vb.localeCompare(va, 'zh');
  }});

  // 把分组 header 和对应数据行重新排列
  const groupRows = [...tbody.querySelectorAll('.group-row')];
  const groupOrder = ["东南亚","亚太","中东","欧洲","北美","南美","日韩台","其他"];
  tbody.innerHTML = '';

  groupOrder.forEach(grp => {{
    const hdr = groupRows.find(r => r.dataset.group === grp);
    if (!hdr) return;
    const grpDataRows = dataRows.filter(r => r.dataset.group === grp);
    if (grpDataRows.length === 0) return;
    tbody.appendChild(hdr);
    grpDataRows.forEach(r => tbody.appendChild(r));
  }});
}}
</script>
</body>
</html>"""


def save_html(items: List[dict], filename: Optional[str] = None,
              period_label: str = "") -> str:
    ensure_output_dir()
    if not filename:
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    content = generate_html(items, period_label=period_label)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath
