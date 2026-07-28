"""
??????????????

???????? IM API ?? interactive ?????
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class FeishuCardSender:
    """?????????"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        receiver_open_id: str,
        base_url: str = "https://open.feishu.cn",
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.receiver_open_id = receiver_open_id
        self.base_url = base_url.rstrip("/")
        self._token: Optional[str] = None
        self._token_expire: float = 0.0

    def _get_token(self) -> str:
        """?? tenant_access_token???????"""
        if self._token and time.time() < self._token_expire - 60:
            return self._token

        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        resp = requests.post(
            url,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"???? token ??: {data}")

        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + data.get("expire", 7200)
        return self._token

    def send_card(self, card: Dict[str, Any]) -> Dict:
        """???????????"""
        token = self._get_token()
        url = f"{self.base_url}/open-apis/im/v1/messages?receive_id_type=open_id"

        body = {
            "receive_id": self.receiver_open_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }

        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") != 0:
            raise RuntimeError(f"????????: {result}")
        return result


# ---------------------------------------------------------------------------
# ????
# ---------------------------------------------------------------------------

def build_intraday_card(
    index_name: str,
    index_code: str,
    price: float,
    change_pct: float,
    change: float,
    open_price: float,
    high: float,
    low: float,
    prev_close: float,
    amount: float,
    up_count: int,
    down_count: int,
    opinion_text: str,
    source_links: List[Dict[str, str]],
    color_up: str,
    color_down: str,
    data_time: str = "",
    disclaimer: str = "",
    guba_url: str = "",
) -> Dict:
    """?? 14:45 ??????"""

    is_up = change_pct >= 0
    color = color_up if is_up else color_down
    sign = "+" if is_up else ""
    arrow = "?" if is_up else "?"

    # ?????
    opinion_lines = []
    if opinion_text:
        opinion_lines.append({"tag": "text", "text": opinion_text})

    # ????
    link_elements = []
    for link in source_links[:3]:
        link_elements.append({
            "tag": "a",
            "text": link.get("title", "??"),
            "href": link.get("url", ""),
        })
    if guba_url:
        link_elements.append({
            "tag": "a",
            "text": "????",
            "href": guba_url,
        })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{index_name} ????"},
            "template": color,
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": False, "text": {
                        "tag": "lark_md",
                        "content": f"**{sign}{change_pct:.2f}%** {arrow} ? {sign}{change:.2f}",
                    }},
                ],
            },
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**??**\n{price:.2f}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**??**\n{open_price:.2f}"}},
                ],
            },
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**??**\n{high:.2f}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**??**\n{low:.2f}"}},
                ],
            },
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**??**\n{prev_close:.2f}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**???**\n{amount/1e8:.1f}?"}},
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**?? ??????**"},
            },
        ],
    }

    if opinion_lines:
        card["elements"].extend(opinion_lines)

    if link_elements:
        card["elements"].append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "?".join([f"[{l['text']}]({l['href']})" for l in link_elements])},
        })

    if data_time:
        card["elements"].append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": f"????: {data_time}"}],
        })

    if disclaimer:
        card["elements"].append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": f"? {disclaimer}"}],
        })

    return card


def build_close_card(
    fund_code: str,
    fund_nav: float,
    fund_change_pct: float,
    fund_date: str,
    index_name: str,
    index_close: float,
    index_change_pct: float,
    index_change: float,
    index_amount: float,
    opinion_text: str,
    source_links: List[Dict[str, str]],
    color_up: str,
    color_down: str,
    disclaimer: str = "",
    guba_url: str = "",
) -> Dict:
    """?? 17:30 ????????"""

    fund_is_up = fund_change_pct >= 0
    color = color_up if fund_is_up else color_down
    sign_f = "+" if fund_is_up else ""
    arrow_f = "?" if fund_is_up else "?"

    idx_is_up = index_change_pct >= 0
    sign_i = "+" if idx_is_up else ""
    arrow_i = "?" if idx_is_up else "?"

    link_elements = []
    for link in source_links[:3]:
        link_elements.append({
            "tag": "a",
            "text": link.get("title", "??"),
            "href": link.get("url", ""),
        })
    if guba_url:
        link_elements.append({
            "tag": "a",
            "text": "????",
            "href": guba_url,
        })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"?? {fund_code} ????"},
            "template": color,
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": False, "text": {
                        "tag": "lark_md",
                        "content": f"**?? {sign_f}{fund_change_pct:.2f}%** {arrow_f} ? ???? {fund_nav:.4f}",
                    }},
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{index_name} ??** {sign_i}{index_change_pct:.2f}% {arrow_i} ? ?? {index_close:.2f} ? ?? {sign_i}{index_change:.2f}"},
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**?? ??????**"},
            },
        ],
    }

    if opinion_text:
        card["elements"].append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": opinion_text},
        })

    if link_elements:
        card["elements"].append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "?".join([f"[{l['text']}]({l['href']})" for l in link_elements])},
        })

    card["elements"].append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"????: {fund_date}" if fund_date else ""}],
    })

    if disclaimer:
        card["elements"].append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": f"? {disclaimer}"}],
        })

    return card
