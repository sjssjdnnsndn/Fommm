from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
import re

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from .config import Settings
from .db import Database, to_decimal
from .keyboards import admin_keyboard, assets_keyboard, confirm_keyboard, main_menu, pin_keyboard, swap_keyboard
from .services import WalletService
from .utils import asset_emoji, asset_label, fmt_amount, mention_html, parse_amount_token, parse_tip_text, safe_html


class BotHandlers:
    def __init__(self, db: Database, wallet: WalletService, settings: Settings):
        self.db = db
        self.wallet = wallet
        self.settings = settings

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        await self.db.ensure_user(user.id, user.username, user.first_name)
        balances = await self.db.get_balances(user.id)
        text = (
            f"<b>👛 {safe_html(self.settings.bot_display_name)}</b>\n\n"
            f"🪪 ID: <code>{user.id}</code>\n"
            f"💵 USDT: <b>{fmt_amount(balances['USDT'], 'USDT')}</b>\n"
            f"💎 TRX: <b>{fmt_amount(balances['TRX'], 'TRX')}</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Internal tips/swaps are instant and do not touch the blockchain."
        )
        if update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu(self.settings.add_to_group_url))
        else:
            await update.effective_message.edit_text(text, parse_mode="HTML", reply_markup=main_menu(self.settings.add_to_group_url))

    async def menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        action = q.data.split(":", 1)[1]
        if action == "deposit":
            await self.begin_deposit(q, context)
        elif action == "withdraw":
            await self.begin_withdraw(q, context)
        elif action in ("tip", "transfer"):
            await q.message.reply_text("Use: <code>/tip @username 500u</code> or reply to a user's message with <code>/tip 500u</code>.", parse_mode="HTML")
        elif action == "receive":
            await self.receive(q, context)
        elif action == "swap":
            await self.begin_swap(q, context)
        elif action == "profile":
            await self.profile(q, context)
        elif action == "history":
            await self.history(q, context)

    @staticmethod
    def _target_user_message(target):
        # Works for both Update and CallbackQuery.
        if hasattr(target, "effective_user"):
            return target.effective_user, target.effective_message
        return target.from_user, target.message

    async def begin_deposit(self, target, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, message = self._target_user_message(target)
        db_user = await self.db.get_user(user.id)
        if not db_user.get("pin_hash"):
            context.user_data.clear()
            context.user_data["state"] = "pin_set"
            context.user_data["pin_mode"] = "deposit"
            await message.reply_text("🔐 Set a 5-digit payment PIN first.\n\nThis PIN is required for withdrawals and protects wallet actions.", reply_markup=pin_keyboard())
            return
        try:
            address = await self.wallet.ensure_tron_address(user.id)
        except Exception as exc:
            await message.reply_text(f"❌ Deposit address setup failed.\n\n{safe_html(str(exc))}", parse_mode="HTML")
            return
        await message.reply_text(
            "<b>📥 Deposit</b>\n\n"
            f"TRON address:\n<code>{address}</code>\n\n"
            "Supported assets now:\n• USDT (TRC20)\n• TRX\n\n"
            "⚠️ Send only supported assets on the TRON network.\n\n"
            "After the transaction is confirmed, press /wallet to refresh your balance.",
            parse_mode="HTML",
        )

    async def begin_withdraw(self, target, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, message = self._target_user_message(target)
        db_user = await self.db.get_user(user.id)
        if not db_user.get("pin_hash"):
            context.user_data.clear()
            context.user_data["state"] = "pin_set"
            context.user_data["pin_mode"] = "withdraw"
            await message.reply_text("🔐 Set a 5-digit payment PIN first.", reply_markup=pin_keyboard())
            return
        await message.reply_text("💸 Select the asset to withdraw:", reply_markup=assets_keyboard("withdraw"))

    async def asset_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        kind, asset = q.data.split(":", 1)
        if kind == "withdraw":
            context.user_data["state"] = "withdraw_address"
            context.user_data["withdraw_asset"] = asset
            await q.message.reply_text(f"Send the destination TRON address for {asset_label(asset)}.")

    async def receive(self, q, context) -> None:
        user = await self.db.get_user(q.from_user.id)
        await q.message.reply_text(
            "<b>📥 Receive internally</b>\n\n"
            f"Username: {('@' + user['username']) if user.get('username') else 'not set'}\n"
            f"User ID: <code>{q.from_user.id}</code>\n\n"
            "Another registered user can tip you with:\n"
            "<code>/tip @username 500u</code>\n"
            "or\n"
            "<code>/tip 500T</code> as a reply to your message.",
            parse_mode="HTML",
        )

    async def profile(self, q, context) -> None:
        user = await self.db.get_user(q.from_user.id)
        await q.message.reply_text(
            "<b>👤 Personal Center</b>\n\n"
            f"Name: {safe_html(user.get('first_name') or '')}\n"
            f"ID: <code>{q.from_user.id}</code>\n"
            f"Username: {safe_html('@' + user['username']) if user.get('username') else '—'}\n"
            f"Payment PIN: {'✅ Set' if user.get('pin_hash') else '❌ Not set'}",
            parse_mode="HTML",
        )

    async def history(self, target, context) -> None:
        user, message = self._target_user_message(target)
        items = await self.db.recent_history(user.id, 12)
        if not items:
            await message.reply_text("📜 No transactions yet.")
            return
        lines = ["<b>📜 Recent History</b>"]
        for item in items:
            amount = to_decimal(item["amount"])
            asset = item["asset"]
            sign = "+" if amount >= 0 else ""
            lines.append(f"{item['entry_type']}: {sign}{fmt_amount(amount, asset)} {asset} · <code>{item['reference']}</code>")
        await message.reply_text("\n".join(lines), parse_mode="HTML")

    async def begin_swap(self, target, context) -> None:
        _user, message = self._target_user_message(target)
        await message.reply_text("🔄 Select swap direction:", reply_markup=swap_keyboard())

    async def swap_direction(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        _, from_asset, to_asset = q.data.split(":")
        context.user_data["state"] = "swap_amount"
        context.user_data["swap_from"] = from_asset
        context.user_data["swap_to"] = to_asset
        settings_doc = await self.db.get_settings()
        rate = Decimal(str(settings_doc.get("swap_rate", "20")))
        if from_asset == "TRX":
            rate_text = f"1 TRX = {fmt_amount(Decimal('1') / rate, 'USDT')} USDT"
        else:
            rate_text = f"1 USDT = {fmt_amount(rate, 'TRX')} TRX"
        await q.message.reply_text(f"Current rate: <b>{rate_text}</b>\n\nSend the amount to swap.", parse_mode="HTML")

    async def handle_pin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        state = context.user_data.get("state")
        if not state or not state.startswith("pin_"):
            return
        current = context.user_data.get("pin_buffer", "")
        if q.data == "pin:cancel":
            context.user_data.clear()
            await q.message.reply_text("❌ Cancelled.")
            return
        if q.data == "pin:back":
            current = current[:-1]
        elif q.data.startswith("pin:"):
            digit = q.data.split(":", 1)[1]
            if len(current) < 5:
                current += digit
        context.user_data["pin_buffer"] = current
        masked = "•" * len(current)
        mode = context.user_data.get("pin_mode")
        if state == "pin_set":
            if len(current) == 5:
                context.user_data["state"] = "pin_confirm"
                context.user_data["pin_first"] = current
                context.user_data["pin_buffer"] = ""
                await q.message.edit_text("🔐 Confirm your 5-digit PIN.", reply_markup=pin_keyboard())
            else:
                await q.message.edit_text(f"🔐 Set a 5-digit PIN\n\n{masked}", reply_markup=pin_keyboard())
        elif state == "pin_confirm":
            if len(current) == 5:
                first = context.user_data.get("pin_first", "")
                if current != first:
                    context.user_data["pin_buffer"] = ""
                    await q.message.edit_text("❌ PINs do not match. Try again.", reply_markup=pin_keyboard())
                    return
                await self.wallet.set_pin(q.from_user.id, current)
                context.user_data["state"] = None
                context.user_data.pop("pin_first", None)
                context.user_data.pop("pin_buffer", None)
                await q.message.edit_text("✅ Payment PIN set successfully.")
                if mode == "withdraw":
                    await q.message.reply_text("💸 Now select the withdrawal asset:", reply_markup=assets_keyboard("withdraw"))
                elif mode == "deposit":
                    await self.begin_deposit(q, context)
        elif state == "pin_withdraw":
            if len(current) == 5:
                ok = await self.wallet.verify_pin(q.from_user.id, current)
                if not ok:
                    context.user_data["pin_buffer"] = ""
                    await q.message.edit_text("❌ Wrong PIN. Try again.", reply_markup=pin_keyboard())
                    return
                wd_id = context.user_data.get("pending_withdrawal_id")
                context.user_data["state"] = None
                context.user_data.pop("pin_buffer", None)
                await q.message.edit_text("✅ PIN verified. Broadcasting withdrawal…")
                try:
                    txid = await self.wallet.perform_withdrawal(wd_id)
                    await q.message.reply_text(f"✅ Withdrawal broadcasted.\n\nTXID:\n<code>{txid}</code>", parse_mode="HTML")
                except Exception as exc:
                    await q.message.reply_text(f"❌ Withdrawal failed or requires KMS.\n\n{safe_html(str(exc))}", parse_mode="HTML")

    async def confirm_withdraw(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if not q.data.startswith("confirmwd:"):
            return
        payload = q.data.split(":", 1)[1]
        parts = payload.split("|")
        wd_id = parts[0]
        context.user_data["state"] = "pin_withdraw"
        context.user_data["pending_withdrawal_id"] = wd_id
        context.user_data["pin_buffer"] = ""
        await q.message.edit_text("🔐 Enter your 5-digit payment PIN.", reply_markup=pin_keyboard())

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        context.user_data.clear()
        try:
            await q.message.edit_text("❌ Cancelled.")
        except Exception:
            await q.message.reply_text("❌ Cancelled.")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return
        text = update.message.text.strip()
        user = update.effective_user
        await self.db.ensure_user(user.id, user.username, user.first_name)
        state = context.user_data.get("state")

        # Plain-text tip command in groups/DMs. Slash command is handled separately too.
        if state is None and (text.lower().startswith("tip ") or text.lower().startswith("/tip ")):
            await self.tip_command(update, context)
            return

        if state == "withdraw_address":
            asset = context.user_data.get("withdraw_asset")
            if not self._looks_like_tron_address(text):
                await update.message.reply_text("❌ That does not look like a valid TRON Base58 address. Try again.")
                return
            context.user_data["withdraw_address"] = text
            context.user_data["state"] = "withdraw_amount"
            await update.message.reply_text(f"Enter the amount of {asset_label(asset)} to withdraw.")
            return

        if state == "withdraw_amount":
            asset = context.user_data.get("withdraw_asset")
            try:
                amount, parsed_asset = parse_amount_token(text)
                if parsed_asset != asset:
                    raise ValueError(f"Use an amount ending with {'u' if asset == 'USDT' else 'T'}.")
                quote = await self.wallet.fee_quote(user.id, asset, amount)
            except Exception as exc:
                await update.message.reply_text(f"❌ {safe_html(str(exc))}", parse_mode="HTML")
                return
            wd_id = await self.db.prepare_withdrawal(
                user.id, asset, quote.total_debit if quote.full_balance_mode else amount,
                quote.network_fee, quote.service_fee, quote.send_amount, context.user_data["withdraw_address"]
            )
            context.user_data["pending_withdrawal_id"] = wd_id
            context.user_data["state"] = "withdraw_confirm"
            await update.message.reply_text(
                "<b>💸 Withdrawal Confirmation</b>\n\n"
                f"Asset: <b>{asset_label(asset)}</b>\n"
                f"Requested: <b>{fmt_amount(amount, asset)} {asset}</b>\n"
                f"Network fee: <b>{fmt_amount(quote.network_fee, asset)} {asset}</b>\n"
                f"Service fee: <b>{fmt_amount(quote.service_fee, asset)} {asset}</b>\n"
                f"You receive: <b>{fmt_amount(quote.send_amount, asset)} {asset}</b>\n\n"
                f"Destination:\n<code>{safe_html(context.user_data['withdraw_address'])}</code>\n\n"
                "<i>Full-balance withdrawals deduct both fees from the amount being withdrawn.</i>",
                parse_mode="HTML",
                reply_markup=confirm_keyboard(f"confirmwd:{wd_id}")
            )
            return

        if state == "swap_amount":
            from_asset = context.user_data.get("swap_from")
            to_asset = context.user_data.get("swap_to")
            try:
                amount = Decimal(text)
                if amount <= 0:
                    raise ValueError("Amount must be positive.")
                balances = await self.db.get_balances(user.id)
                if amount > balances[from_asset]:
                    raise ValueError("Insufficient balance.")
                settings_doc = await self.db.get_settings()
                base_rate = Decimal(str(settings_doc.get("swap_rate", "20")))
                rate = base_rate if from_asset == "USDT" else Decimal("1") / base_rate
                out = (amount * rate).quantize(Decimal("0.000001"))
            except Exception as exc:
                await update.message.reply_text(f"❌ {safe_html(str(exc))}", parse_mode="HTML")
                return
            context.user_data["swap_amount"] = str(amount)
            context.user_data["swap_out"] = str(out)
            context.user_data["state"] = "swap_confirm"
            await update.message.reply_text(
                f"<b>🔄 Confirm Swap</b>\n\n{fmt_amount(amount, from_asset)} {from_asset} → <b>{fmt_amount(out, to_asset)} {to_asset}</b>",
                parse_mode="HTML",
                reply_markup=confirm_keyboard("confirmswap")
            )
            return

        if state == "admin_rate":
            if user.id not in self.settings.admins():
                context.user_data.clear()
                return
            try:
                rate = Decimal(text)
                if rate <= 0:
                    raise ValueError
                await self.db.update_settings({"swap_rate": str(rate)})
                context.user_data.clear()
                await update.message.reply_text(f"✅ Swap rate saved: 1 USDT = {fmt_amount(rate, 'TRX')} TRX")
            except Exception:
                await update.message.reply_text("❌ Enter a positive number, e.g. 20.5")
            return

        if text.startswith("/wallet") or text.lower() == "wallet":
            await self.start(update, context)
            return
        if text.lower() == "cancel":
            context.user_data.clear()
            await update.message.reply_text("❌ Cancelled.")

    async def confirm_swap(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if q.data != "confirmswap":
            return
        try:
            from_asset = context.user_data["swap_from"]
            to_asset = context.user_data["swap_to"]
            amount = Decimal(context.user_data["swap_amount"])
            settings_doc = await self.db.get_settings()
            base_rate = Decimal(str(settings_doc.get("swap_rate", "20")))
            rate = base_rate if from_asset == "USDT" else Decimal("1") / base_rate
            out = (amount * rate).quantize(Decimal("0.000001"))
            await self.db.swap(q.from_user.id, from_asset, to_asset, amount, rate)
            context.user_data.clear()
            await q.message.edit_text(f"✅ Swap completed.\n\n{fmt_amount(amount, from_asset)} {from_asset} → {fmt_amount(out, to_asset)} {to_asset}")
        except Exception as exc:
            context.user_data.clear()
            await q.message.edit_text(f"❌ Swap failed: {safe_html(str(exc))}", parse_mode="HTML")

    async def tip_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        parsed = parse_tip_text(update.message.text)
        reply_target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
        if not parsed:
            # Reply-style tip: /tip 500u
            raw = update.message.text.strip()
            if reply_target and re.fullmatch(r"(?:/)?tip\s+[0-9]+(?:\.[0-9]+)?[uUtT]", raw, re.I):
                amount_token = raw.split()[-1]
                amount, asset = parse_amount_token(amount_token)
                target_id = reply_target.id
                target_username = reply_target.username
            else:
                await update.message.reply_text("Use /tip @username 500u, /tip 123456789 500T, or reply to a message with /tip 500u.")
                return
        else:
            target_identity, amount, asset = parsed
            recipient = await self.db.find_user_by_identity(target_identity)
            if not recipient:
                await update.message.reply_text("❌ Recipient is not registered with this bot.")
                return
            target_id = recipient["user_id"]
            target_username = recipient.get("username")

        if target_id == update.effective_user.id:
            await update.message.reply_text("❌ You cannot tip yourself.")
            return
        sender_balance = (await self.db.get_balances(update.effective_user.id))[asset]
        if amount > sender_balance:
            await update.message.reply_text(f"❌ Insufficient {asset} balance.")
            return
        token = f"tip-{update.effective_user.id}-{target_id}-{asset}-{amount}-{int(update.message.message_id)}"
        context.user_data["pending_tip"] = {"token": token, "target_id": target_id, "target_username": target_username, "amount": str(amount), "asset": asset}
        await update.message.reply_text(
            "<b>🎁 Confirm Tip</b>\n\n"
            f"To: {mention_html(target_id, target_username)}\n"
            f"Amount: <b>{fmt_amount(amount, asset)} {asset}</b>\n"
            "Fee: <b>0</b>\n\n"
            f"Your balance after tip: <b>{fmt_amount(sender_balance - amount, asset)} {asset}</b>\n\n"
            "Send this tip?",
            parse_mode="HTML",
            reply_markup=confirm_keyboard("confirmtip", "canceltip")
        )

    async def confirm_tip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        pending = context.user_data.get("pending_tip")
        if not pending:
            await q.message.edit_text("❌ Tip session expired.")
            return
        try:
            amount = Decimal(pending["amount"])
            asset = pending["asset"]
            ref = await self.db.internal_transfer(q.from_user.id, pending["target_id"], asset, amount, "TIP")
            context.user_data.clear()
            settings_doc = await self.db.get_settings()
            gif_id = settings_doc.get("tip_gif_file_id")
            caption = (
                f"🎁 <b>{mention_html(q.from_user.id, q.from_user.username)}</b> sent a tip\n\n"
                f"{asset_emoji(asset)} <b>{fmt_amount(amount, asset)} {asset}</b>\n"
                f"👤 To: {mention_html(pending['target_id'], pending.get('target_username'))}\n\n"
                "✅ Internal transfer completed"
            )
            if gif_id:
                await q.message.delete()
                await q.message.chat.send_animation(gif_id, caption=caption, parse_mode="HTML")
            else:
                await q.message.edit_text(caption, parse_mode="HTML")
        except Exception as exc:
            await q.message.edit_text(f"❌ Tip failed: {safe_html(str(exc))}", parse_mode="HTML")

    async def admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user.id not in self.settings.admins():
            await update.message.reply_text("⛔ Admin only.")
            return
        await update.message.reply_text("⚙️ Admin Panel", reply_markup=admin_keyboard())

    async def admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if q.from_user.id not in self.settings.admins():
            await q.message.reply_text("⛔ Admin only.")
            return
        action = q.data.split(":", 1)[1]
        if action == "gif":
            context.user_data["state"] = "admin_gif"
            await q.message.reply_text("🎬 Send the GIF/animation you want to use above tip messages.")
        elif action == "rate":
            context.user_data["state"] = "admin_rate"
            await q.message.reply_text("Enter the swap rate as TRX per 1 USDT. Example: 20.5")
        elif action == "stats":
            users = await self.db.count_users()
            queued = await self.db.count_withdrawals("QUEUED")
            broad = await self.db.count_withdrawals("BROADCASTED")
            await q.message.reply_text(f"📊 Users: {users}\n⏳ Queued withdrawals: {queued}\n✅ Broadcasted withdrawals: {broad}")

    async def animation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user.id not in self.settings.admins():
            return
        if context.user_data.get("state") != "admin_gif":
            return
        file_id = update.message.animation.file_id
        await self.db.update_settings({"tip_gif_file_id": file_id})
        context.user_data.clear()
        await update.message.reply_text("✅ Tip GIF updated.\n\nThe next tip confirmation will use this animation.")

    async def deposit_scan_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        users = await self.db.get_users_for_scan(self.settings.deposit_scan_batch)
        if not users:
            return
        now_ms = int(__import__("time").time() * 1000)
        for user in users:
            try:
                deposits = await self.wallet.scan_user_deposits(user)
                for asset, amount, txid in deposits:
                    try:
                        await context.bot.send_message(
                            user["user_id"],
                            f"✅ Deposit detected\n\n{fmt_amount(amount, asset)} {asset}\nTXID: <code>{txid}</code>",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
                await self.db.set_last_scan(user["user_id"], now_ms)
                await asyncio.sleep(0.35)  # stay under the free-plan 3 RPS limit.
            except Exception as exc:
                # Continue scanning the batch even if one address fails.
                print(f"deposit scan error user={user.get('user_id')}: {exc}")

    @staticmethod
    def _looks_like_tron_address(value: str) -> bool:
        return bool(re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]{33}", value.strip()))
