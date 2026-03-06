#!/usr/bin/env python3
"""
全球互联网内容平台合规动态监控工具 - 主入口
面向互联网内容平台（视频/直播/UGC/社交）的海外合规团队
聚焦：内容安全、未成年保护、数据隐私、版权、支付合规、商业化

用法:
    python monitor.py run                    # 执行一次完整抓取
    python monitor.py run --period week      # 周报 (近7天)
    python monitor.py run --period month     # 月报 (近30天)
    python monitor.py report                 # 从数据库生成报告
    python monitor.py report --period week   # 周报
    python monitor.py report --period month  # 月报
    python monitor.py report --format html   # 生成 HTML 报告
    python monitor.py query --keyword "loot box"  # 关键词搜索
    python monitor.py stats                  # 查看数据库统计
    python monitor.py schedule --interval 24 # 每24小时自动执行
"""

import argparse
import logging
import re
import sys
import time
from datetime import datetime

from models import Database
from fetcher import fetch_and_process
from translator import translate_items_batch
from reporter import print_table, save_markdown, save_html, generate_markdown
from utils import _get_region_group
from config import PERIOD_DAYS

# ─── 日志配置 ─────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/monitor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def _period_to_days(period: str) -> int:
    """将周期名称转为天数"""
    return PERIOD_DAYS.get(period, PERIOD_DAYS["all"])


# ─── 语义去重（同地区/同日期窗口内高度相似的文章只保留一条）────────────

def _title_bigram_sim(a: str, b: str) -> float:
    """计算两个标题的 bigram 字符 Jaccard 重叠率（0~1）。"""
    a, b = a.lower(), b.lower()
    if len(a) < 2 or len(b) < 2:
        return 0.0
    bg_a = {a[i:i + 2] for i in range(len(a) - 1)}
    bg_b = {b[i:i + 2] for i in range(len(b) - 1)}
    union = bg_a | bg_b
    return len(bg_a & bg_b) / len(union) if union else 0.0


# ─── 事件指纹（事件聚类核心）────────────────────────────────────────────

_FP_STOPWORDS = {
    'the','a','an','of','in','to','for','and','or','is','are','was','be',
    'by','on','at','with','that','this','from','has','have','been','will',
    'its','it','as','not','but','also','after','before','new','about','over',
    'says','said','would','could','should','law','rule','rules','regulation',
    'regulations','platform','platforms','digital','online','social','media',
}


def _event_fingerprint(title: str) -> frozenset:
    """
    从标题中提取事件指纹：数字 + 大写缩写 + 长内容词 + 内容词二元组。

    为什么需要指纹而不仅用 bigram 相似度：
    "Karnataka bans social media for users under 16" 和
    "India: Under-16 social media ban enacted in Karnataka"
    标题 bigram 相似度仅约 0.15，但两篇文章都有 #16 和 "karnataka"（长内容词），
    通过 _same_event_by_fingerprint 的规则可识别为同一事件。
    """
    tokens = set()
    # 1. 数字（年龄限制、罚款金额）
    for m in re.finditer(r'\d+', title):
        tokens.add(f"#{m.group()}")
    # 2. 大写缩写 (GDPR / DSA / FTC / COPPA …)
    for m in re.finditer(r'\b[A-Z]{2,}\b', title):
        tokens.add(m.group().lower())
    # 3. 内容词（去停用词）
    words = [
        w for w in re.findall(r"[a-z\u4e00-\u9fff]{2,}", title.lower())
        if w not in _FP_STOPWORDS
    ]
    # 3a. 长内容词作为独立 token（≥5 字符，代表专有名词/地名）
    for w in words:
        if len(w) >= 5:
            tokens.add(w)
    # 3b. 内容词二元组
    for i in range(len(words) - 1):
        tokens.add(f"{words[i]}_{words[i + 1]}")
    return frozenset(tokens)


