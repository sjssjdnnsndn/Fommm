from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(add_to_group_url: str = "") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💰 Deposit", callback_data="menu:deposit"), InlineKeyboardButton("💸 Withdraw", callback_data="menu:withdraw")],
        [InlineKeyboardButton("↗️ Transfer", callback_data="menu:transfer"), InlineKeyboardButton("📥 Receive", callback_data="menu:receive")],
        [InlineKeyboardButton("🎁 Tip", callback_data="menu:tip")],
        [InlineKeyboardButton("🔄 Swap", callback_data="menu:swap"), InlineKeyboardButton("👤 Personal Center", callback_data="menu:profile")],
        [InlineKeyboardButton("📜 History", callback_data="menu:history")],
    ]
    if add_to_group_url:
        rows.append([InlineKeyboardButton("👥 Add to Group", url=add_to_group_url)])
    return InlineKeyboardMarkup(rows)


def assets_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 USDT (TRC20)", callback_data=f"{prefix}:USDT")],
        [InlineKeyboardButton("💎 TRX", callback_data=f"{prefix}:TRX")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])


def pin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data="pin:1"), InlineKeyboardButton("2", callback_data="pin:2"), InlineKeyboardButton("3", callback_data="pin:3")],
        [InlineKeyboardButton("4", callback_data="pin:4"), InlineKeyboardButton("5", callback_data="pin:5"), InlineKeyboardButton("6", callback_data="pin:6")],
        [InlineKeyboardButton("7", callback_data="pin:7"), InlineKeyboardButton("8", callback_data="pin:8"), InlineKeyboardButton("9", callback_data="pin:9")],
        [InlineKeyboardButton("取消", callback_data="pin:cancel"), InlineKeyboardButton("0", callback_data="pin:0"), InlineKeyboardButton("⌫", callback_data="pin:back")],
    ])


def confirm_keyboard(confirm_data: str, cancel_data: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data=confirm_data), InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)]
    ])


def swap_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("USDT → TRX", callback_data="swapdir:USDT:TRX")],
        [InlineKeyboardButton("TRX → USDT", callback_data="swapdir:TRX:USDT")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Tip GIF", callback_data="admin:gif")],
        [InlineKeyboardButton("💱 Swap Rate", callback_data="admin:rate")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin:stats")],
        [InlineKeyboardButton("❌ Close", callback_data="cancel")],
    ])
