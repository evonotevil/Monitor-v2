#!/usr/bin/env python3
"""
全球游戏行业立法动态监控工具 - 主入口
面向中资手游出海合规 (以原神发行方式为参考)

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
    """计算两个英文标题的 bigram 字符重叠率（0~1）。"""
    a, b = a.lower(), b.lower()
    if len(a) < 2 or len(b) < 2:
        return 0.0
    bg_a = {a[i:i + 2] for i in range(len(a) - 1)}
    bg_b = {b[i:i + 2] for i in range(len(b) - 1)}
    return len(bg_a & bg_b) / max(len(bg_a), len(bg_b))


def _deduplicate_items(items):
    """
    在同一「显示分组」且日期相差 ≤2 天的文章中，找出英文标题 bigram 相似度 >65%
    的文章对，只保留 impact_score 最高的那篇（相同则保留最早抓到的）。
    其余视为重复，丢弃前在摘要末尾追加多来源提示。

    注意：按显示分组（东南亚/欧洲/北美/其他…）而非原始 region 字段去重，
    这样来自不同子 region（如"全球"/"澳大利亚"/"英国"）但属同一显示组的
    同主题文章也能被合并。
    """
    from models import LegislationItem
    keep: list[LegislationItem] = []
    dropped: set[int] = set()   # 索引集合

    for i, item_i in enumerate(items):
        if i in dropped:
            continue
        group_i = _get_region_group(item_i.region)
        duplicates = []   # (j, sim)
        for j, item_j in enumerate(items):
            if j <= i or j in dropped:
                continue
            # 按显示分组比较，而非原始 region 字段
            if group_i != _get_region_group(item_j.region):
                continue
            # 日期差 ≤2 天
            try:
                from datetime import date
                d_i = date.fromisoformat(item_i.date)
                d_j = date.fromisoformat(item_j.date)
                if abs((d_i - d_j).days) > 2:
                    continue
            except ValueError:
                continue
            sim = _title_bigram_sim(item_i.title, item_j.title)
            if sim > 0.65:
                duplicates.append((j, sim))

        if duplicates:
            # 收集所有候选（包括 i 自身）
            group = [(i, 0.0)] + duplicates
            # 按 impact_score 降序排，分数相同则保留索引最小（先抓到的）
            group.sort(key=lambda x: (-items[x[0]].impact_score, x[0]))
            winner_idx = group[0][0]
            loser_count = len(group) - 1
            for idx, _ in group[1:]:
                dropped.add(idx)
            # 给保留项追加来源提示
            if loser_count > 0 and items[winner_idx].summary:
                items[winner_idx].summary += f" [另有 {loser_count} 篇同主题报道]"

    result = [item for i, item in enumerate(items) if i not in dropped]
    if len(items) != len(result):
        logger.info(
            f"[去重] 语义去重：{len(items)} 条 → {len(result)} 条"
            f"（合并 {len(items) - len(result)} 条高度相似文章）"
        )
    return result


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

                    item.summary_zh = translated.get("summary_zh", "")
                    item.title_zh   = translated.get("title_zh", "")

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
                        item.impact_score = score_impact(item.status, item.source_name)

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
            print_table(all_items)

            if args.output:
                if args.output.endswith(".html"):
                    path = save_html(all_items, args.output, period_label=label)
                else:
                    path = save_markdown(all_items, args.output)
                logger.info(f"报告已保存到: {path}")
            else:
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                prefix = {"week": "weekly", "month": "monthly", "all": "report"}.get(args.period, "report")
                md_path = save_markdown(all_items, f"{prefix}_{ts}.md")
                html_path = save_html(all_items, f"{prefix}_{ts}.html", period_label=label)
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

        fmt = args.format.lower()
        if fmt == "table":
            print_table(items)
        elif fmt in ("markdown", "md"):
            path = save_markdown(items, args.output) if args.output else save_markdown(items)
            print(f"Markdown 报告已保存到: {path}")
        elif fmt == "html":
            path = (save_html(items, args.output, period_label=label) if args.output
                    else save_html(items, period_label=label))
            print(f"HTML 报告已保存到: {path}")
        else:
            print_table(items)

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