def _fp_sim(a: frozenset, b: frozenset) -> float:
    """两个事件指纹的 Jaccard 相似度（0~1）。"""
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _same_event_by_fingerprint(fp_a: frozenset, fp_b: frozenset) -> bool:
    """
    精确规则判断两个指纹是否指向同一事件。

    比单纯的 Jaccard 更可靠，因为 Jaccard 容易被 GDPR/2026 等通用词干扰。

    规则（满足其一即判为同一事件）：
      ① Jaccard ≥ 0.30（大量共同 token）
      ② 共同 token 中同时包含：
           • 非年份数字（年龄/金额 < 4位年份）→ 具体事件参数
           • ≥6 字符的专有名词 → 具体地点/机构名
    """
    common = fp_a & fp_b
    if not common:
        return False
    if _fp_sim(fp_a, fp_b) >= 0.30:
        return True
    # 精确规则：非年份数字 + 长专有名词
    has_specific_num = any(
        t.startswith('#') and t[1:].isdigit()
        and not (len(t[1:]) == 4 and t[1:2] == '2')   # 排除 2xxx 年份
        for t in common
    )
    has_entity = any(
        not t.startswith('#') and '_' not in t and len(t) >= 6
        for t in common
    )
    return has_specific_num and has_entity


def _deduplicate_items(items):
    """
    抓取时去重（事件聚类第一层）：同一显示分组内，日期差 ≤7 天的文章中，
    满足以下任一条件则视为同一事件：
      ① 标题 bigram Jaccard > 0.55（高度相同措辞）
      ② 事件指纹 Jaccard > 0.30（不同措辞但指向同一法案/事件）

    保留 impact_score 最高的那篇（相同则保留最早抓到的）。
    """
    from models import LegislationItem
    from datetime import date as _date
    dropped: set[int] = set()

    # 预计算指纹
    fps = [_event_fingerprint(item.title) for item in items]

    for i, item_i in enumerate(items):
        if i in dropped:
            continue
        group_i = _get_region_group(item_i.region)
        duplicates = []

        for j, item_j in enumerate(items):
            if j <= i or j in dropped:
                continue
            if group_i != _get_region_group(item_j.region):
                continue
            try:
                d_i = _date.fromisoformat(item_i.date)
                d_j = _date.fromisoformat(item_j.date)
                if abs((d_i - d_j).days) > 7:
                    continue
            except ValueError:
                continue

            # ① 标题 bigram 相似度（原有逻辑，阈值从 0.65 → 0.55）
            sim = _title_bigram_sim(item_i.title, item_j.title)
            if sim > 0.55:
                duplicates.append(j)
                continue

            # ② 事件指纹精确规则（同一法案不同标题措辞）
            if _same_event_by_fingerprint(fps[i], fps[j]):
                duplicates.append(j)

        if duplicates:
            group = [i] + duplicates
            group.sort(key=lambda x: (-items[x].impact_score, x))
            winner_idx = group[0]
            loser_count = len(group) - 1
            for idx in group[1:]:
                dropped.add(idx)
            if loser_count > 0 and items[winner_idx].summary:
                items[winner_idx].summary += f" [另有 {loser_count} 篇同主题报道]"

    result = [item for i, item in enumerate(items) if i not in dropped]
    if len(items) != len(result):
        logger.info(
            f"[去重] 事件聚类：{len(items)} 条 → {len(result)} 条"
            f"（合并 {len(items) - len(result)} 条同主题文章）"
        )
    return result


