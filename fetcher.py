"""
数据抓取模块 - RSS 解析 & Google News 搜索
严格过滤：只保留真正的立法/监管/执法动态
"""

import re
import json
import time
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote_plus
import concurrent.futures

import requests
from bs4 import BeautifulSoup

from config import (
    RSS_FEEDS,
    KEYWORDS,
    GOOGLE_NEWS_SEARCH_TEMPLATE,
    GOOGLE_NEWS_REGIONS,
    FETCH_TIMEOUT,
    MAX_CONCURRENT_REQUESTS,
    MAX_ARTICLE_AGE_DAYS,
)
from models import LegislationItem
from classifier import classify_article, is_china_mainland

logger = logging.getLogger(__name__)

# ─── HTTP 工具 ────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,ja;q=0.6,ko;q=0.5",
}


def safe_get(url: str, timeout: int = FETCH_TIMEOUT) -> Optional[requests.Response]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        logger.warning(f"请求失败 {url}: {e}")
        return None


# ─── RSS 解析 ─────────────────────────────────────────────────────────

def parse_rss_date(date_str: str) -> str:
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d")


def clean_html(html_text: str) -> str:
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:500]


def fetch_rss_feed(feed_config: dict) -> List[dict]:
    url = feed_config["url"]
    resp = safe_get(url)
    if not resp:
        return []

    items = []
    try:
        root = ET.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            description = item.findtext("description", "")
            items.append({
                "title": clean_html(title),
                "url": link,
                "date": parse_rss_date(pub_date),
                "summary": clean_html(description),
                "source": feed_config["name"],
                "region": feed_config.get("region", ""),
                "lang": feed_config.get("lang", "en"),
            })

        for entry in root.findall(".//atom:entry", ns):
            title = entry.findtext("atom:title", "", ns)
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            updated = entry.findtext("atom:updated", "", ns) or entry.findtext("atom:published", "", ns)
            summary = entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns)
            items.append({
                "title": clean_html(title),
                "url": link,
                "date": parse_rss_date(updated),
                "summary": clean_html(summary or ""),
                "source": feed_config["name"],
                "region": feed_config.get("region", ""),
                "lang": feed_config.get("lang", "en"),
            })

    except ET.ParseError as e:
        logger.warning(f"RSS 解析失败 {url}: {e}")

    logger.info(f"[RSS] {feed_config['name']}: 获取 {len(items)} 条")
    return items


# ─── Google News 搜索 ──────────────────────────────────────────────────

def fetch_google_news(query: str, region_key: str = "en_US") -> List[dict]:
    region = GOOGLE_NEWS_REGIONS.get(region_key, GOOGLE_NEWS_REGIONS["en_US"])
    url = GOOGLE_NEWS_SEARCH_TEMPLATE.format(
        query=quote_plus(query),
        hl=region["hl"],
        gl=region["gl"],
        ceid=region["ceid"],
    )

    resp = safe_get(url)
    if not resp:
        return []

    items = []
    try:
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            description = item.findtext("description", "")

            source_name = "Google News"
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0]
                source_name = parts[1] if len(parts) > 1 else source_name

            items.append({
                "title": clean_html(title),
                "url": link,
                "date": parse_rss_date(pub_date),
                "summary": clean_html(description),
                "source": source_name,
                "region": "",  # 由 classifier 检测
                "lang": region["hl"].split("-")[0],
            })
    except ET.ParseError as e:
        logger.warning(f"Google News RSS 解析失败: {e}")

    logger.info(f"[Google News] '{query}' ({region_key}): 获取 {len(items)} 条")
    return items


# ─── 严格相关性过滤 ──────────────────────────────────────────────────

