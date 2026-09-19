from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from html import escape

AMOUNT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([uUtT])$")
TIP_RE = re.compile(r"^(?:/)?tip\s+(.+?)\s+([0-9]+(?:\.[0-9]+)?[uUtT])\s*$", re.I)


def quantize_asset(value: Decimal, asset: str) -> Decimal:
    places = 6 if asset == "USDT" else 6
    return value.quantize(Decimal("1." + "0" * places), rounding=ROUND_DOWN)


def parse_amount_token(token: str) -> tuple[Decimal, str]:
    m = AMOUNT_RE.fullmatch(token.strip())
    if not m:
        raise ValueError("Use 500u for USDT or 500T for TRX.")
    try:
        amount = Decimal(m.group(1))
    except InvalidOperation as exc:
        raise ValueError("Invalid amount.") from exc
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    asset = "USDT" if m.group(2).lower() == "u" else "TRX"
    return quantize_asset(amount, asset), asset


def parse_tip_text(text: str) -> tuple[str, Decimal, str] | None:
    m = TIP_RE.match(text.strip())
    if not m:
        return None
    target = m.group(1).strip()
    amount, asset = parse_amount_token(m.group(2))
    return target, amount, asset


def fmt_amount(value: Decimal, asset: str) -> str:
    places = 6 if asset == "USDT" else 6
    q = value.quantize(Decimal("1." + "0" * places), rounding=ROUND_DOWN)
    text = format(q, "f").rstrip("0").rstrip(".")
    return text or "0"


def asset_emoji(asset: str) -> str:
    return "💵" if asset == "USDT" else "💎"


def asset_label(asset: str) -> str:
    return "USDT (TRC20)" if asset == "USDT" else "TRX"


def safe_html(value: str) -> str:
    return escape(value, quote=False)


def mention_html(user_id: int, username: str | None = None) -> str:
    if username:
        return "@" + safe_html(username.lstrip("@"))
    return f'<a href="tg://user?id={user_id}">user</a>'
