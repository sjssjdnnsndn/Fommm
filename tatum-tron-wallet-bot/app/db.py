from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo import AsyncMongoClient
from bson.decimal128 import Decimal128


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def d128(value: Decimal | str | int | float) -> Decimal128:
    return Decimal128(str(value))


def to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value or "0"))


class Database:
    def __init__(self, uri: str, db_name: str):
        self.client = AsyncMongoClient(uri)
        self.db = self.client[db_name]
        self.users = self.db.users
        self.ledger = self.db.ledger
        self.deposits = self.db.deposits
        self.withdrawals = self.db.withdrawals
        self.pending = self.db.pending_actions
        self.settings = self.db.settings

    async def init(self) -> None:
        await self.db.command("ping")
        await self.users.create_index("username_normalized")
        await self.users.create_index("tron_address", unique=True, sparse=True)
        await self.deposits.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        await self.deposits.create_index("unique_key", unique=True)
        await self.withdrawals.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        await self.ledger.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        await self.pending.create_index("token", unique=True)

    async def close(self) -> None:
        await self.client.close()

    async def get_user(self, user_id: int) -> dict | None:
        return await self.users.find_one({"user_id": user_id})

    async def ensure_user(self, user_id: int, username: str | None, first_name: str | None) -> dict:
        normalized = (username or "").lstrip("@").lower() or None
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username,
                    "username_normalized": normalized,
                    "first_name": first_name,
                    "updated_at": utcnow(),
                },
                "$setOnInsert": {
                    "user_id": user_id,
                    "balances": {"USDT": d128("0"), "TRX": d128("0")},
                    "created_at": utcnow(),
                    "pin_hash": None,
                    "tron_index": None,
                    "tron_address": None,
                    "last_deposit_scan_ms": 0,
                },
            },
            upsert=True,
        )
        return (await self.get_user(user_id)) or {}

    async def next_tron_index(self, start: int) -> int:
        doc = await self.settings.find_one_and_update(
            {"_id": "tron_index"},
            {"$inc": {"value": 1}, "$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(doc["value"]) + start - 1

    async def set_wallet(self, user_id: int, index: int, address: str) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"tron_index": index, "tron_address": address, "updated_at": utcnow()}},
        )

    async def set_pin_hash(self, user_id: int, pin_hash: str) -> None:
        await self.users.update_one({"user_id": user_id}, {"$set": {"pin_hash": pin_hash}})

    async def find_user_by_identity(self, identity: str) -> dict | None:
        identity = identity.strip()
        if identity.startswith("@"):
            identity = identity[1:]
        if identity.isdigit():
            return await self.get_user(int(identity))
        return await self.users.find_one({"username_normalized": identity.lower()})

    async def get_settings(self) -> dict:
        doc = await self.settings.find_one({"_id": "bot"})
        return doc or {"tip_gif_file_id": None, "swap_rate": "20"}

    async def update_settings(self, values: dict) -> None:
        await self.settings.update_one({"_id": "bot"}, {"$set": values}, upsert=True)

    async def get_balances(self, user_id: int) -> dict[str, Decimal]:
        user = await self.get_user(user_id)
        balances = (user or {}).get("balances", {})
        return {"USDT": to_decimal(balances.get("USDT")), "TRX": to_decimal(balances.get("TRX"))}

    async def create_ledger_entry(self, user_id: int, asset: str, amount: Decimal, entry_type: str, ref: str, description: str, session=None) -> None:
        await self.ledger.insert_one(
            {
                "user_id": user_id,
                "asset": asset,
                "amount": d128(amount),
                "entry_type": entry_type,
                "reference": ref,
                "description": description,
                "created_at": utcnow(),
            },
            session=session,
        )

    async def internal_transfer(self, sender_id: int, receiver_id: int, asset: str, amount: Decimal, kind: str = "TIP") -> str:
        if sender_id == receiver_id:
            raise ValueError("You cannot send to yourself.")
        ref = f"{kind}-{uuid4().hex[:16]}"
        async with await self.client.start_session() as session:
            async with session.start_transaction():
                debit = await self.users.update_one(
                    {"user_id": sender_id, f"balances.{asset}": {"$gte": d128(amount)}},
                    {"$inc": {f"balances.{asset}": d128(-amount)}},
                    session=session,
                )
                if debit.modified_count != 1:
                    raise ValueError("Insufficient balance.")
                credit = await self.users.update_one(
                    {"user_id": receiver_id},
                    {"$inc": {f"balances.{asset}": d128(amount)}},
                    session=session,
                )
                if credit.modified_count != 1:
                    raise ValueError("Recipient is not registered with the bot.")
                await self.create_ledger_entry(sender_id, asset, -amount, kind, ref, f"{kind} sent", session)
                await self.create_ledger_entry(receiver_id, asset, amount, kind, ref, f"{kind} received", session)
        return ref

    async def swap(self, user_id: int, from_asset: str, to_asset: str, amount: Decimal, rate: Decimal) -> str:
        if amount <= 0 or rate <= 0:
            raise ValueError("Invalid swap amount/rate.")
        out_amount = amount * rate if from_asset == "USDT" else amount / rate
        out_amount = out_amount.quantize(Decimal("0.000001"))
        ref = f"SWAP-{uuid4().hex[:16]}"
        async with await self.client.start_session() as session:
            async with session.start_transaction():
                debit = await self.users.update_one(
                    {"user_id": user_id, f"balances.{from_asset}": {"$gte": d128(amount)}},
                    {"$inc": {f"balances.{from_asset}": d128(-amount), f"balances.{to_asset}": d128(out_amount)}},
                    session=session,
                )
                if debit.modified_count != 1:
                    raise ValueError("Insufficient balance.")
                await self.create_ledger_entry(user_id, from_asset, -amount, "SWAP", ref, f"Swap {from_asset} → {to_asset}", session)
                await self.create_ledger_entry(user_id, to_asset, out_amount, "SWAP", ref, f"Swap {from_asset} → {to_asset}", session)
        return ref

    async def prepare_withdrawal(
        self,
        user_id: int,
        asset: str,
        requested: Decimal,
        network_fee: Decimal,
        service_fee: Decimal,
        send_amount: Decimal,
        destination: str,
    ) -> str:
        ref = f"WD-{uuid4().hex[:16]}"
        total_debit = requested if send_amount < requested else requested + network_fee + service_fee
        # For full-balance mode the requested amount is the full balance, and fees are taken from it.
        if send_amount < requested:
            total_debit = requested
        else:
            total_debit = requested + network_fee + service_fee
        # The caller supplies the exact debit via requested in full-balance mode.
        doc = {
            "withdrawal_id": ref,
            "user_id": user_id,
            "asset": asset,
            "requested_amount": d128(requested),
            "network_fee": d128(network_fee),
            "service_fee": d128(service_fee),
            "send_amount": d128(send_amount),
            "total_debit": d128(total_debit),
            "destination": destination,
            "status": "QUEUED",
            "created_at": utcnow(),
        }
        async with await self.client.start_session() as session:
            async with session.start_transaction():
                result = await self.users.update_one(
                    {"user_id": user_id, f"balances.{asset}": {"$gte": d128(total_debit)}},
                    {"$inc": {f"balances.{asset}": d128(-total_debit)}},
                    session=session,
                )
                if result.modified_count != 1:
                    raise ValueError("Insufficient balance after fees.")
                await self.withdrawals.insert_one(doc, session=session)
                await self.create_ledger_entry(user_id, asset, -total_debit, "WITHDRAWAL", ref, "Withdrawal debit", session)
        return ref

    async def mark_withdrawal(self, withdrawal_id: str, **values) -> None:
        values["updated_at"] = utcnow()
        await self.withdrawals.update_one({"withdrawal_id": withdrawal_id}, {"$set": values})

    async def get_withdrawal(self, withdrawal_id: str) -> dict | None:
        return await self.withdrawals.find_one({"withdrawal_id": withdrawal_id})

    async def recent_history(self, user_id: int, limit: int = 10) -> list[dict]:
        cur = self.ledger.find({"user_id": user_id}).sort("created_at", DESCENDING).limit(limit)
        return await cur.to_list(length=limit)

    async def create_deposit_once(self, user_id: int, asset: str, tx_id: str, amount: Decimal, metadata: dict) -> bool:
        unique_key = f"{user_id}:{asset}:{tx_id}"
        doc = {
            "unique_key": unique_key,
            "user_id": user_id,
            "asset": asset,
            "tx_id": tx_id,
            "amount": d128(amount),
            "metadata": metadata,
            "status": "CREDITED",
            "created_at": utcnow(),
        }
        try:
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    await self.deposits.insert_one(doc, session=session)
                    await self.users.update_one({"user_id": user_id}, {"$inc": {f"balances.{asset}": d128(amount)}}, session=session)
                    await self.create_ledger_entry(user_id, asset, amount, "DEPOSIT", tx_id, f"On-chain {asset} deposit", session)
            return True
        except DuplicateKeyError:
            return False

    async def set_last_scan(self, user_id: int, timestamp_ms: int) -> None:
        await self.users.update_one({"user_id": user_id}, {"$set": {"last_deposit_scan_ms": timestamp_ms}})

    async def get_users_for_scan(self, limit: int) -> list[dict]:
        cur = self.users.find({"tron_address": {"$ne": None}}).sort("last_deposit_scan_ms", ASCENDING).limit(limit)
        return await cur.to_list(length=limit)

    async def count_users(self) -> int:
        return await self.users.count_documents({})

    async def count_withdrawals(self, status: str | None = None) -> int:
        q = {} if status is None else {"status": status}
        return await self.withdrawals.count_documents(q)