# 必须包含至少一个「法规/监管行动」信号词
REGULATORY_SIGNALS = [
    # 英文
    r"\bregulat\w*\b", r"\blegislat\w*\b", r"\b(?:new |proposed )?law\b", r"\bbill\b",
    r"\bact\b", r"\bordinance\b", r"\bstatute\b", r"\bdirective\b",
    r"\benforcement\b", r"\bfine[ds]?\b", r"\bpenalt\w+\b", r"\bsanction\w*\b",
    r"\bcompliance\b", r"\bmandat\w+\b", r"\bban(?:s|ned|ning)?\b",
    r"\brestrict\w*\b", r"\brequire\w*\b", r"\bprohibit\w*\b",
    r"\bruling\b", r"\bverdict\b", r"\bconsent order\b",
    r"\bpolicy\b", r"\bguideline\w*\b", r"\brule\w*\b",
    r"\bdraft\b", r"\bconsultation\b", r"\bproposal\b",
    r"\bFTC\b", r"\bCOPPA\b", r"\bGDPR\b", r"\bCCPA\b", r"\bDSA\b", r"\bDMA\b",
    r"\bIGAC\b", r"\bGRAC\b", r"\bESRB\b", r"\bPEGI\b", r"\bCERO\b",
    r"\bOnline Safety Act\b", r"\bKIDS Act\b",
    # 日文
    r"規制", r"法律", r"法案", r"条例", r"施行", r"罰則", r"処分", r"義務",
    r"景品表示法", r"資金決済法", r"特商法",
    # 韩文
    r"규제", r"법안", r"법률", r"의무", r"제재", r"개정",
    r"게임산업진흥법",
]

# 必须包含至少一个「游戏/互动娱乐」信号词
GAME_SIGNALS = [
    r"\bvideo\s*game\w*\b", r"\bmobile\s*game\w*\b", r"\bonline\s*game\w*\b",
    r"\bgaming\b",
    r"\bloot\s*box\w*\b", r"\bgacha\b", r"\bmicrotransaction\w*\b",
    r"\bin.?app\s*purchas\w*\b", r"\bapp\s*store\b", r"\bgoogle\s*play\b",
    r"\bplay\s*store\b", r"\bvirtual\s*currenc\w*\b",
    r"\bminor\w*\b.*\b(?:online|digital|screen)\b",
    r"\bchildren\b.*\b(?:online|digital|app|internet)\b",
    r"\bgame\s*(?:developer|publish|industr|compan|rating|age)\w*\b",
    r"\bgame\b.*\b(?:regulat|law|legislat|ban|restrict|fine|enforc)\b",
    r"\b(?:regulat|law|legislat|ban|restrict|fine|enforc)\w*\b.*\bgame\b",
    r"ゲーム", r"ガチャ",
    r"게임", r"확률형",
]

# 排除词 - 即使匹配了上面的词，如果标题中大量出现这些词，基本可以判断不是法规新闻
EXCLUSION_PATTERNS = [
    r"\breview\b.*\b(?:score|rating|stars?|gameplay)\b",  # 游戏评测
    r"\breleas\w*\b.*\b(?:date|trailer|gameplay)\b",  # 游戏发布
    r"\btrailer\b", r"\bgameplay\b", r"\bwalkthrough\b",
    r"\btournament\b", r"\besports? (?:team|event|match)\b",
    r"\bsale\b.*\b(?:off|discount|deal)\b",
    r"\bbest game\w*\b", r"\btop \d+ game\b",
    r"\bhow to play\b", r"\bgame guide\b",
    r"\bpatch note\b", r"\bupdate.*(?:v\d|version|season|content)\b",
    r"\bGemini\b", r"\bCopilot\b", r"\bChatGPT\b",  # AI 产品新闻
    r"\bSDK\b.*\b(?:release|update|version)\b",  # SDK 更新
    r"\bAPI\b.*\b(?:release|update|version|new)\b",  # API 更新
    r"\bWWDC\d*\b", r"\bGoogle I/O\b",  # 开发者大会（含WWDC25/26等）
    r"@\s*WWDC",                         # @WWDC25 格式
    r"\bdeveloper tool\b", r"\bXcode\b", r"\bSwift\b", r"\bKotlin\b",
    # Apple/Google 开发者博客通用噪音（非立法）
    r"developer activit",                # "developer activities" / "开发者活动"
    r"最新的开发者活动",                   # 中文"查看我们最新的开发者活动"
    r"\bjoin us (?:at|in|for)\b",        # 活动邀请
    r"今天@",                             # "今天@WWDC25：第X天"
    r"\btech talk\b",                    # Apple Tech Talk
    r"storefront.*currenc|currenc.*storefront",   # Apple全球定价页（175 storefronts, 44 currencies）
    r"(?:tax.*price|price.*tax).*(?:\d{2,3}\s*(?:store|market)|storefronts?)",  # Apple价格/税收更新
    r"应用.*价格.*税收|价格.*税收.*更新|税收.*价格.*更新",  # 中文版苹果价格税收更新
    r"应用.*税收.*价格|税收.*更新.*店面",  # 中文版苹果税收价格
    # 博彩/赌场 (casino gambling) 不是游戏行业法规
    r"\bcasino\b", r"\bsports?\s*bet", r"\bpoker\b", r"\bslot\s*machine\b",
    r"\bbookie\b", r"\bhorse\s*rac", r"\b赌场\b",
    r"\bfishing\b.*\b(?:season|rule)\b",  # 钓鱼 (fishing game 误匹配)
    r"\bNBA\b.*\bfine\b", r"\bNFL\b.*\bfine\b",  # 体育罚款
    r"\bprediction\s*market\b",  # 预测市场
    r"\bIAG\b", r"\bInside Asian Gaming\b",  # 博彩行业会议
    r"\btribal\s*gam", r"\btribal\s*bet",  # 部落博彩
    r"\bskill\s*game.*(?:ban|legal|tax)\b",  # "技巧游戏"(实为赌博机)
    r"\bdigital\s*lotter", r"\blottery\s*game\b",  # 数字彩票
    r"\bPAGCOR\b",  # 菲律宾博彩
    r"\bwatchOS\b", r"\b64.?bit\s*require\b",  # 纯技术要求
    r"\bNBA\b", r"\bNFL\b", r"\bNHL\b", r"\bMLB\b",  # 体育联赛
    r"\bCOMESA\b",  # 非洲区域贸易组织(非游戏)
    r"\bCleveland\s*Cavaliers\b",
    r"骑士队",
    r"\blottery\b",  # 彩票
    r"\bbetting\b",  # 投注
]


