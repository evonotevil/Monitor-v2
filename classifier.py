"""
文章分类器 - 自动分配区域、一级分类、二级分类、状态
分类对齐 config.py: 数据隐私 / AI合规 / 未成年人保护 / 平台与竞争合规 /
                    广告营销合规 / 消费者保护 / 知识产权 / 内容监管 / 经营合规
"""

import re
from typing import Tuple

from config import (
    CATEGORIES, MONITORED_REGIONS, STATUS_LABELS,
    SOURCE_TIER_MAP, SOURCE_TIER_PATTERNS,
)
from models import LegislationItem


# ─── 国家 → 区域 映射 ──────────────────────────────────────────────

COUNTRY_PATTERNS = {
    # 欧洲
    "欧盟": [r"european union|\bEU\b|GDPR|DSA\b|DMA\b|digital services act|digital markets act|european commission|european parliament|brussels|AI act|欧盟|EDPB"],
    "英国": [r"united kingdom|\bUK\b|british|ofcom|online safety act|UK GDPR|英国|britain|\bICO\b|CMA\b"],
    "德国": [r"germany|german|德国|deutschland|BfDI|Bundeskartellamt"],
    "法国": [r"france|french|法国|CNIL|Autorité de la concurrence"],
    "荷兰": [r"netherlands|dutch|荷兰|ACM\b"],
    "奥地利": [r"austria|austrian|奥地利|noyb"],
    "比利时": [r"belgium|belgian|比利时"],
    "意大利": [r"italy|italian|意大利|AGCM|Garante"],
    "西班牙": [r"spain|spanish|西班牙|AEPD"],
    "波兰": [r"poland|polish|波兰"],
    "瑞典": [r"sweden|swedish|瑞典"],
    "挪威": [r"norway|norwegian|挪威"],
    # 北美
    "美国": [r"united states|\bUS\b|\bUSA\b|american|FTC\b|federal trade commission|CCPA|CPRA|COPPA|KOSA|congress\b|senate\b|california|section 230|tennessee|florida|new york|attorney general|DOJ\b|department of justice"],
    "加拿大": [r"canada|canadian|加拿大|PIPEDA|OPC\b"],
    # 南美
    "巴西": [r"brazil|brazilian|巴西|LGPD|ANPD\b"],
    "墨西哥": [r"mexico|mexican|墨西哥|INAI\b"],
    "阿根廷": [r"argentina|阿根廷"],
    "智利": [r"chile|chilean|智利"],
    "哥伦比亚": [r"colombia|colombian|哥伦比亚"],
    # 东南亚
    "越南": [r"vietnam|vietnamese|越南|việt nam|MIC.*vietnam|nghị định|thông tư|PDPL.*vietnam"],
    "印度尼西亚": [r"indonesia|indonesian|印尼|印度尼西亚|Kominfo|Kemenkominfo"],
    "泰国": [r"thailand|thai\b|泰国|PDPA.*thailand|thai.*PDPA"],
    "菲律宾": [r"philippines|filipino|菲律宾|NPC.*philippine"],
    "马来西亚": [r"malaysia|malaysian|马来西亚|MCMC|PDPA.*malaysia"],
    "新加坡": [r"singapore|新加坡|IMDA|PDPA.*singapore"],
    # 南亚
    "印度": [r"\bindia\b|indian|印度|DPDPA|MeitY"],
    "巴基斯坦": [r"pakistan|巴基斯坦"],
    # 港澳台
    "香港": [r"hong kong|香港|PCPD"],
    "澳门": [r"macau|macao|澳门"],
    "台湾": [r"taiwan|台湾|台灣|個資法"],
    # 日本
    "日本": [r"japan|japanese|日本|PPC\b|景品表示法|資金決済法|特商法|消費者庁|個人情報保護"],
    # 韩国
    "韩国": [r"korea|korean|韩国|한국|KFTC|공정거래|개인정보|문화체육관광부"],
    # 大洋洲
    "澳大利亚": [r"australia|australian|澳大利亚|澳洲|ACCC|eSafety|OAIC\b"],
    "新西兰": [r"new zealand|新西兰|OPC.*zealand"],
    # 中东/非洲
    "沙特": [r"saudi|沙特|CITC\b"],
    "阿联酋": [r"UAE|united arab emirates|阿联酋|dubai|TRA\b"],
    "土耳其": [r"turkey|turkish|türkiye|土耳其|KVKK\b"],
    "尼日利亚": [r"nigeria|尼日利亚|NITDA\b"],
    "南非": [r"south africa|南非|POPIA\b"],
}

