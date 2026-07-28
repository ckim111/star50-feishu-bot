"""
?? A: ????? 14:45 ????50 ?????

??: GitHub Actions cron (UTC 06:45 = CST 14:45)
"""

import logging
import os
import sys
import yaml

# ???????? sys.path ?
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_monitor.trading_calendar import should_run_today
from market_monitor.market_data import fetch_index_quote
from market_monitor.news_aggregator import aggregate_opinions
from market_monitor.feishu_card import FeishuCardSender, build_intraday_card

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("task_a")


def main():
    # ????
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    fc = config["feishu"]
    cal = config.get("trading_calendar", {})

    # ?????
    if not should_run_today(
        extra_holidays=cal.get("extra_holidays", []),
        extra_trading_days=cal.get("extra_trading_days", []),
    ):
        logger.info("?????????")
        return

    # ????50 ????
    kc50 = None
    for idx in config.get("indices", []):
        if idx["id"] == "kc50":
            kc50 = idx
            break
    if not kc50:
        logger.error("?????50????")
        return

    # 1. ????
    logger.info("????50??...")
    quote = fetch_index_quote(kc50["secid"])
    logger.info(f"??50: {quote.price:.2f} ({quote.change_pct:+.2f}%)")

    # 2. ??????
    logger.info("??????...")
    news_cfg = config.get("news", {})
    llm_cfg = config.get("llm", {})
    # ????????? LLM API key
    llm_cfg = dict(llm_cfg)
    if os.environ.get("LLM_API_KEY"):
        llm_cfg["api_key"] = os.environ["LLM_API_KEY"]

    opinion = aggregate_opinions(
        keyword="??50",
        report_page_size=news_cfg.get("report_page_size", 5),
        guba_page_size=news_cfg.get("guba_page_size", 10),
        request_interval=news_cfg.get("request_interval", 1.0),
        sources=news_cfg.get("sources", []),
        llm_config=llm_cfg if llm_cfg.get("api_key") else None,
    )

    # ??????
    if opinion.llm_summary:
        opinion_text = opinion.llm_summary
    else:
        opinion_text = (
            f"?? {opinion.bullish} ??? / {opinion.bearish} ???"
            f" / {opinion.neutral} ???"
            + (" (????)" if opinion.method == "mechanical" else "")
        )

    # ????
    source_links = [
        {"title": i.source[:8], "url": i.url}
        for i in opinion.items if i.url
    ]
    guba_url = f"https://guba.eastmoney.com/list,{kc50.get('guba_code', 'zssh000688')}.html"

    # 3. ????
    card_cfg = config.get("card", {})
    card = build_intraday_card(
        index_name=kc50["name"],
        index_code=kc50["secid"],
        price=quote.price,
        change_pct=quote.change_pct,
        change=quote.change,
        open_price=quote.open,
        high=quote.high,
        low=quote.low,
        prev_close=quote.prev_close,
        amount=quote.amount,
        up_count=quote.up_count,
        down_count=quote.down_count,
        opinion_text=opinion_text,
        source_links=source_links,
        color_up=card_cfg.get("color_up", "#E53935"),
        color_down=card_cfg.get("color_down", "#43A047"),
        data_time="14:40",
        disclaimer=card_cfg.get("disclaimer", ""),
        guba_url=guba_url,
    )

    sender = FeishuCardSender(
        app_id=fc["app_id"],
        app_secret=fc["app_secret"],
        receiver_open_id=fc["receiver_open_id"],
        base_url=fc.get("base_url", "https://open.feishu.cn"),
    )

    logger.info("??????...")
    result = sender.send_card(card)
    logger.info(f"????: {result.get('data', {}).get('message_id', 'N/A')}")


if __name__ == "__main__":
    main()
