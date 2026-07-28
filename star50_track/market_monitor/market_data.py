"""
东方财富行情数据拉取模块。

数据来源：
- 股票/指数实时行情: push2.eastmoney.com
- 基金净值历史: api.fund.eastmoney.com
- 基金实时估算: fundgz.1234567.com.cn
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# 通用请求头
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.eastmoney.com/",
}


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class IndexQuote:
    """指数行情快照"""
    name: str
    code: str
    price: float               # 最新价
    open: float                # 开盘价
    high: float                # 最高价
    low: float                 # 最低价
    prev_close: float          # 昨收
    change: float              # 涨跌额
    change_pct: float          # 涨跌幅 (%)
    volume: float              # 成交量 (手)
    amount: float              # 成交额 (元)
    timestamp: int             # 数据时间戳 (Unix 秒)
    up_count: int = 0          # 上涨家数
    down_count: int = 0        # 下跌家数


@dataclass
class FundNav:
    """基金净值数据"""
    code: str
    name: str = ""
    date: str = ""             # 净值日期 YYYY-MM-DD
    unit_nav: float = 0.0      # 单位净值
    acc_nav: float = 0.0       # 累计净值
    daily_change_pct: float = 0.0  # 日涨跌幅 (%)
    estimate_nav: float = 0.0  # 实时估算净值 (仅盘中)
    estimate_change_pct: float = 0.0  # 估算涨跌幅 (%)


@dataclass
class NewsItem:
    """新闻/观点条目"""
    title: str
    url: str
    source: str                # 来源
    publish_time: str          # 发布时间
    summary: str = ""          # 摘要


# ---------------------------------------------------------------------------
# 行情拉取
# ---------------------------------------------------------------------------

def fetch_index_quote(secid: str) -> IndexQuote:
    """
    获取指数实时行情。

    Args:
        secid: 东方财富证券代码，如 '1.000688' (科创50)

    Returns:
        IndexQuote 实例

    字段说明 (东方财富 push2 接口, 单位: 价格类 /100, 涨跌额 /100, 涨跌幅 /100):
        f43=最新价  f44=最高  f45=最低  f46=开盘
        f47=成交量  f48=成交额  f50=量比
        f57=代码  f58=名称  f60=昨收
        f107=交易状态  f169=涨跌额  f170=涨跌幅
        f171=振幅  f86=时间戳
    """
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    fields = "f43,f44,f45,f46,f47,f48,f50,f57,f58,f60,f86,f107,f168,f169,f170,f171"
    params = {"secid": secid, "fields": fields, "ut": "fa5fd1943c7b386f172d6893dbfdc10c"}

    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            if attempt < 2:
                logger.warning('行情请求重试 %d/3: %s', attempt + 1, e)
                time.sleep(1)
            else:
                raise

    if data.get("rc") != 0 or not data.get("data"):
        raise RuntimeError(f"行情接口异常: {data}")

    d = data["data"]
    return IndexQuote(
        name=d.get("f58", ""),
        code=d.get("f57", ""),
        price=_div100(d.get("f43")),
        open=_div100(d.get("f46")),
        high=_div100(d.get("f44")),
        low=_div100(d.get("f45")),
        prev_close=_div100(d.get("f60")),
        change=_div100(d.get("f169")),
        change_pct=_div100(d.get("f170")),
        volume=d.get("f47", 0) or 0,
        amount=d.get("f48", 0) or 0,
        timestamp=d.get("f86", 0) or 0,
        up_count=d.get("f168", 0) or 0,
        down_count=d.get("f171", 0) or 0,
    )


def fetch_fund_nav(fund_code: str) -> FundNav:
    """
    获取基金最新净值（历史接口，盘后可用）。

    Args:
        fund_code: 基金代码，如 '011609'
    """
    url = "https://api.fund.eastmoney.com/f10/lsjz"
    params = {"fundCode": fund_code, "pageIndex": 1, "pageSize": 2}
    headers = {**HEADERS, "Referer": f"https://fund.eastmoney.com/{fund_code}.html"}

    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            if attempt < 2:
                logger.warning('基金净值请求重试 %d/3: %s', attempt + 1, e)
                time.sleep(1)
            else:
                raise

    if data.get("ErrCode") != 0:
        raise RuntimeError(f"基金净值接口异常: {data}")

    records = data.get("Data", {}).get("LSJZList", [])
    if not records:
        raise RuntimeError(f"基金 {fund_code} 无净值数据")

    latest = records[0]
    return FundNav(
        code=fund_code,
        date=latest.get("FSRQ", ""),
        unit_nav=_to_float(latest.get("DWJZ")),
        acc_nav=_to_float(latest.get("LJJZ")),
        daily_change_pct=_to_float(latest.get("JZZZL")),
    )


def fetch_fund_estimate(fund_code: str) -> Optional[FundNav]:
    """
    获取基金盘中实时估算净值。
    仅在交易时段有效，非交易时段可能返回无意义数据。
    """
    url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    # 响应格式: jsonpgz({...});
    text = resp.text
    match = re.search(r"jsonpgz\((.+)\)", text)
    if not match:
        logger.warning("基金估算接口解析失败: %s", text[:200])
        return None

    import json
    d = json.loads(match.group(1))
    return FundNav(
        code=fund_code,
        name=d.get("name", ""),
        estimate_nav=_to_float(d.get("gsz")),
        estimate_change_pct=_to_float(d.get("gszzl")),
        unit_nav=_to_float(d.get("dwjz")),
        date=d.get("jzrq", ""),
    )


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _div100(val: Any) -> float:
    """东方财富行情字段统一除以 100"""
    if val is None:
        return 0.0
    try:
        return float(val) / 100.0
    except (TypeError, ValueError):
        return 0.0


def _to_float(val: Any) -> float:
    """安全字符串转浮点"""
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