# 国家 → 区域 映射表
COUNTRY_TO_REGION = {}
for region_name, region_info in MONITORED_REGIONS.items():
    for country in region_info["countries"]:
        COUNTRY_TO_REGION[country] = region_name

# 中国大陆关键词（用于排除）
CHINA_MAINLAND_PATTERNS = [
    r"(?<!\bhong\s)(?<!\bmacau\s)(?<!\btaiwan\s)china(?!.*hong kong)(?!.*macau)(?!.*taiwan)",
    r"中国(?!.*香港)(?!.*澳门)(?!.*台湾)",
    r"中华人民共和国|版号|网信办|新闻出版署|PIPL|防沉迷",
]


# ─── 分类检测规则 ─────────────────────────────────────────────────────

CATEGORY_PATTERNS = {
    # ── 数据隐私 ──────────────────────────────────────────────────────
    "数据隐私": {
        "_l1": [
            r"privacy|data.?protection|GDPR|CCPA|CPRA|LGPD|DPDPA|隐私|データ保護|개인정보",
            r"data.?breach|data.?transfer|cookie|consent.*data|个人数据|個人資料|跨境数据|data.?local",
            r"biometric|facial.?recognit|fingerprint.*data|生物识别|人脸识别",
        ],
        "GDPR/欧盟数据保护": [r"GDPR|general data protection|EDPB|欧盟.*数据"],
        "CCPA/美国各州隐私法": [r"CCPA|CPRA|california.*privacy|state privacy law|indiana.*privacy|virginia.*privacy"],
        "儿童隐私(COPPA)": [r"COPPA|children.*privacy|kids.*privacy|儿童隐私|child.*data.*protect"],
        "跨境数据传输": [r"cross.?border.*data|data.*transfer|跨境数据|数据出境|standard.*contractual|adequacy.*decision|数据充分性"],
        "数据本地化": [r"data.*local\w*|server.*local\w*|数据本地化"],
        "生物识别数据": [r"biometric|facial.?recognit|fingerprint.*data|voice.*recognit|生物识别|人脸识别|声纹"],
        "数据泄露通知": [r"data.*breach|breach.*notif|数据泄露"],
    },

    # ── AI 合规 ───────────────────────────────────────────────────────
    "AI合规": {
        "_l1": [
            r"\bAI\b.*(?:act|regulat|law|rule|liabil|govern)|artificial.*intelligence.*(?:law|regulat|rule)",
            r"generative.*AI|gen.*AI|large.*language.*model|\bLLM\b|\bGPT\b|foundation.*model",
            r"AI.*(?:train|copyright|liabil|agent|scraping)|machine.*learning.*(?:law|copyright|regulat)",
            r"deepfake.*(?:law|regulat|ban)|AIGC.*法|生成式.*AI.*规|人工智能.*法",
        ],
        "AI法规立法": [r"AI.*act|AI.*regulat.*law|artificial.*intelligence.*act|EU.*AI.*act|AI.*governance.*law|人工智能.*法"],
        "AI训练数据版权": [r"AI.*train.*copyright|train.*data.*copyright|copyright.*AI.*train|LLM.*copyright|Books\d.*lawsuit|AI.*scraping.*copyright"],
        "AI代理与自动化": [r"AI.*agent|agentic.*AI|autonomous.*AI|automated.*(?:decision|action|shopping)|AI.*bot.*(?:law|regulat)"],
        "生成式AI治理": [r"generative.*AI.*(?:law|regulat|rule|govern)|AIGC|deepfake.*(?:law|ban|regulat)|gen.*AI.*govern"],
        "AI责任与风险": [r"AI.*liabilit|AI.*risk.*(?:law|regulat)|AI.*harm|algorithmic.*accountab|AI.*bias.*law"],
    },

    # ── 未成年人保护 ──────────────────────────────────────────────────
    "未成年人保护": {
        "_l1": [
            r"minor|children|child(?:ren)?|\bkid\b|youth|teen|underage|未成年|青少年|儿童|未成年者|청소년",
            r"age.*verif|age.*restrict|年龄|COPPA|KOSA|kids.*online.*safety",
            r"children.*online.*safety|parental.*control|social.*media.*ban.*(?:minor|under)",
            r"under.*16|under.*13|16.*social.*media|social.*media.*age",
        ],
        "年龄验证": [r"age.*verif|age.*check|age.*gate|年龄验证|年齢確認|연령 확인|age.*estimat"],
        "社交媒体年龄限制": [r"social.*media.*(?:ban|age|minor|under|16|13)|under.*16.*(?:ban|social)|age.*social.*media|social.*media.*youth"],
        "未成年消费限制": [r"minor.*spend|minor.*purchas|children.*spend|kids.*spend|未成年.*消费|미성년.*결제"],
        "儿童数字安全": [r"children.*(?:digital|online).*safety|KOSA|kids.*online.*safety|child.*digital.*safety|儿童数字安全"],
        "家长控制": [r"parental.*control|family.*link|parent.*setting|家长控制|保護者"],
    },

    # ── 平台与竞争合规 ────────────────────────────────────────────────
    "平台与竞争合规": {
        "_l1": [
            r"digital.*services.*act|DSA\b|digital.*markets.*act|DMA\b",
            r"app.*store.*(?:antitrst|compet|regulat|law)|apple.*app.*store.*(?:antitrst|compet|fine)",
            r"platform.*(?:compet|antitrst|regulat|transparen)|online.*platform.*(?:law|rule|obligat)",
            r"gatekeeper|third.?party.*pay|平台政策|平台竞争|数字市场法|数字服务法",
        ],
        "DSA/数字服务法": [r"digital.*services.*act|\bDSA\b.*(?:enforce|compli|fine|violat)|数字服务法"],
        "DMA/数字市场法": [r"digital.*markets.*act|\bDMA\b.*(?:enforce|compli|gate|obligat)|数字市场法"],
        "App Store反垄断": [r"app.*store.*(?:antitrst|compet|fine|law)|apple.*(?:antitrst|compet).*(?:store|pay)|google.*play.*(?:antitrst|compet)|苹果税|佣金.*平台|平台.*反垄断"],
        "平台透明度义务": [r"platform.*transparen|transparency.*obligat|algorithmic.*transparen|platform.*audit|研究人员.*数据.*访问"],
        "第三方支付开放": [r"third.?party.*pay|alternative.*pay|alternative.*(?:store|market)|side.?load|第三方支付|外链支付"],
    },

    # ── 广告营销合规 ──────────────────────────────────────────────────
    "广告营销合规": {
        "_l1": [
            r"advertis.*(?:regulat|law|enforce|fine)|marketing.*(?:law|regulat|comply|rule)",
            r"dark.?pattern|misleading.*ad|deceptive.*ad|false.*advertis",
            r"influencer.*disclos|sponsorship.*disclos|KOL.*comply|网红.*合规",
            r"广告.*合规|广告.*规定|广告.*法|营销.*合规",
        ],
        "虚假/误导广告": [r"misleading.*ad|false.*advertis|deceptive.*ad|虚假广告|허위광고|誤認表示"],
        "暗黑模式": [r"dark.?pattern|manipulat.*design|deceptive.*design|暗黑模式|다크패턴|deceptive.*interface"],
        "网红/KOL合规": [r"influencer.*(?:law|rule|disclos|comply)|KOL.*comply|streamer.*disclos|creator.*disclos|网红|YouTuber.*rule"],
        "定向广告合规": [r"targeted.*ad.*(?:law|ban|regulat)|behavioral.*ad.*(?:law|restrict)|personali.*ad.*(?:law|ban)|定向广告|行为广告"],
        "价格透明度": [r"price.*transparen|pricing.*disclos|价格透明|価格表示|hidden.*fee.*law"],
    },

    # ── 消费者保护 ──────────────────────────────────────────────────
    "消费者保护": {
        "_l1": [
            r"consumer.*protect|consumer.*right|消费者保护|消費者保護|소비자 보호",
            r"refund.*(?:law|rule|right)|subscription.*auto.?renew|auto.?renew.*subscript",
            r"FTC.*consumer|consumer.*fine|consumer.*law",
            r"loot.?box.*consumer|gacha.*consumer|random.*purchas.*consumer|microtransaction.*law",
        ],
        "退款政策": [r"refund|chargeback|退款|返金|환불"],
        "订阅自动续费": [r"auto.?renew|subscription.*renew|自动续费|自動更新|자동갱신|subscription.*trap"],
        "随机付费机制": [r"loot.?box|gacha|random.*(?:item|reward)|probability.*disclos|확률형|ガチャ|开箱|抽奖|抽卡|涉赌|microtransaction.*regulat"],
        "消费者权益诉讼": [r"consumer.*lawsuit|consumer.*litigation|class.*action.*consumer|消费者诉讼|집단소송"],
        "虚假宣传": [r"mislead.*consumer|deceptive.*consumer|false.*claim.*consumer|虚假宣传|不当表示"],
    },

    # ── 知识产权 ──────────────────────────────────────────────────────
    "知识产权": {
        "_l1": [
            r"copyright.*(?:infring|law|act|lawsuit|enforce)|intellectual.*property.*(?:law|regulat)",
            r"AI.*(?:copyright|train.*data|scraping).*(?:law|lawsuit|regulat)|copyright.*AI",
            r"pirac.*(?:law|enforce|suit)|DMCA|版权|著作権|저작권",
            r"web.*scrap.*(?:copyright|law|suit)|content.*scrap.*(?:law|suit)",
        ],
        "AI训练数据版权": [r"AI.*train.*copyright|copyright.*AI.*train|LLM.*copyright|Books\d|training.*data.*copyright|著作権.*AI.*学習"],
        "平台版权责任": [r"platform.*copyright.*liabilit|safe.*harbor.*copyright|DMCA.*platform|platform.*copyright.*law"],
        "内容抓取与爬虫": [r"web.*scrap.*(?:copyright|law|suit|legal)|content.*scrap.*(?:law|suit)|crawl.*copyright|scraping.*(?:lawsuit|legal)"],
        "版权执法": [r"copyright.*infring.*(?:suit|fine|enforce)|pirac.*(?:enforce|suit|fine)|版权执法|著作権侵害"],
    },

    # ── 内容监管 ──────────────────────────────────────────────────────
    "内容监管": {
        "_l1": [
            r"content.*(?:regulat|moder|law|removal)|illegal.*content.*(?:law|regulat|removal)",
            r"hate.*speech.*(?:law|regulat|fine)|misinformation.*(?:law|regulat)",
            r"content.*classif|content.*rating.*(?:law|regulat)|内容监管|内容审查",
            r"AI.*generat.*content.*(?:law|regulat)|AIGC.*法",
        ],
        "违法内容治理": [r"illegal.*content.*(?:law|removal|obligat)|harmful.*content.*(?:law|regulat)|content.*removal.*obligat"],
        "仇恨言论": [r"hate.*speech.*(?:law|fine|regulat)|hate.*content.*(?:law|ban)|仇恨言论"],
        "AI生成内容": [r"AI.*generat.*content.*(?:law|regulat|label)|deepfake.*(?:label|disclos|ban)|AIGC|synthetic.*media.*law"],
        "内容分级": [r"content.*rating.*(?:law|regulat|system)|age.*rating.*(?:law|platform)|分级.*法|内容分级"],
    },

    # ── 经营合规 ──────────────────────────────────────────────────────
    "经营合规": {
        "_l1": [
            r"local.*(?:agent|represent|entity|publisher).*(?:digital|platform|service)",
            r"digital.*(?:service|platform).*(?:licens|permit|registr)",
            r"foreign.*(?:digital|platform|tech).*(?:require|registr|agent|licens)",
            r"本地代理|本地代表|经营合规|数字服务.*许可|digital.*service.*tax",
        ],
        "本地代理/代表处": [r"local.*(?:agent|represent|entity).*(?:digital|platform|service)|본지 대리인.*플랫폼|本地代理.*平台"],
        "数字服务许可": [r"digital.*service.*(?:licens|permit|registr)|online.*platform.*(?:licens|permit)|数字服务.*许可"],
        "税务合规": [r"digital.*(?:service.*tax|tax)|DST\b|数字税|税务合规|VAT.*digital|GST.*digital|digital.*goods.*tax"],
        "外资限制": [r"foreign.*(?:invest|own|company).*restrict.*(?:digital|tech|platform)|外资限制.*平台|FDI.*digital"],
    },
}