def is_legislation_relevant(article: dict) -> bool:
    """
    严格过滤：必须同时满足:
    1. 包含法规/监管行动信号词
    2. 包含游戏/互动娱乐信号词
    3. 不匹配排除词模式
    4. 非中国大陆内容
    """
    title = article.get("title", "")
    summary = article.get("summary", "")
    text = f"{title} {summary}"
    text_lower = text.lower()

    # 排除中国大陆
    if is_china_mainland(text):
        return False

    # 检查排除词（在标题和摘要中）
    for p in EXCLUSION_PATTERNS:
        if re.search(p, text_lower, re.IGNORECASE):
            return False

    # 必须有法规信号
    has_regulatory = False
    for p in REGULATORY_SIGNALS:
        if re.search(p, text_lower, re.IGNORECASE):
            has_regulatory = True
            break
    if not has_regulatory:
        return False

    # 必须有游戏信号
    has_game = False
    for p in GAME_SIGNALS:
        if re.search(p, text_lower, re.IGNORECASE):
            has_game = True
            break
    if not has_game:
        return False

    return True


def is_recent(article: dict, max_days: int = MAX_ARTICLE_AGE_DAYS) -> bool:
    try:
        article_date = datetime.strptime(article["date"], "%Y-%m-%d")
        cutoff = datetime.now() - timedelta(days=max_days)
        return article_date >= cutoff
    except (ValueError, KeyError):
        return True


# ─── 精确发布时间抓取 ─────────────────────────────────────────────────

# 已知RSS日期不可信的来源（会把抓取日期当作发布日期）
RECYCLED_DATE_SOURCES = {
    "Android Developers Blog",
}

