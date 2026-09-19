from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import Settings
from .db import Database, to_decimal
from .tatum import TatumClient
from .utils import fmt_amount


ph = PasswordHasher()


@dataclass
class FeeQuote:
    asset: str
    requested: Decimal
    network_fee: Decimal
    service_fee: Decimal
    total_debit: Decimal
    send_amount: Decimal
    full_balance_mode: bool


class WalletService:
    def __init__(self, db: Database, tatum: TatumClient, settings: Settings):
        self.db = db
        self.tatum = tatum
        self.settings = settings

    async def ensure_tron_address(self, user_id: int) -> str:
        user = await self.db.get_user(user_id)
        if user and user.get("tron_address"):
            return user["tron_address"]
        if not self.settings.tron_xpub:
            raise RuntimeError("TRON_XPUB is not configured. Run bootstrap_wallet.py first.")
        index = await self.db.next_tron_index(self.settings.user_index_start)
        address = await self.tatum.derive_address(self.settings.tron_xpub, index)
        if not address:
            raise RuntimeError("Tatum did not return a TRON address.")
        await self.db.set_wallet(user_id, index, address)
        return address

    async def set_pin(self, user_id: int, pin: str) -> None:
        if len(pin) != 5 or not pin.isdigit():
            raise ValueError("PIN must be exactly 5 digits.")
        await self.db.set_pin_hash(user_id, ph.hash(pin))

    async def verify_pin(self, user_id: int, pin: str) -> bool:
        user = await self.db.get_user(user_id)
        stored = (user or {}).get("pin_hash")
        if not stored:
            return False
        try:
            return ph.verify(stored, pin)
        except VerifyMismatchError:
            return False

    async def fee_quote(self, user_id: int, asset: str, requested: Decimal) -> FeeQuote:
        balances = await self.db.get_balances(user_id)
        balance = balances[asset]
        if requested <= 0 or requested > balance:
            raise ValueError("Invalid amount or insufficient balance.")

        if asset == "USDT":
            service_fee = self.settings.service_fee_usd
            network_fee = self.settings.usdt_network_fee_estimate
        else:
            # $0.50 converted to TRX using the admin-configured TRX/USDT rate.
            service_fee = (self.settings.service_fee_usd / self.settings.trx_usdt_rate).quantize(Decimal("0.000001"))
            network_fee = self.settings.trx_network_fee_estimate

        is_full = requested >= balance
        if is_full:
            send_amount = balance - network_fee - service_fee
            if send_amount <= 0:
                raise ValueError("Your full balance is too small to cover the withdrawal fees.")
            total_debit = balance
        else:
            total_debit = requested + network_fee + service_fee
            if total_debit > balance:
                raise ValueError(
                    f"Insufficient balance after fees. Available {fmt_amount(balance, asset)} {asset}."
                )
            send_amount = requested
        return FeeQuote(asset, requested, network_fee, service_fee, total_debit, send_amount, is_full)

    async def perform_withdrawal(self, withdrawal_id: str) -> str:
        wd = await self.db.get_withdrawal(withdrawal_id)
        if not wd:
            raise ValueError("Withdrawal not found.")
        user = await self.db.get_user(wd["user_id"])
        index = self.settings.treasury_index
        if self.settings.is_mainnet and not self.settings.allow_mainnet_private_key_signing:
            await self.db.mark_withdrawal(withdrawal_id, status="KMS_REQUIRED", error="Mainnet private-key signing is disabled. Configure Tatum KMS.")
            raise RuntimeError("Mainnet automatic signing is disabled. Configure Tatum KMS first.")
        if not self.settings.tron_mnemonic:
            raise RuntimeError("TRON_MNEMONIC is not configured.")

        private_key = await self.tatum.derive_private_key(self.settings.tron_mnemonic, index)
        asset = wd["asset"]
        send_amount = to_decimal(wd["send_amount"])
        destination = wd["destination"]
        await self.db.mark_withdrawal(withdrawal_id, status="BROADCASTING")
        try:
            if asset == "USDT":
                # feeLimit is an upper TRX resource budget, not the user's final USDT fee.
                fee_limit = float(self.settings.trx_network_fee_estimate * self.settings.fee_reserve_multiplier)
                result = await self.tatum.send_trc20(
                    private_key,
                    destination,
                    self.settings.usdt_trc20_contract,
                    str(send_amount),
                    fee_limit,
                )
            else:
                result = await self.tatum.send_trx(private_key, destination, str(send_amount))
            tx_id = result.get("txId") or result.get("txID") or result.get("transactionId")
            if not tx_id:
                raise RuntimeError(f"Tatum did not return a transaction id: {result}")
            await self.db.mark_withdrawal(withdrawal_id, status="BROADCASTED", tx_id=tx_id)
            return tx_id
        except Exception as exc:
            await self.db.mark_withdrawal(withdrawal_id, status="FAILED", error=str(exc))
            raise

    async def credit_deposit_from_tatum(self, user: dict, asset: str, tx_id: str, amount: Decimal, metadata: dict) -> bool:
        if amount <= 0:
            return False
        ok = await self.db.create_deposit_once(user["user_id"], asset, tx_id, amount, metadata)
        return ok

    async def scan_user_deposits(self, user: dict) -> list[tuple[str, Decimal, str]]:
        address = user.get("tron_address")
        if not address:
            return []
        last_ms = int(user.get("last_deposit_scan_ms") or 0)
        if last_ms <= 0:
            last_ms = int((time() - self.settings.deposit_lookback_hours * 3600) * 1000)
        results: list[tuple[str, Decimal, str]] = []

        trx_data = await self.tatum.tron_transactions(address, last_ms)
        for tx in self._items(trx_data):
            txid = self._txid(tx)
            amount = self._native_amount(tx)
            if txid and amount > 0:
                credited = await self.credit_deposit_from_tatum(user, "TRX", txid, amount, tx)
                if credited:
                    results.append(("TRX", amount, txid))

        if self.settings.usdt_trc20_contract:
            usdt_data = await self.tatum.trc20_transactions(address, self.settings.usdt_trc20_contract, last_ms)
            for tx in self._items(usdt_data):
                txid = self._txid(tx)
                amount = self._token_amount(tx)
                if txid and amount > 0:
                    credited = await self.credit_deposit_from_tatum(user, "USDT", txid, amount, tx)
                    if credited:
                        results.append(("USDT", amount, txid))
        return results

    @staticmethod
    def _items(data: dict | list) -> list[dict]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        for key in ("transactions", "data", "result"):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return []

    @staticmethod
    def _txid(tx: dict) -> str | None:
        return tx.get("txID") or tx.get("txId") or tx.get("hash") or tx.get("transactionHash")

    @staticmethod
    def _native_amount(tx: dict) -> Decimal:
        for key in ("amount", "value"):
            value = tx.get(key)
            if value is None:
                continue
            try:
                # Tatum's TRON transaction API returns native amount in base units for raw txs.
                n = Decimal(str(value))
                if n > Decimal("1000000"):
                    return n / Decimal("1000000")
                return n
            except Exception:
                continue
        return Decimal("0")

    @staticmethod
    def _token_amount(tx: dict) -> Decimal:
        for key in ("amount", "value", "tokenValue"):
            value = tx.get(key)
            if value is None:
                continue
            try:
                n = Decimal(str(value))
                # TRC20 transfer APIs normally expose token units; normalize 6-decimal USDT.
                if n >= Decimal("1000000"):
                    return n / Decimal("1000000")
                return n
            except Exception:
                continue
        return Decimal("0")