def _deduplicate_report_items(items: list, merge_fn=None, date_window_days: int = 10) -> list:
    """
    报告层事件聚类（第二层）：对 DB 查出的已翻译条目做跨来源合并。

    识别同一事件的判定（满足其一即合并）：
      ① title_zh bigram Jaccard > 0.55（中文标题高度相似）
      ② 英文原标题事件指纹 Jaccard > 0.30（同一法案不同报道角度）

    日期窗口：date_window_days 内（月报默认 10 天，同一法案进展通常集中在
    一两周内；跨周期的不同动态属于独立事件，不应强制合并）。

    保留日期最新、id 最小的条目作为"代表"，其余摘要通过 merge_fn 合并。
    """
    from datetime import date as _date
    dropped: set[int] = set()

    # 预计算英文原标题的事件指纹
    fps = [_event_fingerprint(item.get("title", "")) for item in items]

    for i, item_i in enumerate(items):
        if i in dropped:
            continue
        group_i = _get_region_group(item_i.get("region", ""))
        title_i_zh = (item_i.get("title_zh") or item_i.get("title") or "").strip()
        if not title_i_zh:
            continue

        duplicates = []
        for j, item_j in enumerate(items):
            if j <= i or j in dropped:
                continue
            if group_i != _get_region_group(item_j.get("region", "")):
                continue
            try:
                d_i = _date.fromisoformat(item_i.get("date", ""))
                d_j = _date.fromisoformat(item_j.get("date", ""))
                if abs((d_i - d_j).days) > date_window_days:
                    continue
            except ValueError:
                continue

            # ① 中文标题 bigram 相似度（原有逻辑，阈值从 0.80 → 0.55）
            title_j_zh = (item_j.get("title_zh") or item_j.get("title") or "").strip()
            if _title_bigram_sim(title_i_zh, title_j_zh) > 0.55:
                duplicates.append(j)
                continue

            # ② 英文原标题事件指纹精确规则（识别"同一法案不同措辞"的报道）
            if _same_event_by_fingerprint(fps[i], fps[j]):
                duplicates.append(j)

        if duplicates:
            group_idxs = [i] + duplicates
            # 日期最新优先；相同日期取 id 最小（最早入库，通常是原始报道）
            group_idxs.sort(
                key=lambda x: (items[x].get("date", ""), -(items[x].get("id") or 0)),
                reverse=True,
            )
            winner_idx = group_idxs[0]
            loser_count = len(group_idxs) - 1
            for idx in group_idxs[1:]:
                dropped.add(idx)

            if loser_count > 0:
                title_zh = (items[winner_idx].get("title_zh") or "").strip()
                cluster_summaries = []
                seen_s: set = set()
                for idx in group_idxs:
                    s = (items[idx].get("summary_zh") or items[idx].get("summary") or "").strip()
                    if s and s not in seen_s:
                        cluster_summaries.append(s)
                        seen_s.add(s)

                if merge_fn and len(cluster_summaries) >= 2 and title_zh:
                    try:
                        merged = merge_fn(title_zh, cluster_summaries)
                        if merged:
                            items[winner_idx]["summary_zh"] = (
                                merged + f"（汇总了来自 {len(group_idxs)} 个源的报道）"
                            )
                    except Exception as _me:
                        logger.warning(f"[集群合并] 摘要合并失败: {_me}")
                        if items[winner_idx].get("summary_zh"):
                            items[winner_idx]["summary_zh"] += f" [另有 {loser_count} 篇同主题报道]"
                else:
                    if items[winner_idx].get("summary_zh"):
                        items[winner_idx]["summary_zh"] += f" [另有 {loser_count} 篇同主题报道]"

    result = [item for i, item in enumerate(items) if i not in dropped]
    if len(items) != len(result):
        logger.info(
            f"[报告去重] 事件聚类：{len(items)} 条 → {len(result)} 条"
            f"（合并 {len(items) - len(result)} 条跨来源同主题报道）"
        )
    return result


# ─── 报告条目截断（主报告 + 附录）────────────────────────────────────────

MAIN_REPORT_LIMIT = 30   # 主报告最多保留条数
MAX_PER_REGION    = 5    # 每个显示分组最多入选条数（防止单一地区刷屏）


