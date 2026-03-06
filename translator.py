"""
翻译/摘要模块

优先路径：Groq API（OpenAI 兼容格式，免费）
  - 标题格式：[地区/国家] 核心事件，专有名词保留英文（TikTok/Meta/GDPR 等）
  - 摘要格式：监管对象 + 具体限制 + 违规后果，30-50 字，内容须与标题显著不同

回退路径：Google Translate（LLM_API_KEY 未配置时）
"""

import json
import logging
import os
import re
import time
from typing import Optional
from utils import bigram_sim

logger = logging.getLogger(__name__)

# ── 内部大模型客户端（OpenAI 兼容） ──────────────────────────────────

_LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
_LLM_API_KEY  = os.environ.get("LLM_API_KEY", "")
_LLM_MODEL    = os.environ.get("LLM_MODEL", "Qwen/Qwen3-8B")  # 可通过环境变量覆盖

# Qwen3 系列默认开启思维链（会生成大段推理过程），翻译场景无需思考直接输出；
# 其他模型不支持此参数则传空 dict，由硅基流动忽略。
_LLM_EXTRA_BODY = {"enable_thinking": False} if "Qwen3" in _LLM_MODEL else {}

try:
    from openai import OpenAI as _OpenAI
    _AI_CLIENT = _OpenAI(api_key=_LLM_API_KEY, base_url=_LLM_BASE_URL, timeout=25.0, max_retries=0) if _LLM_API_KEY else None
    _HAS_AI = bool(_LLM_API_KEY)
    if not _HAS_AI:
        logger.info("LLM_API_KEY 未设置，将使用 Google Translate 回退")
except ImportError:
    _AI_CLIENT = None
    _HAS_AI = False
    logger.warning("openai 未安装，将使用 Google Translate。运行: pip install openai")

# ── Google Translate 回退 ─────────────────────────────────────────────

try:
    from deep_translator import GoogleTranslator
    _HAS_TRANSLATOR = True
except ImportError:
    _HAS_TRANSLATOR = False
    logger.warning("deep-translator 未安装。运行: pip install deep-translator")

_cache: dict = {}

# ── 专有名词纠错表 ────────────────────────────────────────────────────
# 修正 AI 生成中常见的音译/意译错误，将其替换回受保护的英文原文

_TERM_CORRECTIONS: dict[str, str] = {
    # Loot Box（最常见的错误意译）
    "战利品箱": "Loot Box", "战利品盒": "Loot Box", "战利品包": "Loot Box",
    "掉落箱":   "Loot Box", "收藏箱":   "Loot Box",
    # Gacha
    "加查": "Gacha", "扭蛋机制": "Gacha 机制",
    # Deepfake
    "深度伪造": "Deepfake",
    # Discord
    "迪斯科": "Discord",
    # Twitch
    "推趣": "Twitch",
    # Roblox（未成年保护场景常见）
    "罗布乐思": "Roblox",
    # 货币单位错误音译
    "拉布尔": "卢布", "卢伯": "卢布", "鲁布": "卢布",   # ruble 误译
    "里尔": "雷亚尔",                                   # real (巴西) 误译保护
}


def _apply_term_corrections(text: str) -> str:
    """将 AI 常见音译/意译错误替换回受保护的英文原文。"""
    for wrong, right in _TERM_CORRECTIONS.items():
        text = text.replace(wrong, right)
    return text



# ── AI Prompt ─────────────────────────────────────────────────────────

