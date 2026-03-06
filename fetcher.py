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


def _clean_title(title: str, source: str = "") -> str:
    """
    标题净化：去掉乱码、重复媒体名称、噪音前后缀，保持标题简洁。

    处理以下情况：
      ① " - MediaName" 后缀（Google News 汇聚格式，已在 fetch_google_news 中处理，
         此函数作为兜底）
      ② "[MediaName] " 前缀
      ③ "MediaName: " 前缀（RSS 常见）
      ④ 乱码字符（非 ASCII 非中日韩的单字节噪音）
      ⑤ 多余的空白
    """
    if not title:
        return title

    t = title.strip()

    # ① 去掉 " - MediaName" 结尾（保留标题核心）
    # 仅当后缀是已知媒体名称模式才处理（防止误删"EU - US Privacy Deal"这类标题）
    if source and " - " in t:
        parts = t.rsplit(" - ", 1)
        # 如果后缀就是信源名称（模糊匹配，容忍大小写差异）
        suffix = parts[-1].strip()
        if source and (
            suffix.lower() == source.lower()
            or source.lower() in suffix.lower()
            or len(suffix) < 40  # 短后缀通常是媒体名
        ):
            # 只有当前缀（实际标题）足够长才截断
            if len(parts[0].strip()) >= 10:
                t = parts[0].strip()

    # ② 去掉 "[MediaName] " 前缀
    t = re.sub(r'^\[[^\]]{1,40}\]\s*', '', t)

    # ③ 去掉 "MediaName: " 前缀（须确保剩余部分仍足够长）
    m = re.match(r'^([A-Za-z][A-Za-z0-9 &]{1,30}):\s+(.{10,})', t)
    if m:
        prefix_candidate = m.group(1)
        # 只有当前缀看起来是媒体名（首字母大写，无动词形式）才去掉
        if re.match(r'^[A-Z][a-zA-Z0-9 &]+$', prefix_candidate):
            t = m.group(2)

    # ④ 压缩多余空白
    t = re.sub(r'\s{2,}', ' ', t).strip()

    return t or title   # 净化失败时保留原标题


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

        _src = feed_config["name"]
        for item in root.findall(".//item"):
            title = clean_html(item.findtext("title", ""))
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            description = item.findtext("description", "")
            items.append({
                "title": _clean_title(title, _src),
                "url": link,
                "date": parse_rss_date(pub_date),
                "summary": clean_html(description),
                "source": _src,
                "region": feed_config.get("region", ""),
                "lang": feed_config.get("lang", "en"),
            })

        for entry in root.findall(".//atom:entry", ns):
            title = clean_html(entry.findtext("atom:title", "", ns))
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            updated = entry.findtext("atom:updated", "", ns) or entry.findtext("atom:published", "", ns)
            summary = entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns)
            items.append({
                "title": _clean_title(title, _src),
                "url": link,
                "date": parse_rss_date(updated),
                "summary": clean_html(summary or ""),
                "source": _src,
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

            cleaned_title = _clean_title(clean_html(title), source_name)
            items.append({
                "title": cleaned_title,
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
    r"\bICO\b", r"\bEDPB\b", r"\bOfcom\b", r"\bCMA\b",
    r"\bOnline Safety Act\b", r"\bKIDS Act\b", r"\bKOSA\b",
    # 日文
    r"規制", r"法律", r"法案", r"条例", r"施行", r"罰則", r"処分", r"義務",
    r"景品表示法", r"資金決済法", r"特商法",
    # 韩文
    r"규제", r"법안", r"법률", r"의무", r"제재", r"개정",
]

# 必须包含至少一个「互联网内容平台」相关信号词
# 聚焦：内容安全、未成年保护、隐私、版权、支付合规、商业化
PLATFORM_SIGNALS = [
    # ── 平台类型 ──────────────────────────────────────────────────────
    r"\bonline\s*platform\w*\b", r"\bdigital\s*platform\w*\b",
    r"\bsocial\s*(?:media|network|platform)\b",
    r"\bstreaming\b",
    r"\bvideo\s*(?:platform|sharing|streaming|hosting)\b",
    r"\blive\s*stream\w*\b", r"\bshort.?video\b",
    r"\bUGC\b",
    r"\bcontent\s*creator\w*\b",
    r"\bapp\s*store\b", r"\bgoogle\s*play\b",
    # ── 知名内容平台（监管场景）────────────────────────────────────────
    r"\bTikTok\b", r"\bByteDance\b",
    r"\bYouTube\b", r"\bFacebook\b", r"\bInstagram\b", r"\bMeta\b",
    r"\bTwitter\b", r"\bNetflix\b", r"\bSpotify\b",
    r"\bSnapchat\b", r"\bReddit\b", r"\bDiscord\b", r"\bTwitch\b",
    r"\bLinkedIn\b", r"\bPinterest\b",
    # ── 支付与变现合规 ────────────────────────────────────────────────
    r"\bin.?app\s*purchas\w*\b",
    r"\bvirtual\s*currenc\w*\b",
    r"\bdigital\s*goods?\b",
    r"\bloot\s*box\w*\b", r"\bgacha\b", r"\bmicrotransaction\w*\b",
    r"\bsubscription.*(?:auto.?renew|cancel|trap|law|regulat)\b",
    r"\bdigital\s*payment\b",
    # ── 未成年人保护 ──────────────────────────────────────────────────
    r"\bminor\w*\b.{0,60}\b(?:online|digital|platform|internet|social|screen|content|app)\b",
    r"\bchildren\b.{0,60}\b(?:online|digital|platform|internet|social|app|content|safety)\b",
    r"\byouth\b.{0,40}\b(?:online|digital|platform|social|screen)\b",
    r"\bage\s*verif\w*\b",
    r"\bCOPPA\b", r"\bKOSA\b",
    r"\bparental\s*control\b",
    r"未成年", r"青少年.{0,20}(?:网络|平台|保护|上网)",
    # ── 隐私与数据合规 ────────────────────────────────────────────────
    r"\bGDPR\b", r"\bCCPA\b", r"\bCPRA\b", r"\bPDPA\b", r"\bLGPD\b", r"\bDPDPA\b",
    r"\bdata\s*protection\b",
    r"\bpersonal\s*data\b",
    r"\bcross.?border.*data\b",
    r"\bdata.*localiz\w*\b",
    r"\bprivacy.*(?:platform|online|digital|enforce|fine|law)\b",
    # ── 内容安全与版权 ────────────────────────────────────────────────
    r"\bdeepfake\b", r"\bAIGC\b",
    r"\bcontent\s*(?:moderat\w*|removal|takedown|illegal)\b",
    r"\bAI.?generat\w*.*content\b",
    r"\bstreaming.*copyright\b|\bcopyright.*stream\w*\b",
    r"\bplatform.*copyright\b|\bcopyright.*platform\b",
    r"\bhate\s*speech\b",
    r"\billegal\s*content\b",
    r"内容监管|内容安全|版权.{0,10}平台|平台.{0,10}版权",
    # ── 平台竞争与治理 ────────────────────────────────────────────────
    r"\bDSA\b", r"\bDMA\b",
    r"\bdigital\s*services\s*act\b", r"\bdigital\s*markets\s*act\b",
    r"\bgatekeeper\b",
    r"\bthird.?party\s*pay\b",
    # ── 广告营销合规 ──────────────────────────────────────────────────
    r"\bdark.?pattern\b",
    r"\binfluencer.*(?:disclos|law|rule)\b",
    r"\btargeted.*ad\b",
    r"\bKOL\b",
    # ── 亚洲语言平台信号 ─────────────────────────────────────────────
    r"平台|流媒体|直播|短视频|数据保护|隐私|内容监管",
    r"プラットフォーム|ストリーミング|配信|プライバシー|著作権",
    r"플랫폼|스트리밍|개인정보|저작권|미성년",
]

# 排除词 - 即使匹配了上面的词，如果标题中出现这些词，基本可以判断不是合规新闻
EXCLUSION_PATTERNS = [
    r"\btrailer\b", r"\bgameplay\b", r"\bwalkthrough\b",       # 游戏/影视宣传内容
    r"\besports?\s*(?:team|event|match|tournament)\b",          # 电竞赛事
    r"\bpatch\s*note\b",                                        # 游戏补丁说明
    r"\bgame\s*guide\b", r"\bhow\s*to\s*play\b",               # 游戏攻略
    r"\bGemini\b", r"\bCopilot\b", r"\bChatGPT\b",             # AI 产品发布（无监管语境）
    r"\bSDK\b.*\b(?:release|update|version)\b",                 # SDK 更新
    r"\bAPI\b.*\b(?:release|update|version|new)\b",             # API 更新
    r"\bWWDC\d*\b", r"\bGoogle\s*I/O\b",                       # 开发者大会
    r"@\s*WWDC",
    r"\bdeveloper\s*activit",
    r"最新的开发者活动",
    r"\bjoin\s*us\s*(?:at|in|for)\b",
    r"今天@",
    r"\btech\s*talk\b",
    r"storefront.*currenc|currenc.*storefront",                  # Apple 全球定价页
    r"(?:tax.*price|price.*tax).*(?:\d{2,3}\s*(?:store|market)|storefronts?)",
    r"应用.*价格.*税收|价格.*税收.*更新|税收.*价格.*更新",
    r"应用.*税收.*价格|税收.*更新.*店面",
    # 博彩/赌博
    r"\bcasino\b", r"\bsports?\s*bet\b", r"\bpoker\b", r"\bslot\s*machine\b",
    r"\bbookie\b", r"\bhorse\s*rac\b", r"\b赌场\b",
    r"\bprediction\s*market\b",
    r"\bIAG\b", r"\bInside\s*Asian\s*Gaming\b",
    r"\btribal\s*gam\w*", r"\btribal\s*bet\w*",
    r"\bskill\s*game.*(?:ban|legal|tax)\b",
    r"\bdigital\s*lotter\w*", r"\blottery\s*game\b",
    r"\bPAGCOR\b",
    r"\blottery\b", r"\bbetting\b",
    # 体育联赛
    r"\bNBA\b", r"\bNFL\b", r"\bNHL\b", r"\bMLB\b",
    r"\bCleveland\s*Cavaliers\b", r"骑士队",
    # 其他纯技术/商业噪音
    r"\bwatchOS\b", r"\b64.?bit\s*require\b",
    r"\bCOMESA\b",
    r"\bfishing\b.*\b(?:season|rule)\b",
]


def is_legislation_relevant(article: dict) -> bool:
    """
    严格过滤：必须同时满足:
    1. 包含法规/监管行动信号词
    2. 包含互联网内容平台相关信号词（内容安全/未成年保护/隐私/版权/支付/商业化）
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

    # 必须有互联网内容平台信号
    has_platform = False
    for p in PLATFORM_SIGNALS:
        if re.search(p, text_lower, re.IGNORECASE):
            has_platform = True
            break
    if not has_platform:
        return False

    return True


# ─── 影响力预评分（漏斗第二层）────────────────────────────────────────

# 标题高风险词 — 命中即直接说明是执法/生效/禁令等高优先动态
_IMPACT_TITLE_RE = re.compile(
    r"\b(?:fine[ds]?|sanction\w*|penalt\w+|effective\b|in\s+force\b|"
    r"penaliz\w*|ban(?:ned|ning|s)?|enforcement\b|lawsuit|settlement|"
    r"prohibit\w*|court\s+order|consent\s+order|blocking\b|enjoin\w*)\b",
    re.IGNORECASE,
)

# 法案阶段权重：取第一个匹配的最高分
_STAGE_RULES = [
    (re.compile(r"\b(?:now\s+)?effective\b|in\s+force|takes?\s+effect", re.IGNORECASE), 0.20),
    (re.compile(r"\benforcement\b|fine[ds]?\b|penalt\w+|sanction|处罚|罚款|制裁", re.IGNORECASE), 0.15),
    (re.compile(r"\bact\b|\blaw\b|enacted|立法|法案|通过", re.IGNORECASE), 0.10),
    (re.compile(r"\bdraft\b|\bconsultation\b|\bproposal\b|草案|征求意见", re.IGNORECASE), 0.05),
]


def _pre_score_article(article: dict) -> float:
    """
    影响力预评分 (0.0–1.0)。在严格语义过滤后、分类前运行。

    组成：
      标题高风险词命中   0.0–0.30  (每命中 1 个 +0.10，上限 0.30)
      法案阶段关键词     0.0–0.20  (取第一个匹配的最高权重)
      官方/法律信源加成  0.15 / 0.10 / 0.05 / 0.00

    注：官方信源来自 FTC、ICO 等；阈值低于 _MIN_PRE_SCORE 的条目直接丢弃。
    """
    title = article.get("title", "")
    text  = f"{title} {article.get('summary', '')}"

    # 1. 标题高风险词：fine / ban / sanction / effective…
    keyword_bonus = min(len(_IMPACT_TITLE_RE.findall(title)) * 0.10, 0.30)

    # 2. 法案阶段：effective > enforcement > act/law > draft
    stage_bonus = 0.0
    for pattern, weight in _STAGE_RULES:
        if pattern.search(text):
            stage_bonus = weight
            break

    # 3. 信源权威层级（官方 RSS 得分最高）
    from classifier import get_source_tier
    tier = get_source_tier(article.get("source", ""))
    source_bonus = {"official": 0.15, "legal": 0.10, "industry": 0.05}.get(tier, 0.0)

    return min(1.0, keyword_bonus + stage_bonus + source_bonus)


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

    # ── 英语圈：美国（全量）+ 英国/澳洲/新加坡（专项关键词）──────────
    for kw in KEYWORDS["en"]:
        tasks.append((kw, "en_US"))
    for kw in KEYWORDS.get("en_uk", []):  # 英国专项：OSA/ICO/CMA 等
        tasks.append((kw, "en_UK"))
    for kw in KEYWORDS.get("en_au", []):  # 澳洲专项：eSafety/Privacy Act 等
        tasks.append((kw, "en_AU"))
    for kw in KEYWORDS.get("en_sg", []):  # 新加坡/东南亚英文专项
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

    # 3. 严格过滤: 法规+平台信号+排除中国大陆+排除噪音+时间范围
    relevant = [a for a in unique_items if is_legislation_relevant(a) and is_recent(a, max_days)]
    logger.info(f"严格过滤后: {len(relevant)} 条互联网平台合规相关文章")

    # 3b. 影响力预评分漏斗：丢弃无任何高优先信号的低质量条目
    _MIN_PRE_SCORE = 0.10
    pre_scored = [(a, _pre_score_article(a)) for a in relevant]
    before_count = len(relevant)
    relevant = []
    for a, s in pre_scored:
        if s >= _MIN_PRE_SCORE:
            a["_pre_score"] = round(s, 2)
            relevant.append(a)
    if len(relevant) < before_count:
        logger.info(
            f"影响力预评分过滤: {before_count} → {len(relevant)} 条"
            f"（丢弃 {before_count - len(relevant)} 条低质量噪音，阈值 {_MIN_PRE_SCORE}）"
        )

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