def _split_main_appendix(items: list) -> tuple:
    """
    漏斗最终截断：按 impact_score 降序，同时满足：
      1. 总数 ≤ MAIN_REPORT_LIMIT (30)
      2. 每个显示分组（欧洲/北美/亚太…）≤ MAX_PER_REGION (5)

    算法：
      Pass-1: 遍历全局排序列表，每条目若所在分组未达上限则入选主报告。
      Pass-2: 若主报告不足 30 条（因分组均衡导致空位），从剩余中补充（不限分组）。
      主报告最终按 impact_score 重排供渲染。
    """
    sorted_items = sorted(
        items,
        key=lambda x: (int(x.get("impact_score", 1)), x.get("date", "")),
        reverse=True,
    )

    region_counts: dict = {}
    main: list = []
    reserve: list = []   # 未入选，按 impact_score 降序

    # Pass-1：按分组均衡入选（硬上限 MAX_PER_REGION）
    for item in sorted_items:
        rg = _get_region_group(item.get("region", "其他"))
        if len(main) < MAIN_REPORT_LIMIT and region_counts.get(rg, 0) < MAX_PER_REGION:
            main.append(item)
            region_counts[rg] = region_counts.get(rg, 0) + 1
        else:
            reserve.append(item)

    # Pass-2：若主报告不满 30，用宽松上限（MAX_PER_REGION + 2 = 7）从剩余补充
    # 仍逐个检查分组计数，防止单一地区垄断
    RELAXED_CAP = MAX_PER_REGION + 2
    if len(main) < MAIN_REPORT_LIMIT and reserve:
        new_reserve = []
        for item in reserve:
            rg = _get_region_group(item.get("region", "其他"))
            if len(main) < MAIN_REPORT_LIMIT and region_counts.get(rg, 0) < RELAXED_CAP:
                main.append(item)
                region_counts[rg] = region_counts.get(rg, 0) + 1
            else:
                new_reserve.append(item)
        reserve = new_reserve

    appendix = reserve
    main.sort(
        key=lambda x: (int(x.get("impact_score", 1)), x.get("date", "")),
        reverse=True,
    )

    if appendix:
        region_summary = ", ".join(
            f"{rg}:{cnt}" for rg, cnt in sorted(region_counts.items())
        )
        logger.info(
            f"[截断] 主报告 {len(main)} 条（≤{MAX_PER_REGION}/地区·总限{MAIN_REPORT_LIMIT}）"
            f"，附录 {len(appendix)} 条 | 分组：{region_summary}"
        )
    return main, appendix


def _period_label(period: str) -> str:
    labels = {"week": "周报（近7天）", "month": "月报（近30天）", "all": "全量报告"}
    return labels.get(period, "全量报告")


# ─── 命令: run ───────────────────────────────────────────────────────

