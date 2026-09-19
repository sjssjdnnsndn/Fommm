# TRON Testnet Wallet Bot

Telegram custodial wallet bot for TRX and optional TRC20 test assets, using Tatum and MongoDB.

## Run & Operate

- `cd tatum-tron-wallet-bot && python -m app.main` — run the bot locally
- `TRON Testnet Wallet Bot` workflow — run the persistent Telegram polling worker
- Required secrets: `TELEGRAM_BOT_TOKEN`, `MONGODB_URI`, `TATUM_API_KEY`, `TRON_MNEMONIC`, `TRON_XPUB`
- The workflow forces `TRON_NETWORK=shasta`, disables mainnet private-key signing, and uses a testnet-only MongoDB database name.

## Stack

- Python 3.13
- Telegram: `python-telegram-bot`
- Database: MongoDB via `pymongo`
- Blockchain API: Tatum TRON endpoints

## Where things live

- `tatum-tron-wallet-bot/app/` — bot handlers, wallet service, database layer, and Tatum client
- `tatum-tron-wallet-bot/scripts/bootstrap_wallet.py` — Tatum wallet generation helper
- `tatum-tron-wallet-bot/.env.example` — configuration reference; do not create or commit a real `.env`

## Architecture decisions

- The internal MongoDB ledger is the source of truth for balances, tips, and swaps.
- This deployment is testnet-only; the workflow overrides the network and keeps the USDT contract empty until a verified Shasta token contract is supplied.
- Mainnet direct private-key signing remains disabled; production mainnet use requires Tatum KMS and treasury controls.

## Product

Users can create a PIN-protected wallet, receive a derived TRON address, scan confirmed deposits, withdraw, tip other Telegram users, swap internal balances, and view history.

## User preferences

- Start with Tatum Testnet and Shasta. Do not switch this workflow to mainnet without an explicit security and KMS migration.

## Gotchas

- Never print wallet mnemonic, xpub, private keys, API keys, or Telegram bot URLs in logs.
- `USDT_TRC20_CONTRACT` must stay empty for TRX-only Shasta testing; mainnet USDT's contract must not be reused on testnet.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
