from __future__ import annotations

from typing import Any
import httpx


class TatumError(RuntimeError):
    pass


class TatumClient:
    def __init__(self, api_key: str, base_url: str = "https://api.tatum.io"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"x-api-key": api_key, "accept": "application/json", "content-type": "application/json"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = await self.client.request(method, f"{self.base_url}{path}", **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise TatumError(f"Tatum {resp.status_code}: {body}")
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception as exc:
            raise TatumError(f"Unexpected Tatum response: {resp.text[:500]}") from exc

    async def generate_tron_wallet(self, mnemonic: str | None = None) -> dict:
        params = {"mnemonic": mnemonic} if mnemonic else None
        return await self._request("GET", "/v3/tron/wallet", params=params)

    async def derive_address(self, xpub: str, index: int) -> str:
        data = await self._request("GET", f"/v3/tron/address/{xpub}/{index}")
        if isinstance(data, dict):
            return data.get("address") or data.get("addressBase58") or data.get("result")
        return str(data)

    async def derive_private_key(self, mnemonic: str, index: int) -> str:
        data = await self._request("POST", "/v3/tron/wallet/priv", json={"mnemonic": mnemonic, "index": index})
        return data.get("key") or data.get("privateKey") or data.get("private_key")

    async def tron_transactions(self, address: str, min_timestamp: int = 0) -> dict:
        params = {
            "onlyConfirmed": "true",
            "onlyTo": "true",
            "orderBy": "block_timestamp,desc",
            "minTimestamp": str(min_timestamp),
        }
        return await self._request("GET", f"/v3/tron/transaction/account/{address}", params=params)

    async def trc20_transactions(self, address: str, contract: str, min_timestamp: int = 0) -> dict:
        params = {
            "onlyConfirmed": "true",
            "onlyTo": "true",
            "orderBy": "block_timestamp,desc",
            "minTimestamp": str(min_timestamp),
            "contractAddress": contract,
        }
        return await self._request("GET", f"/v3/tron/transaction/account/{address}/trc20", params=params)

    async def send_trx(self, from_private_key: str, to: str, amount: str) -> dict:
        return await self._request(
            "POST",
            "/v3/tron/transaction",
            json={"fromPrivateKey": from_private_key, "to": to, "amount": amount},
        )

    async def send_trc20(self, from_private_key: str, to: str, token_address: str, amount: str, fee_limit_trx: float) -> dict:
        return await self._request(
            "POST",
            "/v3/tron/trc20/transaction",
            json={
                "fromPrivateKey": from_private_key,
                "to": to,
                "tokenAddress": token_address,
                "amount": amount,
                "feeLimit": fee_limit_trx,
            },
        )
