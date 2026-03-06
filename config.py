"""
全球游戏行业立法动态监控工具 - 配置文件
面向中资手游出海合规视角 (以原神发行模式为参考)
重点覆盖: 数据隐私、玩法合规(开箱/抽卡)、广告营销合规、涉赌合规、
         未成年保护、消费者保护、经营合规(本地代理/代表处/分级)
"""

# ─── 重点监控区域（不含中国大陆）──────────────────────────────────────
#
# ⚠️  注意：MONITORED_REGIONS 和 REGION_DISPLAY_ORDER 是「纯文档字段」，
#    不被任何功能代码读取，仅供人工参考。
#    实际抓取覆盖范围由下方 KEYWORDS 字典决定（Google News 搜索词）。
#    如需新增某个国家/地区的抓取，请在 KEYWORDS 里添加对应搜索词，
#    而非修改 MONITORED_REGIONS。
#    区域显示分组的配置在 utils.py（_REGION_GROUP_MAP / _GROUP_ORDER）。
#
MONITORED_REGIONS = {
    "欧洲": {
        "countries": ["欧盟", "英国", "德国", "法国", "荷兰", "比利时", "奥地利", "意大利", "西班牙", "波兰", "瑞典", "挪威"],
        "focus": ["GDPR", "DSA", "DMA", "AI法案", "Loot Box", "Online Safety Act", "消费者保护"],
    },
    "北美": {
        "countries": ["美国", "加拿大"],
        "focus": ["FTC执法", "COPPA", "CCPA", "KIDS Act", "Loot Box", "各州隐私法", "未成年保护"],
    },
    "南美": {
        "countries": ["巴西", "阿根廷", "墨西哥", "智利", "哥伦比亚"],
        "focus": ["LGPD", "消费者保护", "游戏税务", "内容分级", "广告合规"],
    },
    "东南亚": {
        "countries": ["越南", "印度尼西亚", "泰国", "菲律宾", "马来西亚", "新加坡"],
        "focus": ["本地代理制度", "IGAC评级", "游戏许可", "PDPA", "本地代表处", "本地注册", "发行商资质"],
    },
    "南亚": {
        "countries": ["印度", "巴基斯坦", "孟加拉国"],
        "focus": ["DPDPA", "游戏禁令", "在线游戏监管", "GST税务", "数字税"],
    },
    "港澳台": {
        "countries": ["香港", "澳门", "台湾"],
        "focus": ["个资法", "游戏分级", "消费者保护", "未成年保护"],
    },
    "日本": {
        "countries": ["日本"],
        "focus": ["景品表示法", "资金決済法", "CERO分级", "特商法", "ガチャ規制", "未成年保护"],
    },
    "韩国": {
        "countries": ["韩国"],
        "focus": ["游戏产业振兴法", "确率型道具", "GRAC分级", "代理人制度", "青少年保护法", "海外游戏本地代理"],
    },
    "大洋洲": {
        "countries": ["澳大利亚", "新西兰"],
        "focus": ["Online Safety Act", "Privacy Act", "Age Verification", "Loot Box", "未成年保护"],
    },
    "中东/非洲": {
        "countries": ["沙特", "阿联酋", "土耳其", "尼日利亚", "南非"],
        "focus": ["内容监管", "游戏许可", "数据保护", "本地化要求"],
    },
}

REGION_DISPLAY_ORDER = [
    "欧洲", "北美", "南美", "东南亚", "南亚", "港澳台", "日本", "韩国", "大洋洲", "中东/非洲",
]

# ─── 一级分类 / 二级分类 (围绕手游出海合规) ─────────────────────────────

CATEGORIES = {
    "数据隐私": [
        "GDPR合规",
        "CCPA/各州隐私法",
        "儿童隐私(COPPA)",
        "跨境数据传输",
        "数据本地化",
        "数据泄露通知",
    ],
    "玩法合规": [
        "抽奖/开箱(Loot Box)",
        "概率公示",
        "虚拟货币",
        "付费随机机制",
        "涉赌认定",
        "游戏内购规范",
    ],
    "未成年人保护": [
        "年龄验证/分级",
        "未成年消费限制",
        "游戏时长限制",
        "内容分级制度",
        "家长控制",
        "防沉迷系统",
    ],
    "广告营销合规": [
        "虚假广告",
        "营销披露",
        "网红/KOL合规",
        "价格透明度",
        "暗黑模式",
        "促销活动合规",
    ],
    "消费者保护": [
        "退款政策",
        "订阅自动续费",
        "价格歧视",
        "消费者权益诉讼",
        "虚假宣传",
    ],
    "经营合规": [
        "本地代理/代表处",
        "游戏许可/牌照",
        "本地分级注册",
        "税务合规",
        "外资限制",
        "本地发行商要求",
    ],
    "平台政策": [
        "App Store政策",
        "Google Play政策",
        "第三方支付",
        "佣金/分成",
        "侧载政策",
    ],
    "内容监管": [
        "内容审查",
        "AI生成内容",
        "知识产权保护",
        "版权合规",
    ],
}