# ─── 状态检测规则 ─────────────────────────────────────────────────────

STATUS_PATTERNS = {
    "已生效": [r"\b(?:now )?effective\b|in force|enacted|enforced|takes? effect|已生效|已实施|施行|발효"],
    "即将生效": [r"coming into|will take effect|即将生效|goes into effect|set to take effect|将于.*生效|将要.*施行"],
    "草案/征求意见": [r"draft|consultation|comment period|草案|征求意见|意见稿|パブリックコメント|public comment|입법예고"],
    "立法进行中": [r"under review|reading|deliberat|审议中|进行中|under consideration|审议|审查"],
    "已提案": [r"\bpropos\w*\b|\bintroduc\w*\b|bill filed|已提案|提出|提交|new bill|发议案|법안 발의"],
    "修订变更": [r"\bamend\w*\b|已修订|修改|修正|개정|revision"],
    "已废止": [r"repeal|abolish|已废止|废除|폐지"],
    "执法动态": [r"enforcement|(?:fined?|penalty|penalised|penalized)\b|sanction|处罚|罚款|执法|violation|settle|consent order|enforcement.?action|벌금|제재"],
    "立法动态": [r"announce|plan to|consider|signal|intend|upcoming|将|拟|검토|예정"],
}


# ─── 影响评分体系（0-10分制）─────────────────────────────────────────

