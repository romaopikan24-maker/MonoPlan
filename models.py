from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict


class MccCategoryMapper:
    """Класифікатор витрат за MCC-кодами Monobank."""

    _MCC_MAP: Dict[int, str] = {
        5411: "Продукти та супермаркети",
        5499: "Продукти та супермаркети",
        5812: "Кафе та ресторани",
        5814: "Фастфуд",
        4121: "Таксі",
        4111: "Громадський транспорт",
        5912: "Аптеки та медицина",
        5541: "АЗС та авто",
        4814: "Зв'язок та інтернет",
        7832: "Розваги та кіно",
        5691: "Одяг та взуття",
    }

    @classmethod
    def get_category(cls, mcc: int) -> str:
        return cls._MCC_MAP.get(mcc, f"Інше (MCC {mcc})")


@dataclass
class CurrencyRate:
    """Картковий курс валюти Monobank до гривні."""

    code: str
    buy: float
    sell: float


@dataclass
class ManualSavingEntry:
    entry_id: str
    category_type: str  # "other_bank" або "cash"
    title: str
    amount: float
    color_hex: str = ""

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "category_type": self.category_type,
            "title": self.title,
            "amount": self.amount,
            "color_hex": self.color_hex,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ManualSavingEntry":
        return cls(
            entry_id=str(data.get("entry_id", "")),
            category_type=str(data.get("category_type", "other_bank")),
            title=str(data.get("title", "")),
            amount=float(data.get("amount", 0.0)),
            color_hex=str(data.get("color_hex", "")),
        )

    @property
    def category_label(self) -> str:
        return "Інші банки" if self.category_type == "other_bank" else "Готівка"


@dataclass
class Transaction:
    """Модель банківської транзакції."""

    tx_id: str
    timestamp: datetime
    description: str
    amount: float
    mcc: int
    category: str

    @property
    def is_expense(self) -> bool:
        return self.amount < 0

    def to_dict(self) -> dict:
        return {
            "tx_id": self.tx_id,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "amount": self.amount,
            "mcc": self.mcc,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        return cls(
            tx_id=data["tx_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            description=data["description"],
            amount=float(data["amount"]),
            mcc=int(data["mcc"]),
            category=data["category"],
        )


class FinancialItem(ABC):
    """Абстрактний базовий клас фінансових об'єктів."""

    def __init__(self, item_id: str, title: str, currency: str = "UAH"):
        self._id = item_id
        self._title = title
        self._currency = currency

    @property
    def item_id(self) -> str:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @property
    def currency(self) -> str:
        return self._currency

    @abstractmethod
    def get_remaining_amount(self) -> float:
        pass


class SavingsJar(FinancialItem):
    """Накопичувальна 'Банка' (Monobank або створена користувачем вручну)."""

    def __init__(
        self,
        jar_id: str,
        title: str,
        current_balance: float,
        goal_amount: float,
        currency: str = "UAH",
        is_custom: bool = False,
    ):
        super().__init__(jar_id, title, currency)
        self._current_balance = max(0.0, current_balance)
        self._goal_amount = max(0.0, goal_amount)
        self._is_custom = bool(is_custom)

    @property
    def current_balance(self) -> float:
        return self._current_balance

    @property
    def goal_amount(self) -> float:
        return self._goal_amount

    @property
    def is_custom(self) -> bool:
        return self._is_custom

    def adjust_balance(self, delta: float) -> None:
        """Поповнює або зменшує накопичену суму власної банки."""
        self._current_balance = max(0.0, self._current_balance + delta)

    def get_remaining_amount(self) -> float:
        if self._goal_amount <= 0:
            return 0.0
        return max(0.0, self._goal_amount - self._current_balance)

    def get_progress_percent(self) -> int:
        if self._goal_amount <= 0:
            return 100
        return int(min(100, (self._current_balance / self._goal_amount) * 100))

    def to_dict(self) -> dict:
        return {
            "jar_id": self._id,
            "title": self._title,
            "current_balance": self._current_balance,
            "goal_amount": self._goal_amount,
            "currency": self._currency,
            "is_custom": self._is_custom,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SavingsJar":
        return cls(
            jar_id=data["jar_id"],
            title=data["title"],
            current_balance=float(data["current_balance"]),
            goal_amount=float(data["goal_amount"]),
            currency=data.get("currency", "UAH"),
            is_custom=bool(data.get("is_custom", False)),
        )


class CreditLiability(FinancialItem):
    """Кредитне зобов'язання або розстрочка."""

    def __init__(
        self,
        liability_id: str,
        title: str,
        credit_limit: float,
        used_amount: float,
        annual_rate: float = 37.2,
        currency: str = "UAH",
    ):
        super().__init__(liability_id, title, currency)
        self._credit_limit = credit_limit
        self._used_amount = max(0.0, used_amount)
        self._annual_rate = annual_rate

    @property
    def credit_limit(self) -> float:
        return self._credit_limit

    @property
    def annual_rate(self) -> float:
        return self._annual_rate

    def get_remaining_amount(self) -> float:
        return self._used_amount

    def to_dict(self) -> dict:
        return {
            "liability_id": self._id,
            "title": self._title,
            "credit_limit": self._credit_limit,
            "used_amount": self._used_amount,
            "annual_rate": self._annual_rate,
            "currency": self._currency,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CreditLiability":
        return cls(
            liability_id=data["liability_id"],
            title=data["title"],
            credit_limit=float(data["credit_limit"]),
            used_amount=float(data["used_amount"]),
            annual_rate=float(data.get("annual_rate", 37.2)),
            currency=data.get("currency", "UAH"),
        )