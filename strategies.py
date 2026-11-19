from abc import ABC, abstractmethod
from typing import List

from models import CreditLiability


class DebtPayoffStrategy(ABC):
    """Абстрактна стратегія пріоритезації погашення боргів."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def sort_liabilities(
        self, liabilities: List[CreditLiability]
    ) -> List[CreditLiability]:
        pass


class AvalancheStrategy(DebtPayoffStrategy):
    """Метод 'Лавини': пріоритет боргам з найвищою відсотковою ставкою."""

    @property
    def name(self) -> str:
        return "Лавина (за відсотковою ставкою)"

    def sort_liabilities(
        self, liabilities: List[CreditLiability]
    ) -> List[CreditLiability]:
        return sorted(liabilities, key=lambda x: x.annual_rate, reverse=True)


class SnowballStrategy(DebtPayoffStrategy):
    """Метод 'Снігової кулі': пріоритет найменшим за сумою боргам."""

    @property
    def name(self) -> str:
        return "Снігова куля (за найменшим залишком)"

    def sort_liabilities(
        self, liabilities: List[CreditLiability]
    ) -> List[CreditLiability]:
        return sorted(liabilities, key=lambda x: x.get_remaining_amount())