# 法律效力权重（基于状态）
_LEGAL_WEIGHT = {
    "已生效":        10,
    "执法动态":       9,
    "即将生效":       7,
    "修订变更":       6,
    "立法进行中":     6,
    "草案/征求意见":  5,
    "已提案":         4,
    "立法动态":       3,
    "政策信号":       3,
    "已废止":         2,
}

# 地区战略重要性权重
_HIGH_IMPORTANCE_REGIONS = {
    "全球", "欧盟", "美国", "英国", "德国", "法国", "北美", "欧洲",
}
_MID_IMPORTANCE_REGIONS = {
    "日本", "韩国", "澳大利亚", "新西兰", "印度", "巴西",
    "加拿大", "大洋洲", "南美",
}


def get_source_tier(source_name: str) -> str:
    """返回信源权威层级: 'official' / 'legal' / 'industry' / 'news'"""
    if source_name in SOURCE_TIER_MAP:
        return SOURCE_TIER_MAP[source_name]
    for tier, pattern in SOURCE_TIER_PATTERNS:
        if re.search(pattern, source_name, re.IGNORECASE):
            return tier
    return "news"


def score_impact(status: str, source_name: str,
                 region: str = "", text: str = "") -> int:
    """
    计算影响评分 (1–10)。
    = round((法律效力权重 + 地区重要性权重) / 2) + 官方信源加成
    """
    legal_w = _LEGAL_WEIGHT.get(status, 3)

    # 执法动态 + 罚款/制裁关键词 → 升至最高法律效力
    if text and re.search(
        r'\bfine[ds]?\b|\bsanction\w*\b|\bpenalt\w+\b|\benforcement\b'
        r'|罚款|处罚|制裁',
        text, re.IGNORECASE,
    ):
        legal_w = max(legal_w, 9)

    # 地区权重
    if region in _HIGH_IMPORTANCE_REGIONS:
        region_w = 10
    elif region in _MID_IMPORTANCE_REGIONS:
        region_w = 7
    else:
        region_w = 6  # 东南亚 / 中东 / 台港澳等

    # 官方信源 +1
    tier = get_source_tier(source_name)
    tier_bonus = 1 if tier == "official" else 0

    score = round((legal_w + region_w) / 2) + tier_bonus
    return min(10, max(1, score))