def cmd_run(args):
    """执行一次完整的抓取-处理-存储流程"""
    days = _period_to_days(args.period)
    label = _period_label(args.period)
    logger.info(f"开始执行抓取 [{label}]...")
    db = Database()

    try:
        items = fetch_and_process(max_days=days)

        if items:
            # 语义去重：同地区同日期窗口内高度相似的文章合并为一条
            items = _deduplicate_items(items)

            no_translate = getattr(args, 'no_translate', False)
            if no_translate:
                logger.info("已跳过翻译 (--no-translate)")
            else:
                from classifier import score_impact
                logger.info(f"正在批量翻译并分类 ({len(items)} 条，每批 3 篇)...")
                kept_items = []
                llm_filtered = 0

                # ── 批量翻译：3 条/LLM 请求，速度 3× ─────────────────
                items_dicts = [item.to_dict() for item in items]
                translated_list = translate_items_batch(items_dicts, batch_size=3)

                for item, translated in zip(items, translated_list):
                    # ── LLM 相关性过滤 ─────────────────────────────────
                    if translated.get("_llm_is_relevant") is False:
                        llm_filtered += 1
                        continue

                    item.summary_zh      = translated.get("summary_zh", "")
                    item.title_zh        = translated.get("title_zh", "")
                    item.detail_zh       = translated.get("detail_zh", "")
                    item.compliance_note = translated.get("compliance_note", "")

                    # ── 应用 LLM 分类结果（覆盖正则，空值保留正则原值）──
                    llm_region   = translated.get("_llm_region", "")
                    llm_category = translated.get("_llm_category_l1", "")
                    llm_status   = translated.get("_llm_status", "")

                    if llm_region:
                        item.region = llm_region
                    if llm_category:
                        item.category_l1 = llm_category
                    if llm_status and llm_status != item.status:
                        logger.info(
                            f"[LLM分类] 状态更新 '{item.status}' → '{llm_status}'"
                            f" | {item.title[:50]}"
                        )
                        item.status = llm_status
                        item.impact_score = score_impact(
                            item.status, item.source_name,
                            region=item.region,
                            text=f"{item.title} {item.summary}",
                        )

                    kept_items.append(item)

                if llm_filtered:
                    logger.info(
                        f"[LLM过滤] 共过滤 {llm_filtered} 条不相关文章，"
                        f"保留 {len(kept_items)} 条"
                    )
                items = kept_items

            new_count = db.bulk_upsert(items)
            logger.info(f"新增 {new_count} 条记录 (共处理 {len(items)} 条)")
            db.log_fetch("full_run", new_count, "ok")
        else:
            logger.info("本次抓取未获取到新数据")
            db.log_fetch("full_run", 0, "ok", "no new items")

        all_items = db.query_items(days=days)
        if all_items:
            # 跨来源去重 + LLM 集群摘要合并
            try:
                from translator import merge_cluster_summary
                all_items = _deduplicate_report_items(all_items, merge_fn=merge_cluster_summary)
            except ImportError:
                all_items = _deduplicate_report_items(all_items)

            # 按 impact_score 截断：主报告 top-40，其余放附录
            main_items, appendix_items = _split_main_appendix(all_items)
            print_table(main_items)

            # 生成月度合规形势综述（LLM，失败时静默回退）
            exec_summary = ""
            try:
                from translator import generate_executive_summary
                logger.info("正在生成月度合规形势综述...")
                exec_summary = generate_executive_summary(main_items)
            except Exception as _e:
                logger.warning(f"综述生成失败，跳过: {_e}")

            if args.output:
                if args.output.endswith(".html"):
                    path = save_html(main_items, args.output, period_label=label,
                                     exec_summary=exec_summary,
                                     appendix_items=appendix_items)
                else:
                    path = save_markdown(main_items, args.output)
                logger.info(f"报告已保存到: {path}")
            else:
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                prefix = {"week": "weekly", "month": "monthly", "all": "report"}.get(args.period, "report")
                md_path = save_markdown(main_items, f"{prefix}_{ts}.md")
                html_path = save_html(main_items, f"{prefix}_{ts}.html", period_label=label,
                                      exec_summary=exec_summary,
                                      appendix_items=appendix_items)
                logger.info(f"Markdown 报告: {md_path}")
                logger.info(f"HTML 报告: {html_path}")

    except Exception as e:
        logger.error(f"抓取执行失败: {e}", exc_info=True)
        db.log_fetch("full_run", 0, "error", str(e))
    finally:
        db.close()


# ─── 命令: report ────────────────────────────────────────────────────

