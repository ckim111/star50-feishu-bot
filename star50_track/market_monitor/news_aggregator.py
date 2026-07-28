"""
??????????

???
1. ?????? - reportapi.eastmoney.com
2. ?????? - guba.eastmoney.com
3. (???) ?? / ???

?????
- ???? LLM?OpenAI / DeepSeek???
- ???????????/??/?????
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import requests
from .market_data import HEADERS

logger = logging.getLogger(__name__)

RATING_MAP = {
    "??": "??", "??": "??", "??": "??",
    "????": "??", "????": "??", "????": "??",
    "??": "??", "????": "??", "??": "??",
    "??": "??", "??": "??", "??": "??", "????": "??",
}


@dataclass
class OpinionItem:
    title: str
    source: str
    url: str = ""
    publish_date: str = ""
    rating: str = ""
    stance: str = ""
    summary: str = ""


@dataclass
class OpinionSummary:
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0
    items: List[OpinionItem] = field(default_factory=list)
    llm_summary: str = ""
    method: str = "mechanical"


def aggregate_opinions(
    keyword: str = "??50",
    report_page_size: int = 5,
    guba_page_size: int = 10,
    request_interval: float = 1.0,
    sources=None,
    llm_config=None,
) -> OpinionSummary:
    sources = sources or []
    enabled = {s["name"] for s in sources if s.get("enabled")}
    items: list = []

    if "??????" in enabled:
        try:
            items.extend(_fetch_reports(keyword, report_page_size))
            time.sleep(request_interval)
        except Exception as e:
            logger.warning("??????: %s", e)

    if "??????" in enabled:
        try:
            items.extend(_fetch_guba_posts(guba_page_size))
            time.sleep(request_interval)
        except Exception as e:
            logger.warning("??????: %s", e)

    bullish = sum(1 for i in items if i.stance == "??")
    bearish = sum(1 for i in items if i.stance == "??")
    neutral = sum(1 for i in items if i.stance == "??")

    summary = OpinionSummary(
        bullish=bullish, bearish=bearish, neutral=neutral,
        items=items, method="mechanical",
    )

    if llm_config and llm_config.get("api_key") and items:
        llm_result = _llm_summarize(items, llm_config)
        if llm_result:
            summary.llm_summary = llm_result
            summary.method = "llm"

    return summary


def _fetch_reports(keyword: str, page_size: int) -> list:
    url = "https://reportapi.eastmoney.com/report/list"
    params = {
        "industryCode": "", "pageSize": page_size * 3,
        "industry": "", "rating": "", "ratingChange": "",
        "beginTime": "", "endTime": "", "pageNo": 1,
        "fields": "", "qType": 0, "qWord": keyword,
        "orgCode": "", "rcode": "",
        "_": int(time.time() * 1000),
    }
    resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    reports = data.get("data", [])
    items = []
    for r in reports:
        title = r.get("title", "")
        if keyword not in title and "??" not in title:
            continue
        rating_name = r.get("emRatingName", "")
        stance = RATING_MAP.get(rating_name, "??")
        info_code = r.get("infoCode", "")
        items.append(OpinionItem(
            title=title,
            source=f"{r.get('orgSName', '')} ??",
            url=f"https://data.eastmoney.com/report/zw_industry.jshtml?infocode={info_code}" if info_code else "",
            publish_date=r.get("publishDate", "")[:10],
            rating=rating_name, stance=stance,
        ))
        if len(items) >= page_size:
            break
    return items


def _fetch_guba_posts(page_size: int) -> list:
    url = "https://gbapi.eastmoney.com/GetTopicList"
    params = {
        "uid": "", "shareCode": "zssh000688",
        "pageIndex": 1, "pageSize": page_size,
        "sort": "reply", "callback": "",
        "_": int(time.time() * 1000),
    }
    resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    posts = data.get("Data", [])
    items = []
    for p in posts:
        title = p.get("post_title", "")
        if not title:
            continue
        post_id = p.get("post_id", "")
        stance = _simple_sentiment(title)
        items.append(OpinionItem(
            title=title, source="??????",
            url=f"https://guba.eastmoney.com/news,zssh000688,{post_id}.html" if post_id else "",
            publish_date=str(p.get("post_publish_time", ""))[:10] if p.get("post_publish_time") else "",
            stance=stance,
        ))
    return items


def _llm_summarize(items: list, llm_config: dict) -> str:
    provider = llm_config.get("provider", "openai").lower()
    api_key = llm_config.get("api_key", "")
    api_base = llm_config.get("api_base", "")
    model = llm_config.get("model", "")
    template = llm_config.get("prompt_template", "????{raw_text}")

    raw_lines = []
    for item in items:
        raw_lines.append(f"[{item.source}] {item.stance}: {item.title}")
    raw_text = "\n".join(raw_lines[:15])
    prompt = template.format(raw_text=raw_text)
    try:
        if provider == "deepseek":
            return _call_deepseek(prompt, api_key, api_base, model)
        else:
            return _call_openai(prompt, api_key, api_base, model)
    except Exception as e:
        logger.warning("LLM ????: %s", e)
        return ""


def _call_openai(prompt: str, api_key: str, api_base: str, model: str) -> str:
    url = f"{api_base.rstrip('/')}/chat/completions" if api_base else "https://api.openai.com/v1/chat/completions"
    model = model or "gpt-4o-mini"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 300},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_deepseek(prompt: str, api_key: str, api_base: str, model: str) -> str:
    url = f"{api_base.rstrip('/')}/chat/completions" if api_base else "https://api.deepseek.com/v1/chat/completions"
    model = model or "deepseek-chat"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 300},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _simple_sentiment(text: str) -> str:
    bullish_words = ["?", "?", "??", "??", "??", "??", "??", "??", "??", "?"]
    bearish_words = ["?", "?", "??", "??", "??", "?", "??", "??", "??", "?"]
    score = 0
    for w in bullish_words:
        if w in text:
            score += 1
    for w in bearish_words:
        if w in text:
            score -= 1
    if score > 0:
        return "??"
    elif score < 0:
        return "??"
    return "??"