# ─── 状态标签 ───────────────────────────────────────────────────────

STATUS_LABELS = [
    "已生效",
    "即将生效",
    "草案/征求意见",
    "立法进行中",
    "已提案",
    "修订变更",
    "已废止",
    "执法动态",
    "立法动态",
]

# ─── 搜索关键词库 (聚焦手游出海合规 - 以原神发行方式为参考) ──────────────────

KEYWORDS = {
    "en": [
        # === 玩法合规 / 涉赌 - Loot Box / Gacha ===
        "loot box regulation 2025",
        "loot box regulation 2026",
        "loot box ban law",
        "gacha regulation law",
        "game loot box gambling law",
        "randomized purchase game regulation",
        "probability disclosure mobile game law",
        "pay to win regulation",
        "mobile game gacha gambling classification",
        "virtual goods gambling law game",
        "game mechanic gambling determination",
        "gacha pay-to-win ban",

        # === 未成年人保护 ===
        "children online safety act game",
        "COPPA game enforcement 2025",
        "COPPA game enforcement 2026",
        "FTC children game fine",
        "game age verification law",
        "minor gaming restriction law",
        "game age rating regulation",
        "children game spending limit law",
        "kids game addiction law",
        "minor game purchase restriction",
        "parental control mobile game law",
        "teen online gaming curfew",

        # === 数据隐私 ===
        "GDPR game enforcement",
        "GDPR mobile game fine",
        "CCPA game privacy law",
        "game data privacy law 2026",
        "children data protection game app",
        "game app privacy regulation",
        "cross-border data transfer game",
        "data localization mobile game",
        "game player data protection fine",

        # === 广告营销合规 ===
        "game advertising regulation law",
        "misleading game advertising enforcement",
        "dark pattern game ban regulation",
        "influencer game advertising disclosure law",
        "game marketing compliance regulation",
        "deceptive game advertising fine",
        "mobile game promotion regulation",
        "game streamer sponsorship disclosure",

        # === 消费者保护 ===
        "in-app purchase regulation consumer",
        "game microtransaction consumer protection law",
        "game refund regulation law",
        "subscription auto-renewal game law",
        "game consumer protection enforcement",
        "virtual currency consumer protection",
        "game overcharge consumer fine",
        "mobile game subscription regulation",

        # === 经营合规 - 本地代理 / 代表处 / 许可 (东南亚重点) ===
        "Korea game local agent representative law",
        "Korea game industry promotion act amendment",
        "Korea foreign game publisher local agent",
        "Vietnam game license local agent requirement",
        "Vietnam game operation permit publisher",
        "Vietnam Ministry of Information game regulation",
        "Vietnam Decree game mobile publisher",
        "Indonesia game rating IGAC requirement",
        "Indonesia game publisher local registration",
        "Indonesia game operator local entity",
        "Indonesia Ministry game regulation Kominfo",
        "Thailand game regulation PDPA publisher",
        "Philippines game regulation publisher NTC",
        "Malaysia game regulation MCMC publisher",
        "Malaysia Communications game content classification",
        "Singapore game rating IMDA requirement",
        "India online gaming regulation GST",
        "India online gaming intermediary rules",
        "game publisher local representative requirement overseas",
        "foreign mobile game developer local entity requirement",
        "game operation license overseas developer",
        "mobile game local publisher license Southeast Asia",
        "game app store local representative requirement",

        # === 欧洲特定 ===
        "UK online safety act game age verification",
        "EU digital services act game platform",
        "DSA game compliance 2025",
        "DSA game compliance 2026",
        "DMA app store game regulation",
        "EU AI act game",
        "EU loot box regulation",
        "Netherlands Belgium loot box ban game",

        # === 澳大利亚 / 大洋洲 ===
        "Australia game loot box age verification",
        "Australia online safety act game",
        "Australia Privacy Act game",

        # === 平台政策 ===
        "app store regulation game DMA antitrust",
        "google play policy game change",
        "apple app store game policy",
        "third party payment game regulation",
        "app store commission game fee regulation",
    ],
    "ja": [
        "ゲーム規制 法律 2025",
        "ゲーム規制 法律 2026",
        "ガチャ規制 法案 改正",
        "未成年者 ゲーム 規制",
        "景品表示法 ガチャ 処分",
        "資金決済法 ゲーム 改正",
        "特商法 ゲーム アプリ",
        "スマートフォンゲーム 課金 規制",
        "消費者庁 ゲーム 処分 罰則",
        "子ども ゲーム 利用 規制",
        "ゲーム 個人情報 保護 規制",
    ],
    "ko": [
        "게임 규제 법안 2025",
        "게임 규제 법안 2026",
        "확률형 아이템 규제 법안",
        "게임산업진흥법 개정",
        "미성년자 게임 규제 법률",
        "게임 대리인 제도 해외",
        "해외 게임사 국내 대리인",
        "게임 소비자 보호 법안",
        "게임 등급 분류 의무",
        "청소년 게임 이용 제한 법률",
        "게임 광고 규제 법안",
    ],
    "vi": [
        "quy định trò chơi điện tử 2025",
        "quy định trò chơi điện tử 2026",
        "luật game mobile đại lý nước ngoài",
        "nghị định trò chơi điện tử",
        "Bộ Thông tin Truyền thông game",
    ],
    "id": [
        "regulasi game mobile Indonesia 2025",
        "regulasi game mobile Indonesia 2026",
        "penerbit game lokal Indonesia",
        "IGAC rating game mobile",
        "Kominfo regulasi game",
        "Kemenkominfo penerbit game asing",
    ],
    "de": [
        # 德语 - 德国/奥地利
        "Spieleregulierung Gesetz 2026",
        "Lootboxen Regulierung Deutschland",
        "Jugendschutz Videospiele Gesetz",
        "Datenschutz Mobile Games DSGVO",
        "Glücksspiel Videospiele Regulierung",
        "Onlinespiele Minderjährige Gesetz",
        "Spielsucht Gesetz Jugendschutz",
    ],
    "fr": [
        # 法语 - 法国/比利时
        "réglementation loot box jeu vidéo",
        "protection mineurs jeux vidéo loi",
        "RGPD jeux mobiles France",
        "jeu vidéo régulation loi 2026",
        "microtransactions jeux vidéo loi",
        "jeux mobiles mineurs protection loi",
        "dark pattern jeux vidéo France",
    ],
    "pt": [
        # 葡萄牙语 - 巴西
        "regulação jogos mobile Brasil 2026",
        "LGPD jogos eletrônicos aplicativo",
        "lei loot box jogo online",
        "proteção menores jogos mobile Brasil",
        "regulamentação jogos SENACON Brasil",
        "jogos mobile privacidade crianças lei",
        "microtransação jogo regulação Brasil",
    ],
    "es": [
        # 西班牙语 - 墨西哥/西班牙/拉美
        "regulación loot box videojuegos ley",
        "ley protección menores videojuegos España",
        "regulación videojuegos consumidor México",
        "privacidad datos videojuegos menores",
        "regulación juegos móviles 2026",
        "microtransacciones videojuegos ley",
        "juegos online regulación España",
    ],
    "zh_tw": [
        # 繁体中文 - 台湾/港澳
        "遊戲法規 台灣 2026",
        "遊戲內購 消費者保護 法規",
        "未成年 遊戲 保護法 台灣",
        "個資法 遊戲 App 台灣",
        "遊戲分級 法規 台灣",
        "手機遊戲 廣告 規範",
    ],
    "th": [
        # 泰语
        "กฎหมายเกมมือถือ ไทย 2026",
        "PDPA เกมออนไลน์ ไทย",
        "ระเบียบเกมมือถือ ผู้เยาว์",
        "คุ้มครองผู้บริโภค เกมออนไลน์ กฎหมาย",
    ],
    "ar": [
        # 阿拉伯语 - 沙特/阿联酋
        "تنظيم ألعاب الجوال السعودية 2026",
        "قانون ألعاب الفيديو الإمارات",
        "حماية الأطفال ألعاب إلكترونية",
        "صناديق الغنائم لعبة قانون",
        "خصوصية البيانات ألعاب الجوال",
    ],
}

