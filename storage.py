import base64
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import List, Optional


@dataclass
class UserSession:
    """Модель збереженої сесії користувача."""

    client_name: str
    token: str
    strategy_index: int = 0
    gemini_api_key: str = ""
    cached_jars: List[dict] = None
    cached_liabilities: List[dict] = None
    cached_transactions: List[dict] = None
    jar_order: List[str] = None
    manual_savings: List[dict] = None
    cached_account_balance: float = 0.0

    def __post_init__(self):
        if self.cached_jars is None:
            self.cached_jars = []
        if self.cached_liabilities is None:
            self.cached_liabilities = []
        if self.cached_transactions is None:
            self.cached_transactions = []
        if self.jar_order is None:
            self.jar_order = []
        if self.manual_savings is None:
            self.manual_savings = []


class UserSessionRepository:
    """Репозиторій для збереження профілю, токенів, порядку банок та накопичень у JSON."""

    def __init__(self, file_name: str = "monoplan_session.json"):
        self._file_path = Path(__file__).parent / file_name

    @staticmethod
    def _encode_secret(raw: str) -> str:
        if not raw:
            return ""
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    @staticmethod
    def _decode_secret(encoded: str) -> str:
        if not encoded:
            return ""
        try:
            return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
        except Exception:
            return ""

    def save_session(self, session: UserSession) -> None:
        payload = asdict(session)
        payload["token"] = self._encode_secret(session.token)
        payload["gemini_api_key"] = self._encode_secret(session.gemini_api_key)
        self._file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_session(self) -> Optional[UserSession]:
        if not self._file_path.exists():
            return None
        try:
            raw = json.loads(self._file_path.read_text(encoding="utf-8"))
            decoded_token = self._decode_secret(raw.get("token", ""))
            decoded_ai_key = self._decode_secret(raw.get("gemini_api_key", ""))
            cached_jars = raw.get("cached_jars", [])
            jar_order = raw.get("jar_order", [])
            manual_savings = raw.get("manual_savings", [])
            if (
                not decoded_token
                and not decoded_ai_key
                and not cached_jars
                and not jar_order
                and not manual_savings
            ):
                return None
            return UserSession(
                client_name=raw.get("client_name", "Клієнт Monobank"),
                token=decoded_token,
                strategy_index=int(raw.get("strategy_index", 0)),
                gemini_api_key=decoded_ai_key,
                cached_jars=cached_jars,
                cached_liabilities=raw.get("cached_liabilities", []),
                cached_transactions=raw.get("cached_transactions", []),
                jar_order=jar_order,
                manual_savings=manual_savings,
                cached_account_balance=float(raw.get("cached_account_balance", 0.0)),
            )
        except Exception:
            return None

    def clear_session(self) -> None:
        if self._file_path.exists():
            self._file_path.unlink()