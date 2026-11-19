from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Dict, List, Optional
import urllib.error
import urllib.request

from models import (
    CreditLiability,
    CurrencyRate,
    ManualSavingEntry,
    SavingsJar,
    Transaction,
)


@dataclass
class ChatMessage:
    """Одне повідомлення в історії діалогу з фінансовим асистентом."""

    role: str  # "user" або "model"
    text: str
    timestamp: datetime


class ChatHistory:
    """Керує історією діалогу та формує контекст для багатоходового спілкування."""

    MAX_MESSAGES = 14

    def __init__(self):
        self._messages: List[ChatMessage] = []

    @property
    def messages(self) -> List[ChatMessage]:
        return list(self._messages)

    def add_user_message(self, text: str) -> ChatMessage:
        msg = ChatMessage(role="user", text=text.strip(), timestamp=datetime.now())
        self._messages.append(msg)
        self._trim()
        return msg

    def add_assistant_message(self, text: str) -> ChatMessage:
        msg = ChatMessage(role="model", text=text.strip(), timestamp=datetime.now())
        self._messages.append(msg)
        self._trim()
        return msg

    def clear(self) -> None:
        self._messages.clear()

    def to_gemini_contents(self) -> List[dict]:
        return [
            {"role": m.role, "parts": [{"text": m.text}]}
            for m in self._messages
        ]

    def _trim(self) -> None:
        if len(self._messages) > self.MAX_MESSAGES:
            self._messages = self._messages[-self.MAX_MESSAGES :]


class FinancialPromptBuilder:
    """Патерн Builder: формує системну інструкцію з фінансовим зрізом та обмеженням тем."""

    @staticmethod
    def build_system_instruction(
        jars: List[SavingsJar],
        liabilities: List[CreditLiability],
        transactions: List[Transaction],
        strategy_name: str,
        currency_rates: Optional[List[CurrencyRate]] = None,
        mono_account_balance: float = 0.0,
        manual_savings: Optional[List[ManualSavingEntry]] = None,
    ) -> str:
        lines: List[str] = [
            "Ти — персональний фінансовий AI-асистент у застосунку MonoPlan.",
            "Відповідай українською мовою, чітко, практично та лише на фінансові теми "
            "(бюджет, витрати, накопичення, банки, кредити, борги, курси валют, фінансові цілі).",
            f"Обрана стратегія погашення боргів: {strategy_name}.",
            "",
            "1. Накопичувальні банки:",
        ]

        if jars:
            for jar in jars:
                jar_type = "власна" if jar.is_custom else "Monobank"
                goal_part = (
                    f" з {jar.goal_amount:,.2f} грн ({jar.get_progress_percent()}%)"
                    if jar.goal_amount > 0
                    else " (без цільового ліміту)"
                )
                lines.append(
                    f"- «{jar.title}» [{jar_type}]: {jar.current_balance:,.2f} грн{goal_part}."
                )
        else:
            lines.append("- Активних банок немає.")

        lines.append("")
        lines.append("2. Кредитні зобов'язання та борги:")
        if liabilities:
            for debt in liabilities:
                lines.append(
                    f"- «{debt.title}»: борг {debt.get_remaining_amount():,.2f} грн, "
                    f"ставка {debt.annual_rate}% річних, ліміт {debt.credit_limit:,.2f} грн."
                )
        else:
            lines.append("- Активних боргів немає.")

        lines.append("")
        lines.append("3. Останні витрати та транзакції:")
        expenses = [tx for tx in transactions if tx.is_expense]
        if expenses:
            cat_totals: Dict[str, float] = {}
            for tx in expenses:
                cat_totals[tx.category] = cat_totals.get(tx.category, 0.0) + abs(tx.amount)
            total_exp = sum(cat_totals.values())
            lines.append(f"- Загальні витрати за період: {total_exp:,.2f} грн.")
            for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  • {cat}: {amt:,.2f} грн.")
        else:
            lines.append("- Дані про витрати відсутні.")

        lines.append("")
        lines.append("4. Курси валют:")
        if currency_rates:
            for rate in currency_rates:
                lines.append(
                    f"- {rate.code}/UAH: купівля {rate.buy:.2f}, продаж {rate.sell:.2f}."
                )
        else:
            lines.append("- Курси валют не завантажено.")

        other_bank_sum = sum(
            s.amount
            for s in (manual_savings or [])
            if s.category_type == "other_bank"
        )
        cash_sum = sum(
            s.amount for s in (manual_savings or []) if s.category_type == "cash"
        )

        lines.append("")
        lines.append("5. Додаткові накопичення користувача:")
        lines.append(
            f"- Власні кошти на рахунках Monobank: {mono_account_balance:,.2f} грн."
        )
        lines.append(f"- Накопичення в інших банках: {other_bank_sum:,.2f} грн.")
        lines.append(f"- Накопичення готівкою: {cash_sum:,.2f} грн.")

        return "\n".join(lines)