# ─── RSS / 数据源 ────────────────────────────────────────────────────
#
# tier 字段标记信源权威层级（对应三层信源金字塔）:
#   "official" — 政府机构 / 监管机构官方公报（最高可信度）
#   "legal"    — 律所 / 法律情报机构（专业法律解读）
#   "industry" — 行业媒体 / 贸易协会（市场视角）
#
RSS_FEEDS = [
    # ── 行业媒体 (Industry tier) ──────────────────────────────────────
    {
        "name": "GamesIndustry.biz",
        "url": "https://www.gamesindustry.biz/feed",
        "lang": "en",
        "type": "rss",
        "region": "全球",
        "tier": "industry",
    },
    {
        "name": "Android Developers Blog",
        "url": "https://feeds.feedburner.com/blogspot/hsDu",
        "lang": "en",
        "type": "rss",
        "region": "全球",
        "tier": "industry",
    },

    # ── 官方公报 (Official tier) ──────────────────────────────────────
    {
        "name": "FTC News",
        "url": "https://www.ftc.gov/feeds/press-release-consumer-protection.xml",
        "lang": "en",
        "type": "rss",
        "region": "北美",
        "tier": "official",
    },
    {
        # 美国联邦公报 — FTC 分类，覆盖 FTC 提交的正式法规文件
        "name": "Federal Register (FTC)",
        "url": "https://www.federalregister.gov/articles/search.rss?conditions[agencies][]=federal-trade-commission",
        "lang": "en",
        "type": "rss",
        "region": "北美",
        "tier": "official",
    },
    {
        # 英国政府官方 Atom — Ofcom 发布的游戏/在线安全动态 (ICO RSS 已失效改用此源)
        "name": "UK Gov (Ofcom/Gaming)",
        "url": "https://www.gov.uk/search/news-and-communications.atom?keywords=gaming+online+safety&organisations%5B%5D=ofcom",
        "lang": "en",
        "type": "rss",   # fetcher 用 atom:entry 解析，兼容 Atom 格式
        "region": "欧洲",
        "tier": "official",
    },
    {
        # 英国政府官方 Atom — 儿童在线安全 (age verification / children act)
        "name": "UK Gov (Children Online Safety)",
        "url": "https://www.gov.uk/search/news-and-communications.atom?keywords=children+online+safety+age+verification",
        "lang": "en",
        "type": "rss",
        "region": "欧洲",
        "tier": "official",
    },

    # ── 法律情报 (Legal tier) ─────────────────────────────────────────
    {
        "name": "GDPR.eu News",
        "url": "https://gdpr.eu/feed/",
        "lang": "en",
        "type": "rss",
        "region": "欧洲",
        "tier": "legal",
    },

    # ── 更多官方来源 (Official tier) ──────────────────────────────────
    # EU Digital Strategy RSS (digital-strategy.ec.europa.eu) — malformed XML，已移除
    # Australian eSafety Commissioner RSS — timeout，已移除
    # Canada Competition Bureau RSS — timeout，已移除
    # 新加坡 IMDA — 官方 RSS 已下线，由 Google News en_SG 关键词搜索替代

    # ── 更多行业媒体 (Industry tier) ──────────────────────────────────
    {
        "name": "Pocket Gamer",
        "url": "https://www.pocketgamer.biz/rss/",
        "lang": "en",
        "type": "rss",
        "region": "全球",
        "tier": "industry",
    },
    {
        # GamesBeat 已并入 VentureBeat，/category/games/feed/ 已失效
        "name": "GamesBeat",
        "url": "https://venturebeat.com/feed/",
        "lang": "en",
        "type": "rss",
        "region": "全球",
        "tier": "industry",
    },
    # IAPP RSS (iapp.org/rss/daily-dashboard) — 返回 0 条，已移除
]

