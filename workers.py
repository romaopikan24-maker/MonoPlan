from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from ai_advisor import ChatHistory, IFinancialAdvisor
from bank_api import IFinancialDataSource
from models import (
    CreditLiability,
    CurrencyRate,
    ManualSavingEntry,
    SavingsJar,
    Transaction,
)


class DataLoaderThread(QThread):
    """Завантажує банківські дані у фоновому потоці."""

    data_loaded = pyqtSignal(str, list, list, list, list, float, str, object)
    error_occurred = pyqtSignal(str)

    def __init__(self, data_source: IFinancialDataSource):
        super().__init__()
        self._data_source = data_source

    def run(self) -> None:
        try:
            client_name = self._data_source.authenticate()
            jars = self._data_source.fetch_savings_jars()
            liabilities = self._data_source.fetch_credit_liabilities()
            currency_rates = self._data_source.fetch_currency_rates()
            account_balance = self._data_source.fetch_account_balance(currency_rates)

            warning = ""
            try:
                transactions = self._data_source.fetch_recent_transactions(days=7)
            except RuntimeError as e:
                transactions = []
                warning = str(e)

            self.data_loaded.emit(
                client_name,
                jars,
                liabilities,
                transactions,
                currency_rates,
                account_balance,
                warning,
                self._data_source,
            )
        except Exception as e:
            self.error_occurred.emit(str(e))


class AiChatThread(QThread):
    """Виконує запит до фінансового AI-чату у фоновому потоці."""

    reply_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        advisor: IFinancialAdvisor,
        chat_history: ChatHistory,
        jars: List[SavingsJar],
        liabilities: List[CreditLiability],
        transactions: List[Transaction],
        strategy_name: str,
        currency_rates: Optional[List[CurrencyRate]] = None,
        mono_account_balance: float = 0.0,
        manual_savings: Optional[List[ManualSavingEntry]] = None,
    ):
        super().__init__()
        self._advisor = advisor
        self._chat_history = chat_history
        self._jars = jars
        self._liabilities = liabilities
        self._transactions = transactions
        self._strategy_name = strategy_name
        self._currency_rates = currency_rates or []
        self._mono_account_balance = mono_account_balance
        self._manual_savings = manual_savings or []

    def run(self) -> None:
        try:
            answer = self._advisor.reply(
                self._chat_history,
                self._jars,
                self._liabilities,
                self._transactions,
                self._strategy_name,
                self._currency_rates,
                self._mono_account_balance,
                self._manual_savings,
            )
            self.reply_ready.emit(answer)
        except Exception as e:
            self.error_occurred.emit(str(e))