def try_fetch_article_date(url: str, timeout: int = 8) -> Optional[str]:
    """
    从原始文章页面抓取更精确的发布时间。
    优先级: article:published_time > datePublished JSON-LD > <time> 标签
    返回 YYYY-MM-DD 格式，失败返回 None。
    """
    if not url or not url.startswith("http"):
        return None
    try:
        resp = requests.get(
            url,
            headers={**HEADERS, "Accept": "text/html"},
            timeout=timeout,
            allow_redirects=True,
        )
        if not resp.ok:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Open Graph / article meta 标签
        for prop in [
            "article:published_time", "og:article:published_time",
            "datePublished", "date", "pubdate", "article:modified_time",
        ]:
            tag = soup.find("meta", {"property": prop}) or soup.find("meta", {"name": prop})
            if tag and tag.get("content"):
                d = _parse_iso_date(tag["content"])
                if d:
                    return d

        # 2. JSON-LD
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
                # data 可能是 dict 或 list
                entries = data if isinstance(data, list) else [data]
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    for key in ("datePublished", "dateCreated"):
                        val = entry.get(key, "")
                        d = _parse_iso_date(str(val))
                        if d:
                            return d
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue

        # 3. <time> 标签 - 先检查属性，再检查文本内容
        for time_tag in soup.find_all("time"):
            for attr in ("datetime", "pubdate", "content"):
                val = time_tag.get(attr, "")
                d = _parse_iso_date(str(val))
                if d:
                    return d
            # 检查 <time> 标签的可见文字（如 "February 26, 2026"）
            d = _parse_human_date(time_tag.get_text(" ", strip=True))
            if d:
                return d

        # 4. 在常见的日期容器元素中搜索（class 含 date / time / published / meta 等）
        DATE_CLASSES = re.compile(
            r"\b(?:date|time|published|updated|posted|created|pubdate|timestamp|byline|article-meta)\b",
            re.IGNORECASE,
        )
        for el in soup.find_all(class_=DATE_CLASSES):
            text = el.get_text(" ", strip=True)
            d = _parse_iso_date(text) or _parse_human_date(text)
            if d:
                return d

        # 5. 在 <header> / <article> 头部搜索可见日期文字（最多扫描前 2000 字符正文）
        for container in (soup.find("header"), soup.find("article"), soup.find("main")):
            if container is None:
                continue
            snippet = container.get_text(" ", strip=True)[:2000]
            d = _parse_human_date(snippet)
            if d:
                return d

    except Exception as e:
        logger.debug(f"[日期抓取] {url}: {e}")
    return None


def _parse_iso_date(s: str) -> Optional[str]:
    """从 ISO 8601 字符串提取 YYYY-MM-DD，超出今天则忽略"""
    if not s:
        return None
    s = s.strip()
    # 常见格式: 2026-02-15T10:30:00Z / 2026-02-15 / 20260215
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y%m%d"):
        try:
            dt = datetime.strptime(s[:len(fmt.replace('%Y','0000').replace('%m','00')
                                        .replace('%d','00').replace('%H','00')
                                        .replace('%M','00').replace('%S','00')
                                        .replace('%z',''))], fmt)
            result = dt.strftime("%Y-%m-%d")
            # 合理性校验：2020-01-01 ~ 今天
            if "2020-01-01" <= result <= datetime.now().strftime("%Y-%m-%d"):
                return result
        except ValueError:
            continue
    # 简单提取 YYYY-MM-DD
    m = re.search(r"(202[0-9]-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))", s)
    if m:
        candidate = m.group(1)
        if candidate <= datetime.now().strftime("%Y-%m-%d"):
            return candidate
    return None


# 月份名称映射（英文全称和缩写）
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_human_date(text: str) -> Optional[str]:
    """
    从自然语言文本中提取英文日期，如 'February 26, 2026' 或 '26 Feb 2026'。
    返回 YYYY-MM-DD，失败返回 None。
    """
    if not text:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    tl = text.lower()

    # 格式1: "Month DD, YYYY" 或 "Month DD YYYY"
    m = re.search(
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december'
        r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'
        r'\s+(\d{1,2}),?\s+(20[2-9]\d)\b',
        tl,
    )
    if m:
        month = _MONTH_MAP.get(m.group(1))
        day, year = int(m.group(2)), int(m.group(3))
        if month:
            try:
                result = datetime(year, month, day).strftime("%Y-%m-%d")
                if "2020-01-01" <= result <= today:
                    return result
            except ValueError:
                pass

    # 格式2: "DD Month YYYY" (英国/欧洲格式)
    m = re.search(
        r'\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december'
        r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'
        r'\s+(20[2-9]\d)\b',
        tl,
    )
    if m:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = _MONTH_MAP.get(month_name)
        if month:
            try:
                result = datetime(year, month, day).strftime("%Y-%m-%d")
                if "2020-01-01" <= result <= today:
                    return result
            except ValueError:
                pass

    return None