# ─── 分类入口 ────────────────────────────────────────────────────────

def classify_article(article: dict) -> LegislationItem:
    """对一篇文章进行区域、分类、状态、影响评分判定"""
    text = f"{article.get('title', '')} {article.get('summary', '')}".strip()

    region = _detect_region(text, article.get("region", ""))
    l1, l2 = _detect_category(text)
    status = _detect_status(text)
    source_name = article.get("source", "")
    impact = score_impact(status, source_name, region=region, text=text)

    return LegislationItem(
        region=region,
        category_l1=l1,
        category_l2=l2,
        title=article.get("title", ""),
        date=article.get("date", ""),
        status=status,
        summary=article.get("summary", "")[:500],
        source_name=source_name,
        source_url=article.get("url", ""),
        lang=article.get("lang", "en"),
        impact_score=impact,
    )


def _detect_region(text: str, fallback: str = "") -> str:
    """检测文章所属区域"""
    text_combined = text.lower()

    country_scores = {}
    for country, patterns in COUNTRY_PATTERNS.items():
        score = 0
        for p in patterns:
            score += len(re.findall(p, text_combined, re.IGNORECASE))
        if score > 0:
            country_scores[country] = score

    if country_scores:
        best_country = max(country_scores, key=country_scores.get)
        region = COUNTRY_TO_REGION.get(best_country)
        if region:
            return region

    if re.search(r"\beu\b|欧盟|european|europe", text_combined, re.IGNORECASE):
        return "欧洲"

    if fallback and fallback in MONITORED_REGIONS:
        return fallback
    return "其他"