class IFinancialAdvisor(ABC):
    """Інтерфейс діалогового фінансового радника."""

    @abstractmethod
    def reply(
        self,
        chat_history: ChatHistory,
        jars: List[SavingsJar],
        liabilities: List[CreditLiability],
        transactions: List[Transaction],
        strategy_name: str,
        currency_rates: Optional[List[CurrencyRate]] = None,
        mono_account_balance: float = 0.0,
        manual_savings: Optional[List[ManualSavingEntry]] = None,
    ) -> str:
        pass


class GeminiFinancialAdvisor(IFinancialAdvisor):
    """Хмарний фінансовий чат-асистент на базі Google Gemini API."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    PREFERRED_PREFIXES = (
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash",
        "gemini-2.5-pro",
        "gemini-pro",
    )

    def __init__(self, api_key: str):
        self._api_key = api_key.strip()
        self._resolved_model: Optional[str] = None

    def _list_available_models(self) -> List[str]:
        """Отримує список моделей, доступних для ключа та підтримуючих generateContent."""
        url = f"{self.BASE_URL}?key={self._api_key}"
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))

        available: List[str] = []
        for item in payload.get("models", []):
            if not isinstance(item, dict):
                continue
            methods = item.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            name = str(item.get("name", ""))
            if name.startswith("models/"):
                name = name[len("models/") :]
            if name:
                available.append(name)
        return available

    def _select_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model

        models = self._list_available_models()
        if not models:
            raise RuntimeError(
                "Для цього API-ключа не знайдено жодної моделі з підтримкою generateContent."
            )

        for prefix in self.PREFERRED_PREFIXES:
            for m in models:
                if m == prefix or m.startswith(prefix):
                    self._resolved_model = m
                    return m

        for m in models:
            if "gemini" in m and "embedding" not in m and "imagen" not in m and "veo" not in m:
                self._resolved_model = m
                return m

        self._resolved_model = models[0]
        return self._resolved_model

    def reply(
        self,
        chat_history: ChatHistory,
        jars: List[SavingsJar],
        liabilities: List[CreditLiability],
        transactions: List[Transaction],
        strategy_name: str,
        currency_rates: Optional[List[CurrencyRate]] = None,
        mono_account_balance: float = 0.0,
        manual_savings: Optional[List[ManualSavingEntry]] = None,
    ) -> str:
        if not self._api_key:
            raise PermissionError("API-ключ Gemini не вказано.")

        system_instruction = FinancialPromptBuilder.build_system_instruction(
            jars=jars,
            liabilities=liabilities,
            transactions=transactions,
            strategy_name=strategy_name,
            currency_rates=currency_rates,
            mono_account_balance=mono_account_balance,
            manual_savings=manual_savings,
        )

        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": chat_history.to_gemini_contents(),
            "generationConfig": {
                "temperature": 0.4,
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")

        try:
            model_id = self._select_model()
            url = f"{self.BASE_URL}/{model_id}:generateContent"
            request = urllib.request.Request(
                url,
                data=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._api_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                data = json.loads(response.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError("AI не повернув відповідь.")
                parts = candidates[0].get("content", {}).get("parts", [])
                text_chunks = [
                    p["text"]
                    for p in parts
                    if "text" in p and not p.get("thought", False)
                ]
                result_text = "\n".join(text_chunks).strip()
                if not result_text:
                    raise RuntimeError("AI повернув порожню текстову відповідь.")
                return result_text
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            if e.code in (400, 401, 403):
                raise PermissionError(
                    "Невірний або заблокований API-ключ Google AI Studio."
                )
            if e.code == 404:
                self._resolved_model = None
                raise RuntimeError(
                    f"Модель недоступна (HTTP 404). {err_body[:180]}".strip()
                )
            if e.code == 429:
                raise RuntimeError(
                    "Перевищено ліміт безкоштовних запитів Gemini API. Зачекайте хвилину."
                )
            raise RuntimeError(f"Помилка Gemini API: HTTP {e.code}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Помилка з'єднання з Gemini API: {e.reason}")

class LocalHeuristicAdvisor(IFinancialAdvisor):
    """Офлайн фінансовий чат-порадник із тематичним фільтром (резервний режим)."""

    _FINANCE_KEYWORDS = (
        "грош", "бюджет", "витрат", "кредит", "борг", "банк", "накопич",
        "ціл", "ставк", "відсот", "лавин", "снігов", "куля", "ощад",
        "заощад", "подушк", "економ", "дохід", "зарплат", "картк", "ліміт",
        "розстроч", "платіж", "стратег", "фінанс", "інвест", "депозит",
        "курс", "валют", "покуп", "скільки", "порад", "аналіз", "привіт", "вітаю",
    )

    def _is_finance_topic(self, text: str) -> bool:
        lowered = text.lower()
        return any(kw in lowered for kw in self._FINANCE_KEYWORDS)

    def reply(
        self,
        chat_history: ChatHistory,
        jars: List[SavingsJar],
        liabilities: List[CreditLiability],
        transactions: List[Transaction],
        strategy_name: str,
        currency_rates: Optional[List[CurrencyRate]] = None,
        mono_account_balance: float = 0.0,
        manual_savings: Optional[List[ManualSavingEntry]] = None,
    ) -> str:
        messages = chat_history.messages
        last_user_msg = messages[-1].text if messages else ""

        if last_user_msg and not self._is_finance_topic(last_user_msg):
            return (
                "Я спеціалізуюся виключно на фінансовому плануванні, аналізі витрат, "
                "накопичувальних банках та погашенні кредитів. "
                "Запитайте мене, наприклад, як швидше закрити кредитний ліміт або де скоротити витрати."
            )

        lowered = last_user_msg.lower()
        total_debt = sum(d.get_remaining_amount() for d in liabilities)
        manual_sum = sum(m.amount for m in (manual_savings or []))
        total_saved = (
            sum(j.current_balance for j in jars)
            + float(mono_account_balance or 0.0)
            + manual_sum
        )

        if any(w in lowered for w in ("борг", "кредит", "ліміт", "розстроч", "лавин", "снігов")):
            if not liabilities:
                return "Зараз у вас немає активних кредитних зобов'язань — вільні кошти можна спрямувати у накопичувальні банки."
            top_rate = max(liabilities, key=lambda x: x.annual_rate)
            smallest = min(liabilities, key=lambda x: x.get_remaining_amount())
            return (
                f"Загальна сума ваших кредитних зобов'язань: {total_debt:,.2f} грн.\n"
                f"• За стратегією «Лавина» найвигідніше першим закрити «{top_rate.title}» "
                f"(ставка {top_rate.annual_rate}% річних, залишок {top_rate.get_remaining_amount():,.2f} грн).\n"
                f"• За стратегією «Снігова куля» найшвидше повністю погасити «{smallest.title}» "
                f"({smallest.get_remaining_amount():,.2f} грн).\n"
                f"Яку суму щомісяця ви готові виділяти на погашення боргів?"
            )

        if any(w in lowered for w in ("витрат", "економ", "категор", "грош")):
            cat_totals: Dict[str, float] = {}
            for tx in transactions:
                if tx.is_expense:
                    cat_totals[tx.category] = cat_totals.get(tx.category, 0.0) + abs(tx.amount)
            if not cat_totals:
                return "Поки що немає транзакцій для аналізу витрат. Підключіть Monobank або завантажте демо-дані."
            top_cat, top_amt = max(cat_totals.items(), key=lambda x: x[1])
            save_15 = top_amt * 0.15
            return (
                f"Найбільша стаття ваших витрат за тиждень — «{top_cat}» ({top_amt:,.2f} грн).\n"
                f"Якщо зменшити витрати в цій категорії на 15%, ви вивільните ~{save_15:,.2f} грн на тиждень "
                f"(~{save_15 * 4:,.2f} грн на місяць), що прискорить досягнення ваших фінансових цілей."
            )

        if any(w in lowered for w in ("банк", "ціл", "накопич", "подушк")):
            if not jars:
                return "У вас поки немає активних гривневих банок. Рекомендую створити окрему банку для фінансової подушки."
            nearest = min(
                [j for j in jars if j.get_remaining_amount() > 0] or jars,
                key=lambda x: x.get_remaining_amount(),
            )
            return (
                f"Загалом у ваших накопиченнях {total_saved:,.2f} грн.\n"
                f"Найближча до закриття ціль — «{nearest.title}» (залишилось {nearest.get_remaining_amount():,.2f} грн). "
                f"Якщо ставка за вашим кредитом вища за 20% річних, спершу варто зменшити кредитний ліміт, а потім прискорити поповнення банок."
            )

        return (
            f"Коротке зведення по вашому портфелю (стратегія: {strategy_name}):\n"
            f"• Загальні накопичення: {total_saved:,.2f} грн\n"
            f"• Загальний борг: {total_debt:,.2f} грн\n"
            f"Уточніть, що саме обговоримо: графік погашення боргів, оптимізацію витрат чи розподіл коштів між банками? "
            f"(Для вільного діалогу вкажіть безкоштовний ключ Gemini API вгорі цієї вкладки)."
        )