def enrich_article_dates(articles: List[dict]) -> List[dict]:
    """
    对通过过滤的文章，尝试从原文页面获取更精确的发布时间。
    只对来源日期不可信 OR 日期为今天的文章执行（节省时间）。
    """
    today = datetime.now().strftime("%Y-%m-%d")

    def needs_enrichment(a: dict) -> bool:
        return (
            a.get("source") in RECYCLED_DATE_SOURCES
            or a.get("date", "") >= today  # 日期为今天（疑似动态RSS）
        )

    to_enrich = [a for a in articles if needs_enrichment(a)]
    if not to_enrich:
        return articles

    logger.info(f"[日期校正] 对 {len(to_enrich)} 条文章抓取精确发布时间...")

    url_to_date: dict = {}

    def fetch_date(article: dict):
        url = article.get("url", "")
        result = try_fetch_article_date(url)
        if result:
            url_to_date[url] = result

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_date, a) for a in to_enrich]
        concurrent.futures.wait(futures, timeout=30)

    enriched = 0
    for a in articles:
        url = a.get("url", "")
        if url in url_to_date and url_to_date[url] != a.get("date"):
            logger.debug(f"[日期校正] {a.get('title','')[:40]} {a.get('date')} → {url_to_date[url]}")
            a["date"] = url_to_date[url]
            enriched += 1

    logger.info(f"[日期校正] 完成, 更新 {enriched} 条")
    return articles


# ─── 聚合抓取入口 ─────────────────────────────────────────────────────

