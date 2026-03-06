"""
全球互联网合规动态监控工具 - 配置文件
覆盖领域: 数据隐私、AI 合规、未成年人保护、平台与竞争合规、
         广告营销合规、消费者保护、知识产权、内容监管、经营合规
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
        "focus": ["GDPR", "DSA", "DMA", "EU AI Act", "Online Safety Act", "消费者保护", "平台竞争"],
    },
    "北美": {
        "countries": ["美国", "加拿大"],
        "focus": ["FTC执法", "COPPA", "CCPA", "KOSA", "各州隐私法", "AI训练版权", "平台反垄断"],
    },
    "南美": {
        "countries": ["巴西", "阿根廷", "墨西哥", "智利", "哥伦比亚"],
        "focus": ["LGPD", "消费者保护", "数据充分性", "内容分级", "广告合规"],
    },
    "东南亚": {
        "countries": ["越南", "印度尼西亚", "泰国", "菲律宾", "马来西亚", "新加坡"],
        "focus": ["个人数据保护法", "PDPA", "未成年保护", "平台许可", "消费者保护"],
    },
    "南亚": {
        "countries": ["印度", "巴基斯坦", "孟加拉国"],
        "focus": ["DPDPA", "数字平台规范", "GST数字税", "在线中介规则"],
    },
    "港澳台": {
        "countries": ["香港", "澳门", "台湾"],
        "focus": ["个资法", "数字平台监管", "消费者保护", "未成年保护"],
    },
    "日本": {
        "countries": ["日本"],
        "focus": ["特商法", "资金决済法", "App Store反垄断", "个人信息保护法", "未成年保护"],
    },
    "韩国": {
        "countries": ["韩国"],
        "focus": ["个人信息保护法", "平台竞争", "消费者保护", "未成年保护"],
    },
    "大洋洲": {
        "countries": ["澳大利亚", "新西兰"],
        "focus": ["Online Safety Act", "Privacy Act", "Age Verification", "AI注册", "生物识别"],
    },
    "中东/非洲": {
        "countries": ["沙特", "阿联酋", "土耳其", "尼日利亚", "南非"],
        "focus": ["儿童数字安全", "数据保护", "内容监管", "平台许可"],
    },
}

REGION_DISPLAY_ORDER = [
    "欧洲", "北美", "南美", "东南亚", "南亚", "港澳台", "日本", "韩国", "大洋洲", "中东/非洲",
]

# ─── 一级分类 / 二级分类 ──────────────────────────────────────────────

CATEGORIES = {
    "数据隐私": [
        "GDPR/欧盟数据保护",
        "CCPA/美国各州隐私法",
        "儿童隐私(COPPA)",
        "跨境数据传输",
        "数据本地化",
        "生物识别数据",
        "数据泄露通知",
    ],
    "AI合规": [
        "AI法规立法",
        "AI训练数据版权",
        "AI代理与自动化",
        "生成式AI治理",
        "AI责任与风险",
    ],
    "未成年人保护": [
        "年龄验证",
        "社交媒体年龄限制",
        "未成年消费限制",
        "儿童数字安全",
        "家长控制",
    ],
    "平台与竞争合规": [
        "DSA/数字服务法",
        "DMA/数字市场法",
        "App Store反垄断",
        "平台透明度义务",
        "第三方支付开放",
    ],
    "广告营销合规": [
        "虚假/误导广告",
        "暗黑模式",
        "网红/KOL合规",
        "定向广告合规",
        "价格透明度",
    ],
    "消费者保护": [
        "退款政策",
        "订阅自动续费",
        "随机付费机制",
        "消费者权益诉讼",
        "虚假宣传",
    ],
    "知识产权": [
        "AI训练数据版权",
        "平台版权责任",
        "内容抓取与爬虫",
        "版权执法",
    ],
    "内容监管": [
        "违法内容治理",
        "仇恨言论",
        "AI生成内容",
        "内容分级",
    ],
    "经营合规": [
        "本地代理/代表处",
        "数字服务许可",
        "税务合规",
        "外资限制",
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

# ─── 搜索关键词库（聚焦全球互联网合规）──────────────────────────────────

KEYWORDS = {
    "en": [
        # === 数据隐私 ===
        "GDPR enforcement fine 2026",
        "data protection authority fine",
        "CCPA CPRA enforcement action",
        "state privacy law enforcement 2026",
        "biometric data regulation law",
        "facial recognition ban regulation",
        "data breach notification law",
        "cross-border data transfer restriction",
        "data localization requirement law",
        "cookie consent enforcement fine",
        "personal data protection law new",
        "data adequacy decision",

        # === AI 合规 ===
        "EU AI Act compliance enforcement",
        "AI regulation law 2026",
        "AI training copyright lawsuit",
        "generative AI regulation law",
        "AI liability legislation",
        "AI agent legal regulation",
        "LLM training data copyright",
        "AI generated content regulation",
        "deepfake regulation ban law",
        "AI governance framework law",
        "machine learning copyright infringement",
        "foundation model regulation",
        "AI scraping copyright law",

        # === 未成年人保护 ===
        "age verification law social media",
        "children online safety act",
        "social media age ban minor law",
        "minor protection digital platform law",
        "youth online safety legislation",
        "KOSA Kids Online Safety Act",
        "children digital safety law",
        "parental consent digital platform",
        "COPPA enforcement 2026",
        "FTC children online privacy fine",
        "under 16 social media ban",
        "age verification requirement platform",
        "child protection online regulation",

        # === 平台与竞争合规 ===
        "Digital Services Act enforcement fine",
        "DSA enforcement 2026",
        "Digital Markets Act compliance gatekeeper",
        "DMA enforcement penalty",
        "app store antitrust regulation",
        "Apple App Store antitrust fine",
        "Google Play antitrust regulation",
        "digital platform antitrust enforcement",
        "third party payment regulation",
        "platform transparency obligation",
        "online platform regulation enforcement",
        "gatekeeper obligation DMA",

        # === 广告营销合规 ===
        "dark pattern ban regulation",
        "deceptive design enforcement fine",
        "influencer disclosure law enforcement",
        "misleading advertising fine digital",
        "targeted advertising ban children",
        "dark pattern fine platform",
        "sponsored content disclosure rule",
        "deceptive advertising FTC enforcement",

        # === 消费者保护 ===
        "auto-renewal subscription law",
        "digital consumer protection enforcement",
        "online consumer rights regulation",
        "subscription trap fine regulation",
        "loot box consumer protection law",
        "gacha regulation consumer law",
        "in-app purchase consumer protection",
        "virtual currency consumer protection",
        "microtransaction consumer regulation",

        # === 知识产权 ===
        "AI training copyright lawsuit settlement",
        "platform copyright liability",
        "web scraping copyright law",
        "copyright infringement AI platform",
        "digital copyright enforcement fine",
        "content scraping legal action",
        "piracy enforcement digital",
        "streaming copyright regulation",

        # === 内容监管 ===
        "content moderation regulation law",
        "illegal content removal obligation",
        "online safety content law",
        "hate speech regulation fine",
        "misinformation regulation platform",
        "content rating digital platform",
        "harmful content law enforcement",

        # === 经营合规 ===
        "digital platform local representative requirement",
        "digital service license regulation",
        "digital services tax",
        "online platform registration requirement",
        "foreign digital platform local entity",
    ],

    # ── 英国专项（UK-specific regulations）──────────────────────────
    "en_uk": [
        "UK Online Safety Act Ofcom enforcement",
        "UK ICO enforcement fine 2026",
        "UK CMA digital markets antitrust",
        "UK children social media age restriction",
        "UK AI regulation governance",
        "UK data protection enforcement fine",
    ],

    # ── 澳大利亚专项 ──────────────────────────────────────────────
    "en_au": [
        "Australia eSafety Commissioner enforcement",
        "Australia Online Safety Act platform",
        "Australia age verification social media law",
        "Australia Privacy Act OAIC enforcement",
        "Australia children social media ban law",
        "Australia ACCC digital platform antitrust",
    ],

    # ── 新加坡 / 东南亚英文专项 ──────────────────────────────────
    "en_sg": [
        "Singapore PDPA enforcement personal data fine",
        "Singapore Online Safety Act IMDA",
        "Southeast Asia digital platform regulation 2026",
        "Singapore digital services platform compliance",
    ],

    "ja": [
        "デジタルプラットフォーム規制 法律 2026",
        "個人情報保護 法改正",
        "AI 著作権 法律 規制",
        "未成年者 SNS 規制 年齢確認",
        "アプリストア 競争法 反独占",
        "特商法 デジタル サービス",
        "消費者庁 デジタル 処分 罰則",
        "子ども オンライン 安全 法律",
        "データ保護 プラットフォーム 規制",
        "生成AI 規制 著作権",
        "プラットフォーム 透明性 義務",
    ],

    "ko": [
        "개인정보보호 법안 플랫폼 2026",
        "AI 규제 법안 저작권",
        "미성년자 SNS 이용 제한 법률",
        "플랫폼 공정거래 규제",
        "앱스토어 반독점 규제",
        "디지털 서비스 소비자 보호 법안",
        "콘텐츠 규제 법안 플랫폼",
        "청소년 보호 온라인 법률",
        "온라인 플랫폼 법안 규제",
        "데이터 보호 규제 법안",
    ],

    "vi": [
        "quy định nền tảng số 2026",
        "bảo vệ dữ liệu cá nhân Việt Nam",
        "luật bảo vệ trẻ em trực tuyến",
        "quy định AI nền tảng số",
        "bảo vệ người tiêu dùng số",
        "Nghị định mạng xã hội",
    ],

    "id": [
        "regulasi platform digital Indonesia 2026",
        "perlindungan data pribadi Indonesia",
        "regulasi AI Indonesia",
        "perlindungan anak online Indonesia",
        "regulasi konten digital Kominfo",
        "persaingan usaha platform digital",
    ],

    "de": [
        "Datenschutz Plattform Regulierung 2026",
        "DSGVO Durchsetzung Strafe",
        "Digitale Dienste Gesetz Plattform",
        "Jugendschutz Online Plattform Gesetz",
        "KI Regulierung Gesetz Deutschland",
        "Wettbewerbsrecht App Store",
        "Verbraucherschutz Digital Gesetz",
        "Hassrede Online Plattform Regulierung",
    ],

    "fr": [
        "réglementation plateforme numérique 2026",
        "RGPD amende enforcement",
        "loi protection mineurs réseaux sociaux",
        "règlement intelligence artificielle",
        "DSA règlement services numériques",
        "droit d'auteur IA formation",
        "protection consommateurs numérique loi",
        "dark pattern interdiction loi",
    ],

    "pt": [
        "regulação plataforma digital Brasil 2026",
        "LGPD enforcement multa",
        "proteção dados pessoais Brasil lei",
        "regulação IA Brasil lei",
        "proteção criança internet lei Brasil",
        "antitruste plataforma digital Brasil",
        "proteção consumidor digital SENACON",
        "adequação dados Brasil União Europeia",
    ],

    "es": [
        "regulación plataforma digital ley 2026",
        "RGPD multa cumplimiento España",
        "ley protección menores redes sociales",
        "regulación inteligencia artificial ley",
        "ley derechos digitales consumidor",
        "antimonopolio tienda aplicaciones ley",
        "protección datos personales ley",
        "contenido ilegal plataforma regulación",
    ],

    "zh_tw": [
        "數位平台監管 法規 2026",
        "個資法 執法 數位平台",
        "未成年 社群媒體 保護法",
        "AI 規範 著作權 法規",
        "平台競爭法 反壟斷",
        "消費者保護 數位服務 法規",
        "數位服務法 平台義務",
    ],

    "th": [
        "กฎหมายแพลตฟอร์มดิจิทัล ไทย 2026",
        "PDPA บังคับใช้ แพลตฟอร์ม",
        "คุ้มครองเด็ก ออนไลน์ กฎหมาย",
        "กฎหมาย AI ไทย",
        "คุ้มครองผู้บริโภค ดิจิทัล กฎหมาย",
    ],

    "ar": [
        "تنظيم المنصات الرقمية قانون 2026",
        "حماية البيانات الشخصية قانون",
        "حماية الأطفال الإنترنت قانون",
        "تنظيم الذكاء الاصطناعي قانون",
        "حماية المستهلك الرقمي قانون",
        "مكافحة الاحتكار المتاجر تطبيقات",
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
        "name": "Federal Register (FTC)",
        "url": "https://www.federalregister.gov/articles/search.rss?conditions[agencies][]=federal-trade-commission",
        "lang": "en",
        "type": "rss",
        "region": "北美",
        "tier": "official",
    },
    {
        "name": "UK Gov (Ofcom/Digital Regulation)",
        "url": "https://www.gov.uk/search/news-and-communications.atom?keywords=online+safety+digital+platform&organisations%5B%5D=ofcom",
        "lang": "en",
        "type": "rss",
        "region": "欧洲",
        "tier": "official",
    },
    {
        "name": "UK Gov (Children Online Safety)",
        "url": "https://www.gov.uk/search/news-and-communications.atom?keywords=children+online+safety+age+verification",
        "lang": "en",
        "type": "rss",
        "region": "欧洲",
        "tier": "official",
    },
    {
        "name": "UK ICO News",
        "url": "https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/?format=rss",
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
    {
        "name": "IAPP Privacy News",
        "url": "https://iapp.org/feed/",
        "lang": "en",
        "type": "rss",
        "region": "全球",
        "tier": "legal",
    },

    # ── 官方 (Official tier 补充) ─────────────────────────────────────
    {
        "name": "EDPB News",
        "url": "https://edpb.europa.eu/news/news_rss_en",
        "lang": "en",
        "type": "rss",
        "region": "欧洲",
        "tier": "official",
    },

    # ── 行业媒体 (Industry tier) ──────────────────────────────────────
    {
        "name": "EFF Deeplinks",
        "url": "https://www.eff.org/rss/updates.xml",
        "lang": "en",
        "type": "rss",
        "region": "全球",
        "tier": "industry",
    },
    {
        "name": "Tech Policy Press",
        "url": "https://techpolicy.press/feed/",
        "lang": "en",
        "type": "rss",
        "region": "全球",
        "tier": "industry",
    },
    # 注: TechCrunch / The Verge 已移除（每月 ~2700 条但相关率 <1%，主要噪音来源）
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

SOURCE_TIER_MAP = {
    # ── official ──────────────────────────────────────────────────────
    "FTC News":                          "official",
    "Federal Register (FTC)":            "official",
    "UK Gov (Ofcom/Digital Regulation)": "official",
    "UK Gov (Children Online Safety)":   "official",
    "UK ICO News":                       "official",
    "EDPB News":                         "official",
    # ── legal ─────────────────────────────────────────────────────────
    "GDPR.eu News":                      "legal",
    "IAPP Privacy News":                 "legal",
    "IAPP":                              "legal",
    "Lexology":                          "legal",
    "JD Supra":                          "legal",
    "Law360":                            "legal",
    # ── industry ──────────────────────────────────────────────────────
    "EFF Deeplinks":                     "industry",
    "Tech Policy Press":                 "industry",
    "TechCrunch":                        "industry",   # 保留映射（可能出现在 Google News 结果）
    "The Verge":                         "industry",   # 保留映射（可能出现在 Google News 结果）
    "Wired":                             "industry",
    "Ars Technica":                      "industry",
    "The Information":                   "industry",
}

SOURCE_TIER_PATTERNS = [
    ("official", (
        r"\bFTC\b|\bFederal Trade Commission\b"
        r"|Information Commissioner(?:'s Office)?"
        r"|\bCNIL\b|\bICO\b|\beSafety\b"
        r"|\bEDPB\b|\bAEPD\b|\bGarante\b"
        r"|Federal Register"
        r"|Ministry of (?:Digital|Information|Communication|Justice|Economy)"
        r"|Kominfo|KemenKominfo"
        r"|MIC.*Viet|Bộ Thông tin"
        r"|Senado|Bundestag|Parliament"
        r"|Consumer Financial Protection"
        r"|Attorney General"
        r"|Data Protection Authority|Data Protection Board"
        r"|Office of (?:the |)Privacy Commissioner"
        r"|European Commission|European Parliament"
        r"|Competition and Markets Authority|\bCMA\b"
        r"|Autorité de la concurrence"
        r"|Bundeskartellamt"
    )),
    ("legal", (
        r"\bIAPP\b|Lexology|JD Supra|Law360"
        r"|Baker McKenzie|Latham & Watkins|White & Case"
        r"|Clifford Chance|Dentons|Covington"
        r"|law firm|law office|legal (?:news|update|alert)"
        r"|counsel|attorney|solicitor"
        r"|GDPR\.eu"
    )),
    ("industry", (
        r"TechCrunch|The Verge|Wired|Ars Technica"
        r"|EFF|Electronic Frontier Foundation"
        r"|Axios|Politico.*Tech|Protocol"
        r"|tech.*news|digital.*media"
    )),
]

# ─── 输出配置 ─────────────────────────────────────────────────────────

OUTPUT_DIR = "reports"
DATABASE_PATH = "data/monitor.db"
MAX_ARTICLE_AGE_DAYS = 90
FETCH_TIMEOUT = 30
MAX_CONCURRENT_REQUESTS = 5

PERIOD_DAYS = {
    "week":  7,
    "month": 30,
    "all":   90,
}