def cmd_report(args):
    """从数据库生成报告"""
    days = _period_to_days(args.period)
    label = _period_label(args.period)
    db = Database()
    try:
        items = db.query_items(
            region=args.region,
            category_l1=args.category,
            status=args.status,
            keyword=args.keyword,
            days=days,
        )

        if not items:
            print(f"数据库中暂无 [{label}] 匹配数据。请先运行 `python monitor.py run` 抓取数据。")
            return

        try:
            from translator import merge_cluster_summary
            items = _deduplicate_report_items(items, merge_fn=merge_cluster_summary)
        except ImportError:
            items = _deduplicate_report_items(items)

        main_items, appendix_items = _split_main_appendix(items)

        exec_summary = ""
        fmt = args.format.lower()
        if fmt == "html":
            try:
                from translator import generate_executive_summary
                exec_summary = generate_executive_summary(main_items)
            except Exception as _e:
                logger.warning(f"综述生成失败，跳过: {_e}")

        if fmt == "table":
            print_table(main_items)
        elif fmt in ("markdown", "md"):
            path = save_markdown(main_items, args.output) if args.output else save_markdown(main_items)
            print(f"Markdown 报告已保存到: {path}")
        elif fmt == "html":
            path = (save_html(main_items, args.output, period_label=label,
                              exec_summary=exec_summary, appendix_items=appendix_items)
                    if args.output
                    else save_html(main_items, period_label=label,
                                   exec_summary=exec_summary, appendix_items=appendix_items))
            print(f"HTML 报告已保存到: {path}")
        else:
            print_table(main_items)

    finally:
        db.close()


# ─── 命令: query ─────────────────────────────────────────────────────

def cmd_query(args):
    """关键词查询"""
    db = Database()
    try:
        days = _period_to_days(getattr(args, 'period', 'all'))
        items = db.query_items(
            region=args.region,
            keyword=args.keyword,
            days=days,
        )
        if items:
            print_table(items)
        else:
            print("未找到匹配的记录。")
    finally:
        db.close()


# ─── 命令: stats ─────────────────────────────────────────────────────

def cmd_stats(args):
    """查看数据库统计信息"""
    db = Database()
    try:
        stats = db.get_stats()
        print()
        print(f"{'='*50}")
        print(f"  数据库统计")
        print(f"{'='*50}")
        print(f"  总记录数: {stats['total']}")
        print(f"  最新日期: {stats['latest_date'] or 'N/A'}")
        print()

        if stats["by_region"]:
            print(f"  按地区分布:")
            for region, cnt in stats["by_region"].items():
                bar = "█" * min(cnt, 30)
                print(f"    {region:<12} {cnt:>4}  {bar}")
            print()

        if stats["by_category"]:
            print(f"  按分类分布:")
            for cat, cnt in stats["by_category"].items():
                bar = "█" * min(cnt, 30)
                print(f"    {cat:<12} {cnt:>4}  {bar}")
            print()

    finally:
        db.close()


# ─── 命令: retranslate ───────────────────────────────────────────────

def cmd_retranslate(args):
    """
    清空含脏词/格式问题的历史翻译字段，然后立即重新翻译。
    用途：当 translator.py 中的 _TERM_CORRECTIONS 或 prompt 更新后，
    让旧数据库条目也能享受最新翻译质量。
    """
    from translator import _TERM_CORRECTIONS, translate_item_fields

    db = Database()
    try:
        # ── 阶段 1：清空含脏词的翻译字段 ──────────────────────────────
        dirty_terms = list(_TERM_CORRECTIONS.keys())
        # 同时清理常见格式问题：【xxx】栏目前缀、问句标题（以"？"结尾）
        extra_patterns = ["【"]
        cleared = db.clear_stale_translations(dirty_terms + extra_patterns)
        logger.info(f"[重译] 已清空 {cleared} 条含脏词翻译的条目")

        force = getattr(args, "force", False)
        if cleared == 0 and not force:
            logger.info("[重译] 无需重译条目，数据库已是最新。若想强制全量重译请加 --force")
            return

        # ── 阶段 2：查询所有 title_zh 为空的条目并重译 ─────────────────
        limit = getattr(args, "limit", 100)
        items_dicts = db.query_items_untranslated(limit=limit)
        if not items_dicts:
            logger.info("[重译] 没有待翻译条目，完成。")
            return

        logger.info(f"[重译] 开始重译 {len(items_dicts)} 条条目（限额 {limit}）…")
        updated = 0
        for item_dict in items_dicts:
            translated = translate_item_fields(item_dict)
            if translated.get("title_zh"):
                db.update_translation(
                    item_dict["id"],
                    translated["title_zh"],
                    translated.get("summary_zh", ""),
                )
                updated += 1
                logger.info(f"  ✓ [{item_dict.get('region','')}] {translated['title_zh'][:40]}")

        logger.info(f"[重译] 完成，共更新 {updated} 条。")
    finally:
        db.close()


