"""
A 股交易日历模块。

判断逻辑（优先级递减）：
1. 周六/周日 → 非交易日
2. 使用 chinese_calendar 库检测节假日
3. config 中的 extra_holidays / extra_trading_days 覆盖
"""

import datetime
from typing import List, Optional


def _load_chinese_calendar():
    """尝试加载 chinese_calendar，失败返回 None"""
    try:
        from chinese_calendar import is_workday  # type: ignore
        return is_workday
    except ImportError:
        return None


def is_trading_day(
    date: Optional[datetime.date] = None,
    extra_holidays: Optional[List[str]] = None,
    extra_trading_days: Optional[List[str]] = None,
) -> bool:
    """
    判断是否为 A 股交易日。

    Args:
        date: 要判断的日期，默认今天
        extra_holidays: 额外休市日，格式 ['2026-05-01', ...]
        extra_trading_days: 额外交易日（调休周末），格式同上

    Returns:
        True 表示是交易日
    """
    if date is None:
        date = datetime.date.today()

    extra_holidays = extra_holidays or []
    extra_trading_days = extra_trading_days or []
    date_str = date.strftime("%Y-%m-%d")

    # 1. 基于 chinese_calendar 库
    is_workday_fn = _load_chinese_calendar()
    if is_workday_fn is not None:
        is_work = is_workday_fn(date)
    else:
        # 2. 降级：仅排除周末
        is_work = date.weekday() < 5

    # 3. 配置覆盖
    if date_str in extra_holidays:
        return False
    if date_str in extra_trading_days:
        return True

    return is_work


def should_run_today(extra_holidays=None, extra_trading_days=None) -> bool:
    """便捷函数：今天是否为交易日"""
    return is_trading_day(
        date=datetime.date.today(),
        extra_holidays=extra_holidays,
        extra_trading_days=extra_trading_days,
    )
