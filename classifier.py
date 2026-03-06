"""
文章分类器 - 自动分配区域、一级分类、二级分类、状态
分类对齐 config.py: 数据隐私/玩法合规/未成年人保护/广告营销合规/消费者保护/经营合规/平台政策/内容监管
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
    "欧盟": [r"european union|\bEU\b|GDPR|DSA\b|DMA\b|digital services act|digital markets act|european commission|european parliament|brussels|AI act|欧盟"],
    "英国": [r"united kingdom|\bUK\b|british|ofcom|online safety act|UK GDPR|英国|britain"],
    "德国": [r"germany|german|德国|deutschland|BfDI"],
    "法国": [r"france|french|法国|CNIL"],
    "荷兰": [r"netherlands|dutch|荷兰|kansspelautoriteit"],
    "奥地利": [r"austria|austrian|奥地利"],
    "比利时": [r"belgium|belgian|比利时"],
    "意大利": [r"italy|italian|意大利|AGCM"],
    "西班牙": [r"spain|spanish|西班牙|AEPD"],
    "波兰": [r"poland|polish|波兰"],
    "瑞典": [r"sweden|swedish|瑞典"],
    "挪威": [r"norway|norwegian|挪威"],
    # 北美
    "美国": [r"united states|\bUS\b|\bUSA\b|american|FTC\b|federal trade commission|CCPA|CPRA|COPPA|congress\b|senate\b|california|KIDS act|section 230|tennessee|florida|alabama|missouri|new york|south carolina|mississippi|connecticut|nevada|pennsylvania|harrisburg|attorney general"],
    "加拿大": [r"canada|canadian|加拿大|PIPEDA"],
    # 南美
    "巴西": [r"brazil|brazilian|巴西|LGPD"],
    "墨西哥": [r"mexico|mexican|墨西哥"],
    "阿根廷": [r"argentina|阿根廷"],
    "智利": [r"chile|chilean|智利"],
    "哥伦比亚": [r"colombia|colombian|哥伦比亚"],
    # 东南亚
    "越南": [r"vietnam|vietnamese|越南|việt nam|MIC.*vietnam|nghị định|thông tư"],
    "印度尼西亚": [r"indonesia|indonesian|印尼|印度尼西亚|IGAC|Kominfo|Kemenkominfo"],
    "泰国": [r"thailand|thai\b|泰国|PDPA.*thailand|thai.*PDPA"],
    "菲律宾": [r"philippines|filipino|菲律宾|NTC.*philippine"],
    "马来西亚": [r"malaysia|malaysian|马来西亚|MCMC"],
    "新加坡": [r"singapore|新加坡|IMDA|MDA.*singapore"],
    # 南亚
    "印度": [r"\bindia\b|indian|印度|DPDPA|Vaishnaw|MeitY"],
    "巴基斯坦": [r"pakistan|巴基斯坦"],
    # 港澳台
    "香港": [r"hong kong|香港|PCPD"],
    "澳门": [r"macau|macao|澳门"],
    "台湾": [r"taiwan|台湾|台灣|個資法"],
    # 日本
    "日本": [r"japan|japanese|日本|CERO|ガチャ|景品表示法|資金決済法|特商法|消費者庁|スマートフォン"],
    # 韩国
    "韩国": [r"korea|korean|韩国|한국|GRAC|게임|게임산업진흥|확률형|문화체육관광부"],
    # 大洋洲
    "澳大利亚": [r"australia|australian|澳大利亚|澳洲|ACCC|eSafety"],
    "新西兰": [r"new zealand|新西兰"],
    # 中东/非洲
    "沙特": [r"saudi|沙特|GAMERS"],
    "阿联酋": [r"UAE|united arab emirates|阿联酋|dubai"],
    "土耳其": [r"turkey|turkish|türkiye|土耳其"],
    "尼日利亚": [r"nigeria|尼日利亚"],
    "南非": [r"south africa|南非"],
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
    r"中华人民共和国|版号|网信办|新闻出版署|PIPL|防沉迷|游戏出海",
]


# ─── 分类检测规则 ─────────────────────────────────────────────────────

CATEGORY_PATTERNS = {
    # ── 数据隐私 ──────────────────────────────────────────────────────
    "数据隐私": {
        "_l1": [
            r"privacy|data.?protection|GDPR|CCPA|CPRA|LGPD|DPDPA|隐私|データ保護|개인정보",
            r"data.?breach|data.?transfer|cookie|consent.*data|个人数据|個人資料|跨境数据|data.?local",
        ],
        "GDPR合规": [r"GDPR|general data protection"],
        "CCPA/各州隐私法": [r"CCPA|CPRA|california.*privacy|state privacy law"],
        "儿童隐私(COPPA)": [r"COPPA|children.*privacy|kids.*privacy|儿童隐私|child.*data.*protect"],
        "跨境数据传输": [r"cross.?border.*data|data.*transfer|跨境数据|数据出境|standard.*contractual"],
        "数据本地化": [r"data.*local\w*|server.*local\w*|数据本地化"],
        "数据泄露通知": [r"data.*breach|breach.*notif|数据泄露"],
    },

    # ── 玩法合规（开箱/抽卡/涉赌） ──────────────────────────────────────
    "玩法合规": {
        "_l1": [
            r"loot.?box|gacha|random.*(?:item|reward|drop)|probability.*disclos",
            r"gambling.*game|game.*gambling|gaming.*gambling",
            r"확률형|ガチャ|开箱|抽奖|抽卡|涉赌|随机道具",
            r"pay.?to.?win|microtransaction|virtual.*currenc|game.*monetiz",
        ],
        "抽奖/开箱(Loot Box)": [r"loot.?box|gacha|random.*item|random.*reward|开箱|抽奖|抽卡|ガチャ|확률형"],
        "概率公示": [r"probability.*disclos|odds.*disclos|drop.*rate|概率公示|確率表示"],
        "虚拟货币": [r"virtual.*currenc|in.?game.*currenc|虚拟货币|仮想通貨|가상화폐"],
        "付费随机机制": [r"pay.*random|paid.*random|random.*purchas|random.*paid|무작위.*구매"],
        "涉赌认定": [r"gambling.*game|game.*gambling|gaming.*mechanic.*gambling|类赌博|涉赌|賭博.*ゲーム"],
        "游戏内购规范": [r"in.?app.*purchas|IAP|microtransaction|内购|인앱결제"],
    },

    # ── 未成年人保护 ──────────────────────────────────────────────────
    "未成年人保护": {
        "_l1": [
            r"minor|children|child(?:ren)?|\bkid\b|youth|teen|underage|未成年|青少年|儿童|未成年者|청소년|未成年人",
            r"age.*verif|age.*restrict|anti.?addiction|年龄|COPPA|KIDS.*act",
            r"children.*online.*safety|parental.*control|family.*link",
        ],
        "年龄验证/分级": [r"age.*verif|age.*check|age.*gate|年龄验证|年齢確認|연령 확인"],
        "未成年消费限制": [r"minor.*spend|minor.*purchas|children.*spend|kids.*spend|未成年.*消费|課金制限|미성년.*결제"],
        "游戏时长限制": [r"play.*time.*limit|screen.*time|curfew|游戏时长|게임 이용시간|playtime.*restrict"],
        "内容分级制度": [r"age.*rat|content.*rat|ESRB|PEGI|CERO|GRAC|IGAC|分级|レーティング|등급"],
        "家长控制": [r"parental.*control|family.*link|parent.*setting|家长控制|保護者"],
        "防沉迷系统": [r"anti.?addiction|防沉迷|addiction.*prevent|game.*addict"],
    },

    # ── 广告营销合规 ──────────────────────────────────────────────────
    "广告营销合规": {
        "_l1": [
            r"advertis.*regulat|advertis.*law|marketing.*(?:law|regulat|comply|rule)",
            r"dark.?pattern|misleading.*ad|deceptive.*ad|false.*advertis",
            r"influencer.*disclos|sponsorship.*disclos|KOL.*comply|网红.*合规",
            r"广告.*合规|广告.*规定|广告.*法|营销.*合规",
        ],
        "虚假广告": [r"misleading.*ad|false.*advertis|deceptive.*ad|虚假广告|誤認表示|허위광고"],
        "营销披露": [r"advertis.*disclos|marketing.*disclos|sponsor.*disclos|营销披露|広告表示"],
        "网红/KOL合规": [r"influencer.*(?:law|rule|disclos|comply)|KOL.*comply|streamer.*disclos|网红|YouTuber.*rule"],
        "价格透明度": [r"price.*transparen|pricing.*disclos|price.*disclos|价格透明|価格表示"],
        "暗黑模式": [r"dark.?pattern|manipulat.*design|deceptive.*design|暗黑模式|다크패턴"],
        "促销活动合规": [r"promotion.*law|promotion.*rule|sale.*law|促销.*合规|景品表示"],
    },

    # ── 消费者保护 ──────────────────────────────────────────────────
    "消费者保护": {
        "_l1": [
            r"consumer.*protect|consumer.*right|消费者保护|消費者保護|소비자 보호",
            r"refund.*game|chargeback.*game|game.*refund",
            r"subscription.*auto.?renew|auto.?renew.*subscript",
            r"FTC.*consumer|consumer.*fine|consumer.*law",
        ],
        "退款政策": [r"refund|chargeback|退款|返金|환불"],
        "订阅自动续费": [r"auto.?renew|subscription.*renew|自动续费|自動更新|자동갱신"],
        "价格歧视": [r"price.*discrimin|dynamic.*pricing.*unfair|价格歧视|価格差別"],
        "消费者权益诉讼": [r"consumer.*lawsuit|consumer.*litigation|class.*action.*consumer|消费者诉讼|집단소송"],
        "虚假宣传": [r"mislead.*consumer|deceptive.*consumer|false.*claim.*consumer|虚假宣传|不当表示"],
    },

    # ── 经营合规（本地代理/代表处/许可/分级） ──────────────────────────
    "经营合规": {
        "_l1": [
            r"local.*agent|local.*represent|local.*publisher|local.*entity",
            r"game.*licens|game.*permit|game.*registr|游戏许可|게임 등록|IGAC.*registr",
            r"foreign.*(?:game|developer|publisher).*(?:require|registr|agent|licens)",
            r"本地代理|本地代表|本地发行|经营合规|대리인.*게임|게임.*대리인",
            r"market.*access.*game|game.*market.*entry|game.*operation.*permit",
        ],
        "本地代理/代表处": [r"local.*agent|local.*represent|대리인|게임.*대리인|local.*entity.*game|本地代理"],
        "游戏许可/牌照": [r"game.*licens|game.*permit|游戏许可|游戏牌照|게임 사업자|사업자 등록"],
        "本地分级注册": [r"local.*rating|rating.*registr|local.*classif|本地分级|IGAC|GRAC.*registr|등급 신청"],
        "税务合规": [r"(?:digital|game).*tax|数字税|税务合规|GST.*game|VAT.*game|游戏税"],
        "外资限制": [r"foreign.*(?:invest|own|company).*restrict|外资限制|FDI.*game"],
        "本地发行商要求": [r"local.*publisher.*require|local.*distributor|overseas.*publisher.*local|海外.*本地发行"],
    },

    # ── 平台政策 ──────────────────────────────────────────────────────
    "平台政策": {
        "_l1": [
            r"app.*store.*(?:polic|rule|guideline|regulat)|apple.*(?:polic|guideline).*(?:game|app)",
            r"google.*play.*(?:polic|regulat|rule)|android.*polic.*(?:game|app)",
            r"side.?load|third.?party.*pay|第三方支付|平台政策|DMA.*app.*store",
        ],
        "App Store政策": [r"app.*store.*(?:polic|guideline|regulat|rule)|apple.*(?:polic|guideline).*(?:game|app|developer)"],
        "Google Play政策": [r"google.*play.*(?:polic|regulat|rule)|android.*polic.*(?:game|app)"],
        "第三方支付": [r"third.?party.*pay|alternative.*pay|第三方支付|alternative.*payment"],
        "佣金/分成比例": [r"commission.*(?:app|store)|revenue.*shar|佣金|分成|30%.*store"],
        "侧载政策": [r"side.?load|alternative.*(?:market|store)|侧载|sideload"],
    },

    # ── 内容监管 ──────────────────────────────────────────────────────
    "内容监管": {
        "_l1": [
            r"content.*regulat|content.*moder|censor|内容监管|内容审查",
            r"game.*rating.*system|classification.*regulat|分级制度",
            r"AI.*(?:act|regulat|law)|copyright.*(?:law|act)|AIGC",
        ],
        "内容审查": [r"content.*(?:review|censor|moder).*(?:law|regulat|rule)|内容审查"],
        "AI生成内容": [r"AI.*(?:generat|act|regulat|law)|AIGC|generative.*AI.*(?:law|regulat)"],
        "知识产权保护": [r"intellectual.*property.*(?:law|regulat)|copyright.*(?:law|act)|知识产权|著作権"],
        "版权合规": [r"copyright.*infring|pirac.*(?:law|enforce)|版权合规|著作権侵害"],
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


# ─── 影响评分体系 ─────────────────────────────────────────────────────
#
# 参考"分布式检索 + 影响评估模型"专业框架:
#   信源层级 × 状态标签 → 影响评分 (1=低 / 2=中 / 3=高)
#
# 高(3): 已生效/即将生效/修订 的法规；官方来源的执法/草案动态
# 中(2): 草案/立法/执法 动态；官方来源的立法动态
# 低(1): 一般立法动态、行业讨论
#

_IMPACT_STATUS_BASE = {
    "已生效":       3,
    "即将生效":     3,
    "修订变更":      3,
    "执法动态":     2,
    "草案/征求意见": 2,
    "立法进行中":   2,
    "已提案":       2,
    "已废止":       1,
    "立法动态":     1,
}


def get_source_tier(source_name: str) -> str:
    """
    返回信源权威层级: 'official' / 'legal' / 'industry' / 'news'
    优先精确匹配 SOURCE_TIER_MAP，其次用 SOURCE_TIER_PATTERNS 正则匹配。
    """
    if source_name in SOURCE_TIER_MAP:
        return SOURCE_TIER_MAP[source_name]
    for tier, pattern in SOURCE_TIER_PATTERNS:
        if re.search(pattern, source_name, re.IGNORECASE):
            return tier
    return "news"


def score_impact(status: str, source_name: str) -> int:
    """
    计算影响评分 (1–3):
      - 基础分来自状态标签
      - 官方信源 (official) 额外 +1（上限3），体现一手信息的权威性
      - 法律情报源 (legal) 额外 +0.5 → 取 ceil（反映专业解读价值）
    """
    base = _IMPACT_STATUS_BASE.get(status, 1)
    tier = get_source_tier(source_name)

    if tier == "official":
        base = min(3, base + 1)
    elif tier == "legal" and base < 3:
        base = min(3, base + 1)   # legal tier 同样升一级，但不超过3

    return base


# ─── 分类入口 ────────────────────────────────────────────────────────

def classify_article(article: dict) -> LegislationItem:
    """对一篇文章进行区域、分类、状态、影响评分判定"""
    text = f"{article.get('title', '')} {article.get('summary', '')}".strip()

    region = _detect_region(text, article.get("region", ""))
    l1, l2 = _detect_category(text)
    status = _detect_status(text)
    source_name = article.get("source", "")
    impact = score_impact(status, source_name)

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
    """检测文章所属区域（返回大区名称如 '欧洲', '北美'）"""
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
