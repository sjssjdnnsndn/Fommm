---
name: TRON testnet operations
description: Secure wallet bootstrap and logging constraints for the Tatum TRON bot.
---

Generate a TRON wallet through Tatum's wallet endpoint, then keep the returned mnemonic and xpub only in workspace secrets. Keep the testnet USDT contract unset until a verified Shasta contract is intentionally configured.

**Why:** Tatum returns wallet credentials directly, and the mnemonic controls the treasury; testnet and mainnet token contracts are not interchangeable.

**How to apply:** Never print wallet responses or credentials. Also keep HTTP client request logging at warning level because Telegram bot tokens are embedded in request URLs.

The asynchronous MongoDB client must be initialized and used on the same event loop as Telegram polling; initializing it with a short-lived `asyncio.run` loop makes every later handler fail.

**Why:** PyMongo's `AsyncMongoClient` binds its low-level asyncio resources to the first loop that uses it.

**How to apply:** Create and set one event loop before building the application, initialize MongoDB on it, and start polling without switching loops.