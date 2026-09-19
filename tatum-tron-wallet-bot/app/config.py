from __future__ import annotations

from decimal import Decimal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    mongodb_uri: str = Field(alias="MONGODB_URI")
    mongodb_db: str = Field(default="tatum_tron_wallet", alias="MONGODB_DB")

    tatum_api_key: str = Field(alias="TATUM_API_KEY")
    tatum_base_url: str = Field(default="https://api.tatum.io", alias="TATUM_BASE_URL")
    tron_network: str = Field(default="shasta", alias="TRON_NETWORK")
    tron_mnemonic: str = Field(default="", alias="TRON_MNEMONIC")
    tron_xpub: str = Field(default="", alias="TRON_XPUB")
    treasury_index: int = Field(default=0, alias="TREASURY_INDEX")
    user_index_start: int = Field(default=1, alias="USER_INDEX_START")

    usdt_trc20_contract: str = Field(
        # The well-known TRON USDT contract is mainnet-only. Keep this empty
        # by default so testnet cannot query or withdraw against it by accident.
        default="",
        alias="USDT_TRC20_CONTRACT",
    )
    usdt_decimals: int = Field(default=6, alias="USDT_DECIMALS")

    # Free-plan-friendly polling instead of unlimited webhooks.
    deposit_scan_interval_seconds: int = Field(default=900, alias="DEPOSIT_SCAN_INTERVAL_SECONDS")
    deposit_scan_batch: int = Field(default=10, alias="DEPOSIT_SCAN_BATCH")
    deposit_lookback_hours: int = Field(default=24, alias="DEPOSIT_LOOKBACK_HOURS")

    service_fee_usd: Decimal = Field(default=Decimal("0.50"), alias="SERVICE_FEE_USD")
    trx_usdt_rate: Decimal = Field(default=Decimal("0.20"), alias="TRX_USDT_RATE")
    usdt_network_fee_estimate: Decimal = Field(default=Decimal("0.35"), alias="USDT_NETWORK_FEE_ESTIMATE")
    trx_network_fee_estimate: Decimal = Field(default=Decimal("1.00"), alias="TRX_NETWORK_FEE_ESTIMATE")
    fee_reserve_multiplier: Decimal = Field(default=Decimal("1.10"), alias="FEE_RESERVE_MULTIPLIER")

    # Direct private-key signing is intentionally off by default on mainnet.
    allow_mainnet_private_key_signing: bool = Field(
        default=False, alias="ALLOW_MAINNET_PRIVATE_KEY_SIGNING"
    )

    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    bot_display_name: str = Field(default="Crypto Wallet", alias="BOT_DISPLAY_NAME")
    add_to_group_url: str = Field(default="", alias="ADD_TO_GROUP_URL")

    def admins(self) -> set[int]:
        out: set[int] = set()
        for item in self.admin_ids.split(","):
            item = item.strip()
            if item.isdigit():
                out.add(int(item))
        return out

    @property
    def is_mainnet(self) -> bool:
        return self.tron_network.lower() == "mainnet"


settings = Settings()