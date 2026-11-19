from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import json
from typing import List, Optional
import urllib.error
import urllib.request

from models import (
    CreditLiability,
    CurrencyRate,
    MccCategoryMapper,
    SavingsJar,
    Transaction,
)


class IFinancialDataSource(ABC):
    """Інтерфейс постачальника фінансових даних (DIP)."""

    def fetch_currency_rates(self) -> List[CurrencyRate]:
        return [
            CurrencyRate(code="USD", buy=41.20, sell=41.75),
            CurrencyRate(code="EUR", buy=44.60, sell=45.30),
        ]
    
    @abstractmethod
    def authenticate(self) -> str:
        pass

    @abstractmethod
    def fetch_savings_jars(self) -> List[SavingsJar]:
        pass

    @abstractmethod
    def fetch_credit_liabilities(self) -> List[CreditLiability]:
        pass

    @abstractmethod
    def fetch_recent_transactions(self, days: int = 7) -> List[Transaction]:
        pass

    @abstractmethod
    def fetch_account_balance(
        self, currency_rates: Optional[List[CurrencyRate]] = None
    ) -> float:
        pass


class MonobankApiAdapter(IFinancialDataSource):
    """Адаптер Monobank Personal REST API з авторизацією через X-Token."""

    BASE_URL = "https://api.monobank.ua"
    PORTAL_URL = "https://api.monobank.ua/"

    def __init__(self, token: str):
        self._token = token.strip()
        self._client_info: Optional[dict] = None
        self._primary_account_id: str = "0"

    @property
    def token(self) -> str:
        return self._token

    def _make_request(self, endpoint: str) -> dict | list:
        url = f"{self.BASE_URL}{endpoint}"
        request = urllib.request.Request(
            url,
            headers={
                "X-Token": self._token,
                "User-Agent": "MonoPlan-PyQt6/1.4",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PermissionError("Невірний токен Monobank (помилка 403).")
            if e.code == 429:
                raise RuntimeError("Ліміт API (429): оновлення раз на 60 сек.")
            raise RuntimeError(f"Помилка сервера Monobank: HTTP {e.code}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Помилка мережі: {e.reason}")

    def authenticate(self) -> str:
        if not self._token:
            raise PermissionError("Введіть X-Token для авторизації.")

        data = self._make_request("/personal/client-info")
        if not isinstance(data, dict):
            raise RuntimeError("Некоректна відповідь від API.")

        self._client_info = data
        for acc in data.get("accounts", []):
            if acc.get("currencyCode") == 980:
                self._primary_account_id = str(acc.get("id", "0"))
                break

        return str(data.get("name", "Клієнт Monobank"))

    def fetch_savings_jars(self) -> List[SavingsJar]:
        if not self._client_info:
            self.authenticate()
        assert self._client_info is not None

        jars: List[SavingsJar] = []
        for raw in self._client_info.get("jars", []):
            if raw.get("currencyCode") != 980:
                continue
            jars.append(
                SavingsJar(
                    jar_id=str(raw.get("id", "")),
                    title=str(raw.get("title", "Без назви")),
                    current_balance=float(raw.get("balance", 0) or 0) / 100.0,
                    goal_amount=float(raw.get("goal") or 0) / 100.0,
                )
            )
        return jars

    def fetch_credit_liabilities(self) -> List[CreditLiability]:
        if not self._client_info:
            self.authenticate()
        assert self._client_info is not None

        liabilities: List[CreditLiability] = []
        for acc in self._client_info.get("accounts", []):
            if acc.get("currencyCode") != 980:
                continue
            credit_limit = float(acc.get("creditLimit", 0) or 0) / 100.0
            available = float(acc.get("balance", 0) or 0) / 100.0
            if credit_limit > 0 and available < credit_limit:
                liabilities.append(
                    CreditLiability(
                        liability_id=str(acc.get("id", "")),
                        title=f"Кредитний ліміт ({acc.get('type', 'Картка')})",
                        credit_limit=credit_limit,
                        used_amount=credit_limit - available,
                        annual_rate=37.2,
                    )
                )
        return liabilities

    def fetch_recent_transactions(self, days: int = 7) -> List[Transaction]:
        if not self._client_info:
            self.authenticate()

        to_ts = int(datetime.now().timestamp())
        from_ts = int((datetime.now() - timedelta(days=days)).timestamp())
        raw_list = self._make_request(
            f"/personal/statement/{self._primary_account_id}/{from_ts}/{to_ts}"
        )
        if not isinstance(raw_list, list):
            return []

        transactions: List[Transaction] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            mcc = int(item.get("mcc", 0) or 0)
            transactions.append(
                Transaction(
                    tx_id=str(item.get("id", "")),
                    timestamp=datetime.fromtimestamp(int(item.get("time", 0) or 0)),
                    description=str(item.get("description", "Без опису")),
                    amount=float(item.get("amount", 0) or 0) / 100.0,
                    mcc=mcc,
                    category=MccCategoryMapper.get_category(mcc),
                )
            )
        return transactions

    def fetch_account_balance(
        self, currency_rates: Optional[List[CurrencyRate]] = None
    ) -> float:
        if not self._client_info:
            return 0.0

        rate_map = {r.code: r.buy for r in (currency_rates or [])}
        iso_to_code = {840: "USD", 978: "EUR"}
        total_uah = 0.0

        for acc in self._client_info.get("accounts", []):
            balance = float(acc.get("balance", 0) or 0)
            credit_limit = float(acc.get("creditLimit", 0) or 0)
            currency_code = int(acc.get("currencyCode", 980) or 980)

            own_funds = max(0.0, (balance - credit_limit) / 100.0)
            if own_funds <= 0:
                continue

            if currency_code == 980:
                total_uah += own_funds
            elif currency_code in iso_to_code:
                code = iso_to_code[currency_code]
                buy_rate = rate_map.get(code, 0.0)
                if buy_rate > 0:
                    total_uah += own_funds * buy_rate

        return round(total_uah, 2)

    def fetch_currency_rates(self) -> List[CurrencyRate]:
        return [
            CurrencyRate(code="USD", buy=41.20, sell=41.75),
            CurrencyRate(code="EUR", buy=44.60, sell=45.30),
        ]


class DemoDataSource(IFinancialDataSource):
    """Локальний постачальник даних для офлайн-демонстрації."""

    def authenticate(self) -> str:
        return "Олександр Коваленко (Демо-режим)"

    def fetch_savings_jars(self) -> List[SavingsJar]:
        return [
            SavingsJar("jar_1", "Ноутбук для навчання", 24500.0, 45000.0),
            SavingsJar("jar_2", "Фінансова подушка", 38000.0, 50000.0),
            SavingsJar("jar_3", "Подорож у Карпати", 6200.0, 12000.0),
        ]

    def fetch_credit_liabilities(self) -> List[CreditLiability]:
        return [
            CreditLiability(
                "cred_1",
                "Кредитна картка (Чорна)",
                30000.0,
                7850.0,
                annual_rate=37.2,
            ),
            CreditLiability(
                "cred_2",
                "Покупка частинами (Монітор)",
                14000.0,
                3500.0,
                annual_rate=0.01,
            ),
            CreditLiability(
                "cred_3",
                "Розстрочка на картку",
                10000.0,
                5200.0,
                annual_rate=22.8,
            ),
        ]

    def fetch_recent_transactions(self, days: int = 7) -> List[Transaction]:
        now = datetime.now()
        return [
            Transaction(
                "1", now, "Сільпо", -842.50, 5411, MccCategoryMapper.get_category(5411)
            ),
            Transaction(
                "2",
                now - timedelta(hours=18),
                "Арома Кава",
                -135.00,
                5812,
                MccCategoryMapper.get_category(5812),
            ),
            Transaction(
                "3",
                now - timedelta(days=1),
                "Uklon",
                -210.00,
                4121,
                MccCategoryMapper.get_category(4121),
            ),
            Transaction(
                "4",
                now - timedelta(days=2),
                "АТБ-Маркет",
                -514.20,
                5411,
                MccCategoryMapper.get_category(5411),
            ),
            Transaction(
                "5",
                now - timedelta(days=3),
                "Аптека Подорожник",
                -390.00,
                5912,
                MccCategoryMapper.get_category(5912),
            ),
            Transaction(
                "6",
                now - timedelta(days=4),
                "Поповнення картки",
                5000.00,
                0,
                "Надходження",
            ),
        ]

    def fetch_account_balance(
        self, currency_rates: Optional[List[CurrencyRate]] = None
    ) -> float:
        return 14250.00