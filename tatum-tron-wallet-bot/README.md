# Tatum Free-plan TRON Telegram Wallet Bot

A Telegram custodial/internal-ledger wallet MVP for **USDT (TRC20)** and **TRX** using:

- Python + python-telegram-bot
- MongoDB
- Tatum TRON APIs
- Internal ledger for tips and swaps

## Included features

- `/start` wallet dashboard with screenshot-inspired button layout
- USDT TRC20 + TRX only
- Per-user TRON deposit address derived from one HD wallet
- Deposit scanner using Tatum account transaction APIs
- 5-digit payment PIN setup with keypad
- Withdrawal PIN required every withdrawal
- `$0.50` service fee model
- Full-balance withdrawal behavior: both fees are deducted from the full balance and only the net amount is sent
- Internal `/tip @username 500u` and `/tip @username 500T`
- Reply-tip: reply to a user's message with `/tip 500u`
- Tip confirmation before ledger movement
- Tip fee = 0
- Internal USDT ↔ TRX swap with admin-configurable rate
- Tip GIF configurable from the admin panel
- Transaction history
- Admin statistics
- MongoDB ledger + withdrawal records + idempotent deposit records

## Important scope decision

The bot's own MongoDB ledger is the source of truth for user balances. Internal tips and swaps do **not** broadcast blockchain transactions.

External withdrawals use the configured TRON treasury address in the initial MVP. Deposits are credited to the internal ledger when Tatum confirms incoming blockchain activity. A production deployment should add automated deposit-address sweeping/consolidation and formal treasury reconciliation.

## Tatum Free plan

Tatum currently lists a Free plan with **100K credits** and **3 RPS**. The code deliberately throttles the scanner and uses slow polling instead of relying on unlimited webhook monitoring. The default scanner checks up to 10 users every 15 minutes; tune this for your user count and credit budget.

Current relevant API credit costs documented by Tatum include:

- TRON wallet generation: 1 credit
- TRON address derivation from xpub: 5 credits
- TRON private-key derivation from mnemonic: 10 credits
- TRON account transactions: 5 credits/call
- TRON TRC20 transactions: 5 credits/call
- TRX transfer: 10 credits/call
- TRC20 transfer: 10 credits/call

See current Tatum docs before production because plans/limits can change.

## Security / mainnet

Tatum explicitly recommends using **Tatum KMS for mainnet signing** and warns against sending private keys to the transaction API. This project therefore defaults `ALLOW_MAINNET_PRIVATE_KEY_SIGNING=false`.

The free-plan testnet path can be used for development. To turn this into a production custodial wallet, integrate Tatum KMS, secure the KMS wallet.dat, add approval/risk controls, and implement deposit sweeping/treasury reconciliation.

## Setup

### 1. Create the Telegram bot

Use BotFather and copy the bot token.

### 2. Create MongoDB Atlas

Create a database and get the connection string.

### 3. Create Tatum keys

Create a Tatum account. The free account currently provides a Mainnet API key and a Testnet API key.

Start with the **Testnet API key**.

### 4. Generate your TRON HD wallet

Copy `.env.example` to `.env` and set `TATUM_API_KEY`.

Then run:

```bash
python scripts/bootstrap_wallet.py
```

Store the returned `mnemonic` and `xpub` in `.env`.

### 5. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6. Run

```bash
python -m app.main
```

## Testnet notes

Tatum's current TRON testnet documentation references Shasta. Testnet USDT is **not the same as mainnet USDT**. Put a suitable test TRC20 token contract into `USDT_TRC20_CONTRACT` before testing USDT deposits/withdrawals.

For TRX-only testing, the bot works with the TRON testnet native asset immediately once your testnet wallet is funded. The project intentionally leaves `USDT_TRC20_CONTRACT` empty by default; configure a verified Shasta token contract before enabling testnet USDT.

## Group `/tip` behavior

Use:

```text
/tip @username 500u
/tip @username 500T
```

or reply to a user's message:

```text
/tip 500u
/tip 500T
```

For plain text `tip @username 500u` without the slash, Telegram group privacy settings may prevent the bot from receiving the message. Use `/setprivacy` in BotFather and disable privacy if you want the no-slash form to work broadly in groups.

## Full-balance withdrawal example

If the user has 100 USDT and requests 100 USDT:

```text
Balance:          100.00 USDT
Network fee:       0.35 USDT
Service fee:       0.50 USDT
You receive:      99.15 USDT
```

The user's entire 100 USDT is debited from the internal ledger; only 99.15 USDT is sent on-chain.

## Deploying on Render

Use a Worker or another always-running service because this bot uses polling.

Required environment variables are the same as `.env`.

Do not commit `.env`, `TRON_MNEMONIC`, API keys, or KMS files.