def fetch_all_rss() -> List[dict]:
    all_items = []
    rss_sources = [f for f in RSS_FEEDS if f.get("type") == "rss"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        futures = {executor.submit(fetch_rss_feed, feed): feed for feed in rss_sources}
        for future in concurrent.futures.as_completed(futures):
            feed = futures[future]
            try:
                items = future.result()
                all_items.extend(items)
            except Exception as e:
                logger.error(f"抓取失败 {feed['name']}: {e}")

    return all_items


def fetch_google_news_all() -> List[dict]:
    all_items = []
    tasks = []

    # ── 英语圈：美国 + 英国/澳洲/加拿大/新加坡 补充视角 ──────────────
    for kw in KEYWORDS["en"]:
        tasks.append((kw, "en_US"))
    for kw in KEYWORDS["en"][30:50]:  # 经营合规相关关键词补充英国视角
        tasks.append((kw, "en_UK"))
    for kw in KEYWORDS["en"][10:30]:  # 未成年/数据隐私补充澳洲视角
        tasks.append((kw, "en_AU"))
    for kw in KEYWORDS["en"][30:50]:  # 东南亚经营合规补充新加坡视角
        tasks.append((kw, "en_SG"))

    # ── 亚洲本地语言 ───────────────────────────────────────────────
    for kw in KEYWORDS["ja"]:
        tasks.append((kw, "ja_JP"))
    for kw in KEYWORDS["ko"]:
        tasks.append((kw, "ko_KR"))
    for kw in KEYWORDS.get("vi", []):
        tasks.append((kw, "vi_VN"))
    for kw in KEYWORDS.get("id", []):
        tasks.append((kw, "en_ID"))
    for kw in KEYWORDS.get("zh_tw", []):
        tasks.append((kw, "zh_TW"))
    for kw in KEYWORDS.get("th", []):
        tasks.append((kw, "th_TH"))

    # ── 欧洲本地语言 ───────────────────────────────────────────────
    for kw in KEYWORDS.get("de", []):
        tasks.append((kw, "de_DE"))
    for kw in KEYWORDS.get("fr", []):
        tasks.append((kw, "fr_FR"))

    # ── 南美 ───────────────────────────────────────────────────────
    for kw in KEYWORDS.get("pt", []):
        tasks.append((kw, "pt_BR"))
    for kw in KEYWORDS.get("es", []):
        tasks.append((kw, "es_MX"))

    # ── 中东 ───────────────────────────────────────────────────────
    for kw in KEYWORDS.get("ar", []):
        tasks.append((kw, "ar_SA"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        futures = {}
        for query, region in tasks:
            future = executor.submit(fetch_google_news, query, region)
            futures[future] = (query, region)
            time.sleep(0.5)

        for future in concurrent.futures.as_completed(futures):
            query, region = futures[future]
            try:
                items = future.result()
                all_items.extend(items)
            except Exception as e:
                logger.error(f"Google News 搜索失败 '{query}': {e}")

    return all_items


# ─── 语言-地区一致性过滤 ──────────────────────────────────────────────
#
# 各语言文章"合理覆盖"的地区集合。
# 逻辑：北美/欧洲的监管动态原始信源是英文，
# 若韩文/日文等非英语文章被分类到这些地区，通常是外媒转载，
# 英文原始源已被收录，无需重复入库。
# "全球"/"其他" 一律保留（多地区综述）。
#
_LANG_ACCEPTABLE_REGIONS = {
    # key = lang 前缀, value = 该语言"一次信源"应覆盖的合理区域集合
    "ko": {"韩国",                          "全球", "其他"},
    "ja": {"日本",                          "全球", "其他"},
    "vi": {"越南", "东南亚",                "全球", "其他"},
    "id": {"印度尼西亚", "东南亚",          "全球", "其他"},
    "th": {"泰国", "东南亚",               "全球", "其他"},
    "zh": {"台湾", "香港", "澳门", "港澳台","全球", "其他"},
    "de": {"德国", "奥地利", "欧盟", "欧洲","全球", "其他"},
    "fr": {"法国", "比利时", "欧盟", "欧洲","全球", "其他"},
    "nl": {"荷兰", "比利时", "欧盟", "欧洲","全球", "其他"},
    "pt": {"巴西", "南美",                  "全球", "其他"},
    "es": {"墨西哥", "西班牙", "阿根廷", "智利", "哥伦比亚", "南美", "全球", "其他"},
    "ar": {"沙特", "阿联酋", "土耳其", "中东/非洲", "全球", "其他"},
}


def _is_foreign_commentary(lang: str, region: str) -> bool:
    """
    判断是否为"外语文章转载非本地区监管新闻"。

    例：韩文(ko)文章被分类为北美 → 视为韩媒转载美国新闻，过滤。
    例：韩文文章分类为韩国 → 本地一次信源，保留。
    英文(en)文章全球通用，始终保留。
    """
    if not lang or lang == "en":
        return False
    lang_prefix = lang.split("-")[0].lower()
    acceptable = _LANG_ACCEPTABLE_REGIONS.get(lang_prefix)
    if acceptable is None:
        return False   # 未配置的语言：保守策略，不过滤
    return region not in acceptable


def fetch_and_process(max_days: int = MAX_ARTICLE_AGE_DAYS) -> List[LegislationItem]:
    """
    完整抓取 & 处理流水线:
    1. 抓取 RSS + Google News
    2. 严格过滤 (法规 + 游戏 + 排除中国大陆 + 排除噪音)
    3. 分类为 LegislationItem
    4. 语言-地区一致性过滤（外语转载非本地新闻）
    5. 翻译标题和摘要
    """
    logger.info("=" * 60)
    logger.info("开始抓取数据...")

    # 1. 抓取
    rss_items = fetch_all_rss()
    logger.info(f"RSS 抓取完成: {len(rss_items)} 条原始数据")

    news_items = fetch_google_news_all()
    logger.info(f"Google News 抓取完成: {len(news_items)} 条原始数据")

    all_raw = rss_items + news_items
    logger.info(f"合计原始数据: {len(all_raw)} 条")

    # 2. 去重 (按 title 归一化)
    seen_titles = set()
    unique_items = []
    for item in all_raw:
        title_key = re.sub(r"\s+", " ", item["title"].strip().lower())
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_items.append(item)
    logger.info(f"去重后: {len(unique_items)} 条")

    # 3. 严格过滤: 法规+游戏+排除中国大陆+排除噪音+时间范围
    relevant = [a for a in unique_items if is_legislation_relevant(a) and is_recent(a, max_days)]
    logger.info(f"严格过滤后: {len(relevant)} 条立法相关文章")

    # 4. 日期精准化（对来源日期不可信的文章抓取真实发布时间）
    relevant = enrich_article_dates(relevant)

    # 5. 分类 + 语言-地区一致性过滤
    legislation_items = []
    lang_filtered = 0
    for article in relevant:
        classified = classify_article(article)
        lang = article.get("lang", "en")
        if _is_foreign_commentary(lang, classified.region):
            logger.debug(
                f"[语言过滤] [{lang}] 文章报道非本地区 [{classified.region}]，跳过: "
                f"{article.get('title', '')[:60]}"
            )
            lang_filtered += 1
            continue
        legislation_items.append(classified)

    if lang_filtered:
        logger.info(f"[语言过滤] 过滤外语转载 {lang_filtered} 条（非本地区监管新闻）")
    logger.info(f"分类完成: {len(legislation_items)} 条立法动态")
    return legislation_items