# ─── 命令: schedule ──────────────────────────────────────────────────

def cmd_schedule(args):
    """定时调度执行"""
    interval_hours = args.interval
    logger.info(f"启动定时监控, 间隔 {interval_hours} 小时")
    logger.info("按 Ctrl+C 停止")

    while True:
        try:
            logger.info(f"{'='*40} 定时任务开始 {'='*40}")
            cmd_run(args)
            logger.info(f"下次执行时间: {interval_hours} 小时后")
            time.sleep(interval_hours * 3600)
        except KeyboardInterrupt:
            logger.info("定时任务已停止")
            break
        except Exception as e:
            logger.error(f"定时任务异常: {e}", exc_info=True)
            logger.info(f"将在 {interval_hours} 小时后重试")
            time.sleep(interval_hours * 3600)


# ─── CLI 参数解析 ─────────────────────────────────────────────────────

def _add_period_arg(p):
    p.add_argument(
        "--period", "-p",
        choices=["week", "month", "all"],
        default="all",
        help="报告周期: week=周报(近7天)  month=月报(近30天)  all=全量(默认)",
    )


def main():
    parser = argparse.ArgumentParser(
        description="全球游戏行业立法动态监控工具 (中资手游出海合规视角)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run
    p_run = subparsers.add_parser("run", help="执行一次完整抓取并生成报告")
    _add_period_arg(p_run)
    p_run.add_argument("--output", "-o", help="输出文件名 (支持 .md / .html)")
    p_run.add_argument("--no-translate", action="store_true", help="跳过翻译(加快速度)")
    p_run.set_defaults(func=cmd_run)

    # report
    p_report = subparsers.add_parser("report", help="从数据库生成报告")
    p_report.add_argument("--format", "-f", default="html",
                          choices=["table", "markdown", "md", "html"],
                          help="输出格式 (默认 html)")
    _add_period_arg(p_report)
    p_report.add_argument("--region", "-r", help="按地区筛选")
    p_report.add_argument("--category", "-c", help="按一级分类筛选")
    p_report.add_argument("--status", "-s", help="按状态筛选")
    p_report.add_argument("--keyword", "-k", help="关键词过滤")
    p_report.add_argument("--output", "-o", help="输出文件名")
    p_report.set_defaults(func=cmd_report)

    # query
    p_query = subparsers.add_parser("query", help="关键词查询")
    p_query.add_argument("--keyword", "-k", required=True, help="搜索关键词")
    p_query.add_argument("--region", "-r", help="按地区筛选")
    _add_period_arg(p_query)
    p_query.set_defaults(func=cmd_query)

    # stats
    p_stats = subparsers.add_parser("stats", help="查看数据库统计")
    p_stats.set_defaults(func=cmd_stats)

    # retranslate
    p_retrans = subparsers.add_parser(
        "retranslate",
        help="清空含脏词/格式问题的历史翻译并重新生成（prompt 更新后用）",
    )
    p_retrans.add_argument(
        "--force", action="store_true",
        help="即使没有检测到脏词也强制重译全部 title_zh 为空的条目",
    )
    p_retrans.add_argument(
        "--limit", type=int, default=100,
        help="单次最多重译条数（默认 100，避免超 Groq 配额）",
    )
    p_retrans.set_defaults(func=cmd_retranslate)

    # schedule
    p_schedule = subparsers.add_parser("schedule", help="定时自动执行")
    p_schedule.add_argument("--interval", type=float, default=24,
                            help="执行间隔(小时), 默认24")
    _add_period_arg(p_schedule)
    p_schedule.add_argument("--output", "-o", help="输出文件名")
    p_schedule.set_defaults(func=cmd_schedule)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