def is_china_mainland(text: str) -> bool:
    """检测是否为中国大陆相关内容"""
    for p in CHINA_MAINLAND_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def _detect_category(text: str) -> Tuple[str, str]:
    """检测一级/二级分类"""
    text_lower = text.lower()
    best_l1 = "内容监管"
    best_l1_score = 0
    best_l2 = ""

    for l1, sub_patterns in CATEGORY_PATTERNS.items():
        l1_score = 0
        l1_patterns = sub_patterns.get("_l1", [])
        for p in l1_patterns:
            l1_score += len(re.findall(p, text_lower, re.IGNORECASE))

        if l1_score > best_l1_score:
            best_l1_score = l1_score
            best_l1 = l1

            best_l2_score = 0
            best_l2 = ""
            for l2_name, l2_patterns in sub_patterns.items():
                if l2_name == "_l1":
                    continue
                l2_score = 0
                for p in l2_patterns:
                    l2_score += len(re.findall(p, text_lower, re.IGNORECASE))
                if l2_score > best_l2_score:
                    best_l2_score = l2_score
                    best_l2 = l2_name

    return best_l1, best_l2


def _detect_status(text: str) -> str:
    """检测状态"""
    text_lower = text.lower()
    best_status = "立法动态"
    best_score = 0

    for status, patterns in STATUS_PATTERNS.items():
        score = 0
        for p in patterns:
            score += len(re.findall(p, text_lower, re.IGNORECASE))
        if score > best_score:
            best_score = score
            best_status = status

    return best_status
