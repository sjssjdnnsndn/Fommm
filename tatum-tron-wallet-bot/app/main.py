from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import settings
from .db import Database
from .handlers import BotHandlers
from .services import WalletService
from .tatum import TatumClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands([
        ("start", "Open wallet"),
        ("wallet", "Show wallet"),
        ("deposit", "Deposit USDT/TRX"),
        ("withdraw", "Withdraw USDT/TRX"),
        ("tip", "Tip a user"),
        ("swap", "Swap USDT/TRX"),
        ("history", "Transaction history"),
    ])


async def post_shutdown(application: Application) -> None:
    await application.bot_data["tatum"].close()
    await application.bot_data["db"].close()


def build_application() -> Application:
    db = Database(settings.mongodb_uri, settings.mongodb_db)
    tatum = TatumClient(settings.tatum_api_key, settings.tatum_base_url)
    wallet = WalletService(db, tatum, settings)
    h = BotHandlers(db, wallet, settings)

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["db"] = db
    app.bot_data["tatum"] = tatum
    app.bot_data["wallet"] = wallet
    app.bot_data["handlers"] = h

    app.add_handler(CommandHandler("start", h.start))
    app.add_handler(CommandHandler("wallet", h.start))
    app.add_handler(CommandHandler("deposit", h.begin_deposit))
    app.add_handler(CommandHandler("withdraw", h.begin_withdraw))
    app.add_handler(CommandHandler("tip", h.tip_command))
    app.add_handler(CommandHandler("swap", h.begin_swap))
    app.add_handler(CommandHandler("history", h.history))
    app.add_handler(CommandHandler("admin", h.admin))

    app.add_handler(CallbackQueryHandler(h.menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(h.asset_callback, pattern=r"^(withdraw):"))
    app.add_handler(CallbackQueryHandler(h.swap_direction, pattern=r"^swapdir:"))
    app.add_handler(CallbackQueryHandler(h.confirm_withdraw, pattern=r"^confirmwd:"))
    app.add_handler(CallbackQueryHandler(h.confirm_tip, pattern=r"^confirmtip$"))
    app.add_handler(CallbackQueryHandler(h.confirm_swap, pattern=r"^confirmswap$"))
    app.add_handler(CallbackQueryHandler(h.admin_callback, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(h.handle_pin_callback, pattern=r"^pin:"))
    app.add_handler(CallbackQueryHandler(h.cancel, pattern=r"^(cancel|canceltip)$"))
    app.add_handler(MessageHandler(filters.ANIMATION, h.animation))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, h.handle_text))

    if app.job_queue:
        app.job_queue.run_repeating(
            h.deposit_scan_job,
            interval=settings.deposit_scan_interval_seconds,
            first=20,
            name="deposit-scanner",
        )

    return app


async def initialize_db(application: Application) -> None:
    await application.bot_data["db"].init()


if __name__ == "__main__":
    import asyncio

    # AsyncMongoClient binds to the event loop used for its first operation.
    # Keep database initialization and Telegram polling on that same loop.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = build_application()
    loop.run_until_complete(initialize_db(app))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