# ─── Google News 搜索 ────────────────────────────────────────────────

GOOGLE_NEWS_SEARCH_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"

GOOGLE_NEWS_REGIONS = {
    # ── 英语圈 ──────────────────────────────────────────────────────
    "en_US": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "en_UK": {"hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
    "en_AU": {"hl": "en-AU", "gl": "AU", "ceid": "AU:en"},
    "en_CA": {"hl": "en-CA", "gl": "CA", "ceid": "CA:en"},
    "en_SG": {"hl": "en",    "gl": "SG", "ceid": "SG:en"},
    "en_IN": {"hl": "en",    "gl": "IN", "ceid": "IN:en"},
    "en_PH": {"hl": "en",    "gl": "PH", "ceid": "PH:en"},
    "en_MY": {"hl": "en",    "gl": "MY", "ceid": "MY:en"},
    "en_ID": {"hl": "en",    "gl": "ID", "ceid": "ID:en"},
    # ── 亚洲 ──────────────────────────────────────────────────────
    "ja_JP": {"hl": "ja",    "gl": "JP", "ceid": "JP:ja"},
    "ko_KR": {"hl": "ko",    "gl": "KR", "ceid": "KR:ko"},
    "vi_VN": {"hl": "vi",    "gl": "VN", "ceid": "VN:vi"},
    "zh_TW": {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
    "th_TH": {"hl": "th",    "gl": "TH", "ceid": "TH:th"},
    # ── 欧洲 ──────────────────────────────────────────────────────
    "de_DE": {"hl": "de",    "gl": "DE", "ceid": "DE:de"},
    "fr_FR": {"hl": "fr",    "gl": "FR", "ceid": "FR:fr"},
    "nl_NL": {"hl": "nl",    "gl": "NL", "ceid": "NL:nl"},
    # ── 南美 ──────────────────────────────────────────────────────
    "pt_BR": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
    "es_MX": {"hl": "es",    "gl": "MX", "ceid": "MX:es"},
    # ── 中东 ──────────────────────────────────────────────────────
    "ar_SA": {"hl": "ar",    "gl": "SA", "ceid": "SA:ar"},
}

# ─── 信源权威层级映射 ─────────────────────────────────────────────────
#
# 用于影响评分: official > legal > industry > news
# get_source_tier() 先精确匹配 SOURCE_TIER_MAP，再用 SOURCE_TIER_PATTERNS 模糊匹配
#
SOURCE_TIER_MAP = {
    # ── official ──────────────────────────────────────────────────────
    "FTC News":                       "official",
    "Federal Register (FTC)":         "official",
    "ICO News (UK)":                  "official",
    "UK Gov (Ofcom/Gaming)":          "official",
    "UK Gov (Children Online Safety)":"official",
    "CNIL":                           "official",
    "Korean MOLEG":                   "official",
    "GRAC":                           "official",
    "KCA":                            "official",
    "GDPR.eu News":                   "official",   # 官方解读机构
    # ── legal ─────────────────────────────────────────────────────────
    "IAPP News":                      "legal",
    "IAPP":                           "legal",
    "Lexology":                       "legal",
    "JD Supra":                       "legal",
    "Law360":                         "legal",
    # ── industry ──────────────────────────────────────────────────────
    "GamesIndustry.biz":              "industry",
    "Android Developers Blog":        "industry",
    "GamesBeat":                      "industry",
    "Kotaku":                         "industry",
    "Polygon":                        "industry",
    "Eurogamer":                      "industry",
    "PC Gamer":                       "industry",
    "IGN":                            "industry",
    "ISFE":                           "industry",
    "ESA":                            "industry",
}

# Google News 源名称模糊匹配（按优先级从高到低）
SOURCE_TIER_PATTERNS = [
    ("official", (
        r"\bFTC\b|\bFederal Trade Commission\b"
        r"|Information Commissioner(?:'s Office)?"
        r"|\bCNIL\b|\bICO\b|\beSafety\b"
        r"|\bGRAC\b|\bKCA\b|\bMOLEG\b"
        r"|Federal Register"
        r"|Ministry of (?:Culture|Information|Communication|Justice)"
        r"|Kominfo|KemenKominfo"
        r"|MIC.*Viet|Bộ Thông tin"
        r"|Senado|Senaat|Bundestag|Parliament"
        r"|Consumer Financial Protection"
        r"|Attorney General"
        r"|Data Protection Authority|Data Protection Board"
        r"|Office of (?:the |)Privacy Commissioner"
    )),
    ("legal", (
        r"\bIAPP\b|Lexology|JD Supra|Law360"
        r"|Baker McKenzie|Latham & Watkins|White & Case"
        r"|Clifford Chance|Dentons|Covington"
        r"|law firm|law office|legal (?:news|update|alert)"
        r"|counsel|attorney|solicitor"
    )),
    ("industry", (
        r"GamesIndustry|GamesBeat|Kotaku|Polygon|Eurogamer"
        r"|PC Gamer|\bIGN\b|\bISFE\b|\bESA\b"
        r"|game.*industry|gaming.*media|game.*news"
    )),
]

# ─── 输出配置 ─────────────────────────────────────────────────────────

OUTPUT_DIR = "reports"
DATABASE_PATH = "data/monitor.db"
MAX_ARTICLE_AGE_DAYS = 90
FETCH_TIMEOUT = 30
MAX_CONCURRENT_REQUESTS = 5

# 周报/月报对应天数
PERIOD_DAYS = {
    "week":  7,
    "month": 30,
    "all":   90,
}