_AI_SYSTEM = """你是全球互联网平台合规法规分析师，专注互联网企业监管动态，需完成四项任务并输出 JSON。

【任务一：相关性判断（is_relevant）】
is_relevant = false 的情形——直接返回 {"is_relevant": false}，无需翻译：
- 纯产品评测 / 新品发布 / 技术版本更新（无监管背景）
- 电竞赛事 / 赌场博彩 / 彩票（无合规议题）
- 公司财报 / 融资 / 裁员（无监管动作）
- 排行榜 / 推荐文章 / 开发者大会活动
is_relevant = true：涉及立法 / 监管 / 执法 / 政策草案 / 合规要求的互联网平台动态，包括但不限于：
数据隐私执法、AI 监管、平台竞争、内容监管、未成年人保护、知识产权、广告合规

【任务二：地区识别（region）】
从文章内容判断最相关地区，从以下选一个：
欧盟 英国 德国 法国 荷兰 比利时 奥地利 意大利 西班牙 波兰 瑞典 挪威
美国 加拿大 巴西 墨西哥 阿根廷 智利 哥伦比亚
越南 印度尼西亚 泰国 菲律宾 马来西亚 新加坡
印度 巴基斯坦 孟加拉国
台湾 香港 澳门 日本 韩国
澳大利亚 新西兰 沙特 阿联酋 土耳其 尼日利亚 南非
全球 其他
若参考地区已给出且合理，优先采用；若不准确则修正。

【任务三：分类与状态】
category_l1 选一个：数据隐私 AI合规 未成年人保护 平台与竞争合规 广告营销合规 消费者保护 知识产权 内容监管 经营合规
status 选一个：已生效 即将生效 草案/征求意见 立法进行中 已提案 修订变更 已废止 执法动态 立法动态

【任务四：翻译与深度分析（仅 is_relevant=true 时执行）】

专有名词保护清单——以下术语禁止音译或意译，必须保留英文原文：
公司/平台：Apple、Google、Meta、TikTok、ByteDance、YouTube、Netflix、Spotify、Microsoft、Amazon、Twitter/X、Reddit、Discord、LinkedIn、Snap
监管机构：FTC、ICO、CNIL、EDPB、Ofcom、CMA、FCA、ANPD、PDPC、Kominfo、KCA
法规/机制：GDPR、CCPA、CPRA、COPPA、DSA、DMA、PDPA、LGPD、EU AI Act、DPDPA、Loot Box、Gacha、NFT
技术术语：Deepfake、App Store、Google Play、LLM（AI 可译为"人工智能"）

标题规则：
- 格式固定：[地区/国家] 核心事件简述
- 专有名词保留英文，其余文字必须为中文
- 严格 35 字以内（含方括号）
- 禁止媒体机构名称后缀（Reuters、BBC、Bloomberg 等）
- 禁止疑问句，一律改为陈述句

摘要规则（summary_zh）：
- 严禁复制或改写标题；标题已说明的事件不再重复，直接补充细节
- 严格 30-50 字
- 公式：[时间节点/起因] + [核心监管动作/罚款金额] + [受影响平台或后果]
- 若原始内容极少，必须基于专业知识合理扩充，严禁简单复述标题

正文分析规则（detail_zh）：
- 120-200 字，分析维度：①监管背景 ②核心监管细节（涉及哪些平台/数据类型/违规行为） ③对互联网企业的影响 ④后续走向
- 必须包含比摘要更丰富的细节和分析视角

摘要规则（summary_zh）修订：
- 禁止重复标题已描述的事件，直接补充标题中未含的具体细节
- 优先包含：生效/实施时间节点、具体罚款金额、受影响的平台名称、主管机构引用的条款
- 严格 30-50 字

合规提示规则（compliance_note）：
- 严格按以下三行格式输出（每行以换行符分隔）：
  【合规要求】[平台需执行的具体动作，如：年龄验证须在90天内上线、内容须3小时内下架]
  【业务影响】[受影响的具体业务线，如：短视频、直播、支付、用户注册]
  【风险预警】[违规的具体后果，如：最高500万欧元罚款、暂停运营许可]
- 每行不超过 30 字，不使用「建议」句式，直接陈述

【输出格式】仅输出合法 JSON，不含任何其他文字：
不相关时：{"is_relevant": false}
相关时：{"is_relevant": true, "region": "...", "category_l1": "...", "status": "...", "title_zh": "...", "summary_zh": "...", "detail_zh": "...", "compliance_note": "..."}"""


# ── LLM 分类结果合法值集合（用于校验，防止模型输出非法值）──────────────

_VALID_REGIONS = {
    "欧盟", "英国", "德国", "法国", "荷兰", "比利时", "奥地利", "意大利",
    "西班牙", "波兰", "瑞典", "挪威", "欧洲",
    "美国", "加拿大", "北美",
    "巴西", "墨西哥", "阿根廷", "智利", "哥伦比亚", "南美",
    "越南", "印度尼西亚", "泰国", "菲律宾", "马来西亚", "新加坡", "东南亚",
    "印度", "巴基斯坦", "孟加拉国", "南亚",
    "台湾", "香港", "澳门", "港澳台",
    "日本", "韩国",
    "澳大利亚", "新西兰", "大洋洲",
    "沙特", "阿联酋", "土耳其", "尼日利亚", "南非", "中东/非洲",
    "全球", "其他",
}

_VALID_CATEGORIES_L1 = {
    "数据隐私", "AI合规", "未成年人保护", "平台与竞争合规",
    "广告营销合规", "消费者保护", "知识产权", "内容监管", "经营合规",
}

_VALID_STATUSES = {
    "已生效", "即将生效", "草案/征求意见", "立法进行中",
    "已提案", "修订变更", "已废止", "执法动态", "立法动态",
}


# ── 文章正文抓取（最优先给 AI 提供上下文）────────────────────────────

def _fetch_article_body(url: str) -> str:
    """尝试获取文章正文前 500 字；超时或失败时静默返回空字符串。"""
    if not url or not url.startswith("http"):
        return ""
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html",
        }
        resp = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
        if not resp.ok:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        # 移除噪音标签
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        # 优先提取语义化正文区域
        for selector in ("article", "main", "[class*='article-body']",
                         "[class*='post-content']", "[class*='entry-content']"):
            el = soup.select_one(selector)
            if el:
                text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
                if len(text) > 80:
                    return text[:500]
        # 兜底：body 全文
        body = soup.find("body")
        if body:
            return re.sub(r"\s+", " ", body.get_text(" ", strip=True))[:500]
    except Exception:
        pass
    return ""


# ── Claude AI 处理 ────────────────────────────────────────────────────

def _ai_process(title: str, summary: str, body_snippet: str = "",
                region_hint: str = "", category_hint: str = "", status_hint: str = "") -> Optional[dict]:
    """
    调用 LLM 完成相关性判断 + 地区/分类/状态识别 + 中文标题摘要生成。
    返回包含 is_relevant、region、category_l1、status、title_zh、summary_zh 的 dict，
    或 None（调用失败时）。
    """
    if not _HAS_AI or not _AI_CLIENT:
        return None

    body_part = (
        f"\n文章正文片段（前500字）：{body_snippet}"
        if body_snippet and len(body_snippet) > 50
        else ""
    )
    # 将正则预分类结果作为参考提示传给 LLM
    hint_parts = []
    if region_hint:
        hint_parts.append(f"地区={region_hint}")
    if category_hint:
        hint_parts.append(f"分类={category_hint}")
    if status_hint:
        hint_parts.append(f"状态={status_hint}")
    hint_line = (
        f"\n初步分类参考（来自规则系统，可修正）：{'、'.join(hint_parts)}"
        if hint_parts else ""
    )
    # 内容不足时明确提示 AI 须扩充而非复述
    has_enough_context = (summary and len(summary) > 40) or (body_snippet and len(body_snippet) > 50)
    lean_warning = (
        "\n⚠️ 原始内容极少，请依据专业背景知识扩充摘要，禁止简单复述标题。"
        if not has_enough_context else ""
    )
    user_msg = (
        f"英文标题：{title}\n"
        f"原始摘要：{summary or '（无）'}"
        f"{body_part}"
        f"{hint_line}"
        f"{lean_warning}"
    )

    try:
        resp = _AI_CLIENT.chat.completions.create(
            model=_LLM_MODEL,
            max_tokens=700,
            extra_body=_LLM_EXTRA_BODY,
            messages=[
                {"role": "system", "content": _AI_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        )
        text = resp.choices[0].message.content.strip()
        logger.info(f"[AI raw] {text[:200]}")   # 打印返回内容，方便排查

        # 兼容多种输出格式，含截断修复
        # 1. 先尝试剥离 markdown 代码块
        code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        json_str = code_block.group(1) if code_block else None
        # 2. 完整 {...}
        if not json_str:
            plain = re.search(r"\{.*\}", text, re.DOTALL)
            json_str = plain.group() if plain else None
        # 3. 截断修复：找到以 { 开头但没有结尾 } 的片段，补上
        if not json_str:
            partial = re.search(r"\{.*", text, re.DOTALL)
            if partial:
                json_str = partial.group().rstrip() + "}"

        if json_str:
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                data = {}

            # ── 步骤 4a：相关性判断 ────────────────────────────────────
            # LLM 明确返回 false 时直接过滤，省去后续翻译 token
            is_relevant = data.get("is_relevant")
            if is_relevant is False:
                logger.info(f"[AI过滤] 判定不相关: {title[:60]}")
                return {"is_relevant": False}

            # ── 步骤 4b：提取分类字段（校验合法性，非法值留空由正则兜底）─
            llm_region = (data.get("region") or "").strip()
            llm_category_l1 = (data.get("category_l1") or "").strip()
            llm_status = (data.get("status") or "").strip()

            if llm_region not in _VALID_REGIONS:
                if llm_region:
                    logger.debug(f"[AI] region 非法值 '{llm_region}'，回退正则")
                llm_region = ""
            if llm_category_l1 not in _VALID_CATEGORIES_L1:
                if llm_category_l1:
                    logger.debug(f"[AI] category_l1 非法值 '{llm_category_l1}'，回退正则")
                llm_category_l1 = ""
            if llm_status not in _VALID_STATUSES:
                if llm_status:
                    logger.debug(f"[AI] status 非法值 '{llm_status}'，回退正则")
                llm_status = ""

            title_zh        = (data.get("title_zh")       or "").strip()
            summary_zh      = (data.get("summary_zh")    or "").strip()
            detail_zh       = (data.get("detail_zh")     or "").strip()
            compliance_note = (data.get("compliance_note") or "").strip()
            # 4c. JSON 解析失败兜底：直接用正则从原文提取字段值
            if not title_zh or not summary_zh:
                tm = re.search(r'"title_zh"\s*:\s*"([^"]{2,})"', text)
                sm = re.search(r'"summary_zh"\s*:\s*"([^"]{2,})"', text)
                if tm:
                    title_zh = tm.group(1).strip()
                if sm:
                    summary_zh = sm.group(1).strip()
            if not detail_zh:
                dm = re.search(r'"detail_zh"\s*:\s*"([^"]{2,})"', text)
                if dm:
                    detail_zh = dm.group(1).strip()
            if not compliance_note:
                cm = re.search(r'"compliance_note"\s*:\s*"([^"]{2,})"', text)
                if cm:
                    compliance_note = cm.group(1).strip()
            if title_zh and summary_zh:
                # ── 步骤 5：JSON 残留字符清理 ─────────────────────────
                # 部分模型（如 Qwen）偶尔将 JSON 结构字符混入字段值
                title_zh   = re.sub(r'[\}\{"\s,]+$', '', title_zh).strip()
                summary_zh = re.sub(r'[\}\{"\s,]+$', '', summary_zh).strip()

                # ── 步骤 6：[地区] 前缀兜底修复 ──────────────────────
                # 若标题未以 [xxx] 开头，从原始英文标题或 item region 推断并补充
                if not re.match(r'^\[.+?\]', title_zh):
                    # 尝试从英文标题里找地区关键词（优先顺序：美国/英国/EU等）
                    _region_hints = [
                        ("美国",  r'\b(US|USA|United States|America[n]?|FTC|Congress|Senate|White House)\b'),
                        ("英国",  r'\b(UK|United Kingdom|Britain|British|ASA|Ofcom|ICO)\b'),
                        ("欧盟",  r'\b(EU|European Union|Europe[an]?|GDPR|DSA|DMA|CNIL)\b'),
                        ("韩国",  r'\b(Korea[n]?|South Korea|GRAC|KCA)\b'),
                        ("日本",  r'\b(Japan[ese]?)\b'),
                        ("澳大利亚", r'\b(Austral[ia]+[n]?|eSafety)\b'),
                        ("加拿大", r'\b(Canada[ian]?)\b'),
                        ("越南",  r'\b(Vietnam[ese]?)\b'),
                        ("印度",  r'\b(India[n]?)\b'),
                        ("中国",  r'\b(China|Chinese)\b'),
                        ("全球",  r'\b(global[ly]?|worldwide|international)\b'),
                    ]
                    inferred = None
                    for region_cn, pattern in _region_hints:
                        if re.search(pattern, title, re.IGNORECASE):
                            inferred = region_cn
                            break
                    if inferred:
                        title_zh = f"[{inferred}] {title_zh}"
                        logger.info(f"[AI] 补充 [地区] 前缀: [{inferred}] → {title_zh[:40]}")

                # ── 步骤 7：专有名词纠错 ──────────────────────────────
                title_zh   = _apply_term_corrections(title_zh)
                summary_zh = _apply_term_corrections(summary_zh)

                # ── 步骤 8：相似度检测，>55% 则要求重新生成摘要 ─────
                sim = bigram_sim(title_zh, summary_zh)
                if sim > 0.55:
                    logger.warning(
                        f"[AI] 摘要与标题 bigram 相似度 {sim:.0%}，触发重新生成"
                    )
                    time.sleep(4)
                    dedup_msg = (
                        f"{user_msg}\n\n"
                        f"上一次生成的摘要【{summary_zh}】与标题【{title_zh}】"
                        f"高度重复（相似度 {sim:.0%}），不符合要求。\n"
                        f"请严格按照公式重写摘要：[背景/起因] + [核心监管动作] + [具体后果（金额/期限/要求）]。"
                        f"摘要必须包含标题中没有的具体信息，30-50 字。"
                    )
                    try:
                        resp3 = _AI_CLIENT.chat.completions.create(
                            model=_LLM_MODEL,
                            max_tokens=300,
                            extra_body=_LLM_EXTRA_BODY,
                            messages=[
                                {"role": "system", "content": _AI_SYSTEM},
                                {"role": "user",   "content": dedup_msg},
                            ],
                        )
                        t3 = resp3.choices[0].message.content.strip()
                        logger.info(f"[AI dedup retry] {t3[:200]}")
                        tm3 = re.search(r'"title_zh"\s*:\s*"([^"]{2,})"', t3)
                        sm3 = re.search(r'"summary_zh"\s*:\s*"([^"]{2,})"', t3)
                        if sm3:
                            summary_zh = _apply_term_corrections(sm3.group(1).strip())
                        if tm3:
                            title_zh = _apply_term_corrections(tm3.group(1).strip())
                    except Exception as e3:
                        logger.warning(f"[AI] 相似度重试失败: {e3}")

                return {
                    "is_relevant":    True,
                    "title_zh":       title_zh,
                    "summary_zh":     summary_zh,
                    "detail_zh":      detail_zh,
                    "compliance_note": compliance_note,
                    "region":         llm_region,
                    "category_l1":    llm_category_l1,
                    "status":         llm_status,
                }
            logger.warning(f"[AI] JSON 字段为空: {json_str[:100]}")
        else:
            logger.warning(f"[AI] 返回内容中未找到 JSON: {text[:200]}")

    except Exception as e:
        err_msg = str(e)
        # 429 速率限制：提取建议等待时间
        retry_m = re.search(r'try again in (\d+\.?\d*)s', err_msg, re.IGNORECASE)
        # 500 服务端瞬时故障（硅基流动 50507 等）：固定等待 6s 后重试
        is_server_error = ('500' in err_msg or '50507' in err_msg or
                           'InternalServerError' in err_msg or 'unknown error' in err_msg.lower())

        if retry_m or is_server_error:
            if retry_m:
                wait_sec = min(float(retry_m.group(1)) + 1.5, 35.0)
                logger.warning(f"[AI] 速率限制，等待 {wait_sec:.1f}s 后重试")
            else:
                wait_sec = 6.0
                logger.warning(f"[AI] 服务端 500 错误，等待 {wait_sec:.1f}s 后重试一次")
            time.sleep(wait_sec)
            try:
                resp2 = _AI_CLIENT.chat.completions.create(
                    model=_LLM_MODEL,
                    max_tokens=300,
                    extra_body=_LLM_EXTRA_BODY,
                    messages=[
                        {"role": "system", "content": _AI_SYSTEM},
                        {"role": "user",   "content": user_msg},
                    ],
                )
                text2 = resp2.choices[0].message.content.strip()
                logger.info(f"[AI raw retry] {text2[:200]}")
                tm = re.search(r'"title_zh"\s*:\s*"([^"]{2,})"', text2)
                sm = re.search(r'"summary_zh"\s*:\s*"([^"]{2,})"', text2)
                if tm and sm:
                    return {"title_zh": tm.group(1).strip(), "summary_zh": sm.group(1).strip()}
            except Exception as e2:
                logger.warning(f"[AI] 重试失败: {type(e2).__name__}: {e2}")
        else:
            logger.warning(f"[AI] 调用异常: {type(e).__name__}: {e}")
    return None


# ── Google Translate 工具函数（回退路径）─────────────────────────────

def _is_mostly_chinese(text: str) -> bool:
    if not text:
        return False
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return chinese_count > len(text) * 0.3


def translate_to_zh(text: str, source_lang: str = "auto") -> str:
    """将文本翻译为中文，失败时返回原文"""
    if not text or not text.strip():
        return text
    if not _HAS_TRANSLATOR:
        return text
    if _is_mostly_chinese(text):
        return text
    cache_key = text[:200]
    if cache_key in _cache:
        return _cache[cache_key]
    try:
        result = GoogleTranslator(source=source_lang, target="zh-CN").translate(text[:500])
        if result:
            _cache[cache_key] = result
            return result
    except Exception as e:
        logger.debug(f"翻译失败: {e}")
    return text


def _build_source_text(item_dict: dict) -> str:
    """构建用于翻译的文本，智能拼接标题+摘要，清理 RSS 截断标记。"""
    title = (item_dict.get("title") or "").strip()
    summary = (item_dict.get("summary") or "").strip()
    # 清理 RSS 截断标记
    summary = re.sub(r"\s*[\[【][\+\d].*?[\]】]\s*$", "", summary).strip()
    summary = re.sub(r"\s*\.{2,}\s*$", "", summary).strip()
    summary = re.sub(r"\s*…\s*$", "", summary).strip()

    if not summary or len(summary) < 20:
        return title

    title_norm = re.sub(r"\s+", " ", title.lower())
    summary_norm = re.sub(r"\s+", " ", summary.lower())
    if summary_norm.startswith(title_norm[:50]):
        extra = summary[len(title_norm[:50]):].strip(" .-")
        combined = f"{title}. {extra}" if len(extra) > 20 else title
    else:
        sep = "。" if title.endswith(("。", "！", "？")) else ". "
        combined = f"{title}{sep}{summary}"
    return combined[:500]


def _ensure_complete_sentence(text: str) -> str:
    """确保翻译结果以完整句子结尾。"""
    if not text:
        return text
    if text[-1] in "。！？.!?":
        return text
    for sep in ["。", "！", "？", ".", "!", "?"]:
        idx = text.rfind(sep)
        if idx > len(text) * 0.4:
            return text[:idx + 1]
    return text


# ── AI 连通性预检（模块级缓存，只检测一次）──────────────────────────

_ai_reachable: Optional[bool] = None   # None=未检测, True=可用, False=不可用


def _check_ai_reachable() -> bool:
    """
    发送一个极小请求测试 LLM 代理是否可达。
    超时 10 秒即判定不可达，后续所有文章直接走 Google Translate，
    避免逐条等待 25 秒超时造成 CI 任务大幅延误。
    """
    global _ai_reachable
    if _ai_reachable is not None:
        return _ai_reachable
    try:
        _AI_CLIENT.chat.completions.create(
            model=_LLM_MODEL,
            max_tokens=5,
            timeout=10.0,
            extra_body=_LLM_EXTRA_BODY,
            messages=[{"role": "user", "content": "hi"}],
        )
        logger.info("[AI] 连通性预检通过，将使用 LLM 处理")
        _ai_reachable = True
    except Exception as e:
        err_str = str(e)
        # 429 表示 API 可达但触发速率限制，仍视为可用
        if "429" in err_str or "rate_limit" in err_str.lower():
            logger.info("[AI] 连通性预检触发速率限制，但 API 可达，将使用 LLM 处理")
            _ai_reachable = True
        else:
            logger.warning(
                f"[AI] 连通性预检失败，本次批量翻译全部使用 Google Translate 回退。"
                f"原因：{type(e).__name__}: {e}"
            )
            _ai_reachable = False
    return _ai_reachable


# ── LLM 批量翻译（3 篇/次，3× 吞吐，4s sleep/批次而非/条）──────────

def _ai_process_batch(items_data: list) -> list:
    """
    将 2-3 篇文章打包进一次 LLM 调用，返回等长结果列表。
    items_data: list of dict，每个 dict 含 title/summary/region_hint/category_hint/status_hint
    返回: list of dict（与 _ai_process() 格式相同），失败的条目对应位置为 None
    调用方收到 None 时应降级为单条 translate_item_fields()。
    """
    if not _HAS_AI or not _AI_CLIENT or not items_data:
        return [None] * len(items_data)

    n = len(items_data)
    parts = []
    for i, d in enumerate(items_data):
        hint_parts = []
        if d.get("region_hint"):
            hint_parts.append(f"地区={d['region_hint']}")
        if d.get("category_hint"):
            hint_parts.append(f"分类={d['category_hint']}")
        if d.get("status_hint"):
            hint_parts.append(f"状态={d['status_hint']}")
        hint_line = f"\n初步分类参考（可修正）：{'、'.join(hint_parts)}" if hint_parts else ""

        has_context = (d.get("summary") and len(d.get("summary", "")) > 40)
        lean_warn = "\n⚠️ 内容极少，需依专业背景扩充摘要。" if not has_context else ""

        parts.append(
            f"【文章{i + 1}】\n"
            f"英文标题：{d.get('title', '')}\n"
            f"原始摘要：{d.get('summary', '') or '（无）'}"
            f"{hint_line}{lean_warn}"
        )

    user_msg = (
        f"以下 {n} 篇文章，逐篇按顺序分析，返回长度严格为 {n} 的 JSON 数组，"
        f"每个元素格式与单篇相同（is_relevant=false 时只含该字段）。\n\n"
        + "\n\n".join(parts)
    )

    try:
        resp = _AI_CLIENT.chat.completions.create(
            model=_LLM_MODEL,
            max_tokens=800 * n,
            timeout=60.0,          # 批量调用生成量大，给足 60s（客户端默认 25s 易超时）
            extra_body=_LLM_EXTRA_BODY,
            messages=[
                {"role": "system", "content": _AI_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        )
        text = resp.choices[0].message.content.strip()
        logger.info(f"[AI batch raw] n={n} {text[:300]}")

        # 解析顶层 JSON 数组
        arr_m = re.search(r'\[.*\]', text, re.DOTALL)
        if arr_m:
            try:
                arr = json.loads(arr_m.group())
                if isinstance(arr, list) and len(arr) == n:
                    return arr
                logger.warning(f"[AI batch] 数组长度 {len(arr)} ≠ {n}，降级逐条处理")
            except json.JSONDecodeError as je:
                logger.warning(f"[AI batch] JSON 解析失败 ({je})，降级逐条处理")
        else:
            logger.warning(f"[AI batch] 未找到 JSON 数组，降级逐条处理: {text[:150]}")

    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "rate_limit" in err_str.lower():
            wait = min(float(re.search(r'try again in (\d+\.?\d*)s', err_str, re.IGNORECASE).group(1)) + 1.5
                       if re.search(r'try again in (\d+\.?\d*)s', err_str, re.IGNORECASE) else 6.0, 35.0)
            logger.warning(f"[AI batch] 速率限制，等待 {wait:.1f}s")
            time.sleep(wait)
        else:
            logger.warning(f"[AI batch] 调用失败，降级逐条处理: {type(e).__name__}: {e}")

    return [None] * n


# 地区前缀兜底规则（批量后处理时使用，与 _ai_process 内保持一致）
_REGION_PREFIX_RULES = [
    ("美国",    r'\b(US|USA|United States|America[n]?|FTC|Congress|Senate|White House)\b'),
    ("英国",    r'\b(UK|United Kingdom|Britain|British|ASA|Ofcom|ICO)\b'),
    ("欧盟",    r'\b(EU|European Union|Europe[an]?|GDPR|DSA|DMA|CNIL)\b'),
    ("韩国",    r'\b(Korea[n]?|South Korea|GRAC|KCA)\b'),
    ("日本",    r'\b(Japan[ese]?)\b'),
    ("澳大利亚", r'\b(Austral[ia]+[n]?|eSafety)\b'),
    ("加拿大",  r'\b(Canada[ian]?)\b'),
    ("越南",    r'\b(Vietnam[ese]?)\b'),
    ("印度",    r'\b(India[n]?)\b'),
    ("全球",    r'\b(global[ly]?|worldwide|international)\b'),
]


def translate_items_batch(items_dicts: list, batch_size: int = 3) -> list:
    """
    批量翻译和分类：每 batch_size 条发一次 LLM 请求（一次 4s sleep），
    单条失败时自动降级为 translate_item_fields()。
    返回列表与 items_dicts 等长，每条格式与 translate_item_fields() 相同。
    """
    if not items_dicts:
        return []

    # LLM 不可用时直接逐条 Google Translate
    if not (_HAS_AI and _check_ai_reachable()):
        return [translate_item_fields(d) for d in items_dicts]

    results = []

    for batch_start in range(0, len(items_dicts), batch_size):
        batch = items_dicts[batch_start: batch_start + batch_size]

        # 准备批量输入
        batch_data = [
            {
                "title":         (d.get("title")       or "").strip(),
                "summary":       (d.get("summary")     or "").strip(),
                "region_hint":   (d.get("region")      or "").strip(),
                "category_hint": (d.get("category_l1") or "").strip(),
                "status_hint":   (d.get("status")      or "").strip(),
            }
            for d in batch
        ]

        raw_results = _ai_process_batch(batch_data)

        for item_dict, raw in zip(batch, raw_results):
            if raw is None:
                # 批次失败 → 单条降级（已含内部 sleep）
                logger.info(f"[batch fallback] {item_dict.get('title','')[:40]}")
                results.append(translate_item_fields(item_dict))
                continue

            # LLM 判定不相关
            if raw.get("is_relevant") is False:
                item_dict["_llm_is_relevant"] = False
                results.append(item_dict)
                continue

            title_zh        = (raw.get("title_zh")        or "").strip()
            summary_zh      = (raw.get("summary_zh")     or "").strip()
            detail_zh       = (raw.get("detail_zh")      or "").strip()
            compliance_note = (raw.get("compliance_note") or "").strip()

            if not title_zh or not summary_zh:
                logger.info(f"[batch fallback] 字段为空 → 单条降级: {item_dict.get('title','')[:40]}")
                results.append(translate_item_fields(item_dict))
                continue

            # 清理 JSON 残留字符
            title_zh   = re.sub(r'[\}\{"\s,]+$', '', title_zh).strip()
            summary_zh = re.sub(r'[\}\{"\s,]+$', '', summary_zh).strip()

            # [地区] 前缀兜底
            if not re.match(r'^\[.+?\]', title_zh):
                for region_cn, pattern in _REGION_PREFIX_RULES:
                    if re.search(pattern, batch_data[batch.index(item_dict)]["title"], re.IGNORECASE):
                        title_zh = f"[{region_cn}] {title_zh}"
                        break

            # 专有名词纠错
            title_zh   = _apply_term_corrections(title_zh)
            summary_zh = _apply_term_corrections(summary_zh)

            # bigram 相似度过高 → 单条重试（含内部 sleep）
            if bigram_sim(title_zh, summary_zh) > 0.55:
                logger.warning(f"[batch] bigram 过高，单条重试: {title_zh[:40]}")
                results.append(translate_item_fields(item_dict))
                continue

            # 校验分类字段合法性
            llm_region   = (raw.get("region")      or "").strip()
            llm_category = (raw.get("category_l1") or "").strip()
            llm_status   = (raw.get("status")      or "").strip()
            if llm_region   not in _VALID_REGIONS:        llm_region   = ""
            if llm_category not in _VALID_CATEGORIES_L1:  llm_category = ""
            if llm_status   not in _VALID_STATUSES:        llm_status   = ""

            item_dict["title_zh"]         = title_zh
            item_dict["summary_zh"]       = summary_zh
            item_dict["detail_zh"]        = detail_zh
            item_dict["compliance_note"]  = compliance_note
            item_dict["_llm_is_relevant"] = True
            item_dict["_llm_region"]      = llm_region
            item_dict["_llm_category_l1"] = llm_category
            item_dict["_llm_status"]      = llm_status
            results.append(item_dict)

        # 每批次 sleep 一次（代替原来每条 sleep）
        time.sleep(4)

    return results


# ── LLM 批量重复验证（供 reporter.py 调用）────────────────────────────

def verify_duplicate_pairs(pairs: list) -> list:
    """
    批量 LLM 验证候选重复新闻对。
    pairs : [(title_zh_a, title_zh_b), ...]  每批最多 20 对
    返回  : [True/False, ...]  与 pairs 等长，True = 是同一事件
    不可用时（LLM 未配置/调用失败）全部返回 False（保守策略：不误删）。
    """
    if not pairs:
        return []
    if not _HAS_AI or not _AI_CLIENT:
        return [False] * len(pairs)

    # 截断到最多 20 对，避免超出 token 限制
    pairs = pairs[:20]

    pair_lines = "\n".join(
        f"{i + 1}. A：{a}\n   B：{b}"
        for i, (a, b) in enumerate(pairs)
    )
    user_msg = (
        f"以下 {len(pairs)} 对新闻标题，判断每对是否描述【同一事件】"
        f"（忽略来源差异，只看核心事件是否相同）。\n"
        f"只输出 JSON 布尔数组，长度必须等于 {len(pairs)}，"
        f"例如：[true, false, true]\n\n{pair_lines}"
    )

    try:
        resp = _AI_CLIENT.chat.completions.create(
            model=_LLM_MODEL,
            max_tokens=60 + len(pairs) * 8,
            extra_body=_LLM_EXTRA_BODY,
            messages=[
                {"role": "system", "content":
                 "你是新闻去重专家。判断两条中文新闻标题是否报道同一事件，"
                 "只输出 JSON 布尔数组，不含其他文字。"},
                {"role": "user", "content": user_msg},
            ],
        )
        text = resp.choices[0].message.content.strip()
        logger.info(f"[AI verify_dup] {text[:200]}")

        # 尝试解析 JSON 数组
        arr_m = re.search(r'\[.*?\]', text, re.DOTALL)
        if arr_m:
            result = json.loads(arr_m.group())
            if isinstance(result, list) and len(result) == len(pairs):
                return [bool(r) for r in result]

        # 兜底：按行解析 true/false
        tokens = re.findall(r'\b(true|false)\b', text.lower())
        if len(tokens) == len(pairs):
            return [t == 'true' for t in tokens]

        logger.warning(f"[AI verify_dup] 无法解析返回，保守返回 False: {text[:100]}")
    except Exception as e:
        logger.warning(f"[AI verify_dup] 调用失败: {e}")

    return [False] * len(pairs)


# ── 集群摘要合并（同事件多来源 → 一条富信息摘要）───────────────────────

def merge_cluster_summary(title_zh: str, summaries: list) -> str:
    """
    将同一事件多篇报道的摘要合并为一段富信息综合摘要（40-60字）。
    LLM 不可用时回退为返回第一条摘要。

    Args:
        title_zh:  该事件的中文标题（用于上下文）
        summaries: 各来源的 summary_zh 列表（至少 2 条）
    Returns:
        合并后的摘要字符串
    """
    if not summaries:
        return ""
    if len(summaries) == 1:
        return summaries[0]

    if not (_HAS_AI and _AI_CLIENT):
        return summaries[0]

    summaries_text = "\n".join(
        f"{i + 1}. {s}" for i, s in enumerate(summaries) if s.strip()
    )
    user_msg = (
        f"以下是同一合规事件「{title_zh}」来自 {len(summaries)} 个信源的摘要：\n\n"
        f"{summaries_text}\n\n"
        f"请将上述摘要整合为一段 40-60 字的综合摘要，"
        f"保留各方报道的补充细节（时间节点、具体罚款金额、受影响平台、专家观点），"
        f"去除重复信息，不使用项目符号，直接输出中文正文。"
    )
    try:
        resp = _AI_CLIENT.chat.completions.create(
            model=_LLM_MODEL,
            max_tokens=200,
            timeout=20.0,
            extra_body=_LLM_EXTRA_BODY,
            messages=[
                {"role": "system",
                 "content": "你是互联网合规新闻编辑，将多篇同主题报道整合为简洁综合摘要，"
                            "中文输出，不超过 60 字，不使用 Markdown。"},
                {"role": "user", "content": user_msg},
            ],
        )
        merged = resp.choices[0].message.content.strip()
        merged = re.sub(r'\*\*|__|\*|_|`|#+\s*', '', merged).strip()
        if len(merged) >= 20:
            logger.info(f"[merge_summary] 合并 {len(summaries)} 条摘要 → {len(merged)} 字")
            return merged
    except Exception as e:
        logger.warning(f"[merge_summary] LLM 合并失败，回退第一条: {e}")
    return summaries[0]


# ── 月度综述生成 ─────────────────────────────────────────────────────

def generate_executive_summary(items: list) -> str:
    """
    基于本月条目列表，用 LLM 生成 200-300 字的合规形势综述。
    LLM 不可用时回退为规则统计摘要。
    items: list of dict（含 title_zh、region、category_l1、status、impact_score）
    """
    if not items:
        return ""

    from collections import Counter
    cat_counts    = Counter(item.get("category_l1", "其他") for item in items)
    region_counts = Counter(item.get("region", "其他")      for item in items)
    high_priority = [i for i in items if int(i.get("impact_score", 1)) >= 3]
    enacted       = [i for i in items if i.get("status") in ("已生效", "即将生效")]
    top_cats      = [c for c, _ in cat_counts.most_common(3)]
    top_regions   = [r for r, _ in region_counts.most_common(3)]

    if _HAS_AI and _AI_CLIENT:
        # 取前 15 条高优先级条目作为上下文
        sample = sorted(items, key=lambda x: -int(x.get("impact_score", 1)))[:15]
        headlines = "\n".join(
            f"- [{i.get('region','')}][{i.get('category_l1','')}][{i.get('status','')}] "
            f"{i.get('title_zh','') or i.get('title','')}"
            for i in sample
        )
        user_msg = (
            f"以下是本月全球互联网平台合规动态（共 {len(items)} 条，"
            f"高优先级 {len(high_priority)} 条，已生效/即将生效 {len(enacted)} 条）"
            f"中影响力最高的 15 条标题：\n\n{headlines}\n\n"
            f"请生成一段 200-300 字的「本月合规形势综述」，"
            f"聚焦全球前三大合规趋势，语言简洁专业，"
            f"面向互联网企业（视频/直播/UGC/社交）海外合规负责人，"
            f"不使用 Markdown 标记，不分段，连贯叙述。"
        )
        try:
            resp = _AI_CLIENT.chat.completions.create(
                model=_LLM_MODEL,
                max_tokens=500,
                timeout=30.0,
                extra_body=_LLM_EXTRA_BODY,
                messages=[
                    {"role": "system",
                     "content": "你是互联网企业合规法务专家，用简洁中文撰写合规形势综述，"
                                "不使用 Markdown 格式，直接输出纯文字段落。"},
                    {"role": "user", "content": user_msg},
                ],
            )
            text = resp.choices[0].message.content.strip()
            # 去除意外的 Markdown 标记
            text = re.sub(r'\*\*|__|\*|_|`|#+\s*', '', text).strip()
            if len(text) >= 50:
                logger.info(f"[AI exec-summary] 生成综述 {len(text)} 字")
                return text
        except Exception as e:
            logger.warning(f"[AI exec-summary] 生成失败，回退规则摘要: {e}")

    # 规则回退
    return (
        f"本月共收录全球互联网平台合规动态 {len(items)} 条，"
        f"其中高优先级（已生效或执法动态）{len(high_priority)} 条，"
        f"已生效或即将生效法规 {len(enacted)} 条。"
        f"主要聚焦领域为{'、'.join(top_cats)}；"
        f"重点地区包括{'、'.join(top_regions)}。"
        f"建议合规团队重点关注{'、'.join(top_cats[:2])}领域的最新执法动向。"
    )


# ── 主入口 ────────────────────────────────────────────────────────────

def translate_item_fields(item_dict: dict) -> dict:
    """
    生成 title_zh、summary_zh，同时通过 LLM 完成相关性判断和分类优化。

    LLM 路径新增返回字段（存储在 item_dict 中，前缀 _llm_）：
      _llm_is_relevant  : bool  — False 表示 LLM 判定不相关，monitor.py 据此过滤
      _llm_region       : str   — LLM 识别的地区（空串表示回退正则）
      _llm_category_l1  : str   — LLM 识别的一级分类
      _llm_status       : str   — LLM 识别的状态

    优先：LLM AI（相关性过滤 + 分类识别 + 规范中文重塑 + 深度摘要）
    回退：Google Translate（字面翻译，跳过相关性判断）
    """
    title = (item_dict.get("title") or "").strip()
    summary = (item_dict.get("summary") or "").strip()

    # ── 路径一：LLM AI ────────────────────────────────────────────────
    if _HAS_AI and _check_ai_reachable():
        # 将正则预分类结果作为参考传给 LLM
        region_hint   = (item_dict.get("region")      or "").strip()
        category_hint = (item_dict.get("category_l1") or "").strip()
        status_hint   = (item_dict.get("status")      or "").strip()

        result = _ai_process(title, summary,
                             region_hint=region_hint,
                             category_hint=category_hint,
                             status_hint=status_hint)
        if result:
            # LLM 判定不相关：打标记后直接返回，不填充翻译字段
            if result.get("is_relevant") is False:
                item_dict["_llm_is_relevant"] = False
                return item_dict

            item_dict["title_zh"]         = result.get("title_zh", "")
            item_dict["summary_zh"]       = result.get("summary_zh", "")
            item_dict["_llm_is_relevant"] = True
            item_dict["_llm_region"]      = result.get("region", "")
            item_dict["_llm_category_l1"] = result.get("category_l1", "")
            item_dict["_llm_status"]      = result.get("status", "")
            time.sleep(4)   # 硅基流动免费层限速，4s 间隔确保不超限
            return item_dict
        logger.warning(f"AI 处理未返回有效结果，回退到 Google Translate: {title[:50]}")

    # ── 路径二：Google Translate 回退 ─────────────────────────────────
    if title and not _is_mostly_chinese(title):
        item_dict["title_zh"] = translate_to_zh(title[:200])
        time.sleep(0.15)
    else:
        item_dict["title_zh"] = title

    source_text = _build_source_text(item_dict)
    if _is_mostly_chinese(source_text):
        item_dict["summary_zh"] = source_text
    else:
        raw = translate_to_zh(source_text)
        item_dict["summary_zh"] = _ensure_complete_sentence(raw)
        time.sleep(0.2)

    return item_dict
