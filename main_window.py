from datetime import datetime
import inspect
from typing import Dict, List, Optional, Tuple
import uuid

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ai_advisor import (
    ChatHistory,
    ChatMessage,
    DEFAULT_GEMINI_API_KEY,
    GeminiFinancialAdvisor,
    IFinancialAdvisor,
    LocalHeuristicAdvisor,
)
from bank_api import DemoDataSource, IFinancialDataSource, MonobankApiAdapter
from models import (
    CreditLiability,
    CurrencyRate,
    ManualSavingEntry,
    SavingsJar,
    Transaction,
)
from storage import UserSession, UserSessionRepository
from strategies import AvalancheStrategy, DebtPayoffStrategy, SnowballStrategy
from ui_widgets import (
    AddJarButtonWidget,
    ChatBubbleWidget,
    CustomJarDialog,
    CustomTitleBarWidget,
    JarCardWidget,
    LiabilityCardWidget,
    ManualSavingCardWidget,
    ManualSavingDialog,
    MONO_ACCOUNT_DEFAULT_COLOR,
    MONO_JARS_DEFAULT_COLOR,
    QrAuthDialog,
    SavingsPieChartWidget,
    TopUpJarDialog,
    pick_next_category_color,
)
from workers import AiChatThread, DataLoaderThread


class MonoPlanWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MonoPlan — Цілі, Борги та Monobank API")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        )
        self.resize(980, 720)

        self._session_repo = UserSessionRepository()
        self._current_session: Optional[UserSession] = None
        self._remember_next_login: bool = True

        self._jars: List[SavingsJar] = []
        self._jar_order: List[str] = []
        self._mono_account_balance: float = 0.0
        self._manual_savings: List[ManualSavingEntry] = []
        self._liabilities: List[CreditLiability] = []
        self._transactions: List[Transaction] = []
        self._currency_rates: List[CurrencyRate] = []
        self._strategy: DebtPayoffStrategy = AvalancheStrategy()
        self._chat_history = ChatHistory()
        self._typing_widget: Optional[QWidget] = None

        self._worker: Optional[DataLoaderThread] = None
        self._ai_worker: Optional[AiChatThread] = None

        self._init_ui()
        self._init_chat_welcome()
        self._restore_or_start_demo()

    def _toggle_maximize_window(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self._title_bar.set_maximized_state(False)
        else:
            self.showMaximized()
            self._title_bar.set_maximized_state(True)

    def changeEvent(self, event) -> None:
        if hasattr(self, "_title_bar"):
            self._title_bar.set_maximized_state(self.isMaximized())
        super().changeEvent(event)

    def _init_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # --- КАСТОМНА ВЕРХНЯ ПОЛОСА ---
        self._title_bar = CustomTitleBarWidget(
            "MonoPlan — Цілі, Борги та Monobank API", self
        )
        self._title_bar.minimize_clicked.connect(self.showMinimized)
        self._title_bar.toggle_maximize_clicked.connect(self._toggle_maximize_window)
        self._title_bar.close_clicked.connect(self.close)
        main_layout.addWidget(self._title_bar)

        # --- ВЕРХНЯ ПАНЕЛЬ АВТОРИЗАЦІЇ ТА ПРОФІЛЮ ---
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_layout = QVBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 14, 16, 14)
        top_layout.setSpacing(10)

        title_row = QHBoxLayout()
        app_title = QLabel("MonoPlan")
        app_title.setObjectName("AppTitle")
        self._status_label = QLabel("Очікування підключення...")
        self._status_label.setObjectName("StatusBanner")

        title_row.addWidget(app_title)
        title_row.addStretch()
        title_row.addWidget(self._status_label)
        top_layout.addLayout(title_row)

        self._guest_panel = QWidget()
        guest_layout = QHBoxLayout(self._guest_panel)
        guest_layout.setContentsMargins(0, 0, 0, 0)
        guest_layout.setSpacing(10)

        self._token_input = QLineEdit()
        self._token_input.setPlaceholderText("Вставте X-Token Monobank...")
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)

        self._remember_cb = QCheckBox("Запам'ятати мене")
        self._remember_cb.setChecked(True)

        self._qr_btn = QPushButton("Отримати токен (QR)")
        self._qr_btn.setObjectName("PrimaryBtn")
        self._qr_btn.clicked.connect(self._on_open_qr_dialog)

        self._connect_btn = QPushButton("Підключити")
        self._connect_btn.setObjectName("SecondaryBtn")
        self._connect_btn.clicked.connect(self._on_connect_token)

        self._demo_btn = QPushButton("Демо-дані")
        self._demo_btn.setObjectName("SecondaryBtn")
        self._demo_btn.clicked.connect(lambda: self._load_data(DemoDataSource()))

        guest_layout.addWidget(self._token_input, stretch=1)
        guest_layout.addWidget(self._remember_cb)
        guest_layout.addWidget(self._qr_btn)
        guest_layout.addWidget(self._connect_btn)
        guest_layout.addWidget(self._demo_btn)
        top_layout.addWidget(self._guest_panel)

        self._user_panel = QWidget()
        self._user_panel.setVisible(False)
        user_layout = QHBoxLayout(self._user_panel)
        user_layout.setContentsMargins(0, 0, 0, 0)
        user_layout.setSpacing(10)

        self._user_badge = QLabel("Акаунт збережено")
        self._user_badge.setObjectName("BadgeGreen")

        self._refresh_btn = QPushButton("Оновити з Monobank")
        self._refresh_btn.setObjectName("PrimaryBtn")
        self._refresh_btn.clicked.connect(self._on_refresh_saved_user)

        self._logout_btn = QPushButton("Вийти")
        self._logout_btn.setObjectName("DangerBtn")
        self._logout_btn.clicked.connect(self._on_logout)

        user_layout.addWidget(self._user_badge)
        user_layout.addStretch()
        user_layout.addWidget(self._refresh_btn)
        user_layout.addWidget(self._logout_btn)
        top_layout.addWidget(self._user_panel)

        main_layout.addWidget(top_bar)

        # --- ВКЛАДКИ ---
        tabs = QTabWidget()
        tabs.addTab(self._build_goals_and_debts_tab(), "Цілі та Борги")
        tabs.addTab(self._build_savings_chart_tab(), "Діаграма накопичень")
        tabs.addTab(self._build_expenses_tab(), "Витрати та Категорії")
        tabs.addTab(self._build_ai_chat_tab(), "Фінансовий AI-чат")
        main_layout.addWidget(tabs)

    def _build_goals_and_debts_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)

        left_col = QVBoxLayout()
        jars_header = QLabel("Цільові накопичення (Банки)")
        jars_header.setObjectName("SectionTitle")
        left_col.addWidget(jars_header)

        jars_scroll = QScrollArea()
        jars_scroll.setWidgetResizable(True)
        jars_container = QWidget()
        jars_container.setObjectName("ScrollContent")
        self._jars_layout = QVBoxLayout(jars_container)
        self._jars_layout.setContentsMargins(0, 4, 4, 0)
        self._jars_layout.setSpacing(10)
        self._jars_layout.addStretch()
        jars_scroll.setWidget(jars_container)
        left_col.addWidget(jars_scroll)

        right_col = QVBoxLayout()
        debts_top = QHBoxLayout()
        debts_header = QLabel("Пріоритет погашення боргів")
        debts_header.setObjectName("SectionTitle")

        self._strategy_combo = QComboBox()
        self._strategy_combo.addItems(
            ["Стратегія: Лавина (за %)", "Стратегія: Снігова куля (за сумою)"]
        )
        self._strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)

        debts_top.addWidget(debts_header)
        debts_top.addStretch()
        debts_top.addWidget(self._strategy_combo)
        right_col.addLayout(debts_top)

        debts_scroll = QScrollArea()
        debts_scroll.setWidgetResizable(True)
        debts_container = QWidget()
        debts_container.setObjectName("ScrollContent")
        self._debts_layout = QVBoxLayout(debts_container)
        self._debts_layout.setContentsMargins(0, 4, 4, 0)
        self._debts_layout.setSpacing(10)
        self._debts_layout.addStretch()
        debts_scroll.setWidget(debts_container)
        right_col.addWidget(debts_scroll)

        layout.addLayout(left_col, stretch=1)
        layout.addLayout(right_col, stretch=1)
        return tab

    def _build_savings_chart_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)

        chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(18, 16, 18, 16)
        chart_layout.setSpacing(12)

        chart_title = QLabel("Структура загальних накопичень")
        chart_title.setObjectName("SectionTitle")
        chart_layout.addWidget(chart_title)

        self._savings_pie = SavingsPieChartWidget()
        chart_layout.addWidget(self._savings_pie, stretch=1)

        self._legend_layout = QVBoxLayout()
        self._legend_layout.setSpacing(8)
        chart_layout.addLayout(self._legend_layout)

        right_col = QVBoxLayout()
        right_top = QHBoxLayout()
        manual_header = QLabel("Інші банки та готівка (вручну)")
        manual_header.setObjectName("SectionTitle")

        add_manual_btn = QPushButton("+ Додати")
        add_manual_btn.setObjectName("PrimaryBtn")
        add_manual_btn.clicked.connect(self._on_add_manual_saving)

        right_top.addWidget(manual_header)
        right_top.addStretch()
        right_top.addWidget(add_manual_btn)
        right_col.addLayout(right_top)

        manual_scroll = QScrollArea()
        manual_scroll.setWidgetResizable(True)
        manual_container = QWidget()
        manual_container.setObjectName("ScrollContent")
        self._manual_savings_layout = QVBoxLayout(manual_container)
        self._manual_savings_layout.setContentsMargins(0, 4, 4, 0)
        self._manual_savings_layout.setSpacing(10)
        self._manual_savings_layout.addStretch()
        manual_scroll.setWidget(manual_container)
        right_col.addWidget(manual_scroll)

        layout.addWidget(chart_card, stretch=1)
        layout.addLayout(right_col, stretch=1)
        return tab

    def _build_expenses_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)

        cat_card = QFrame()
        cat_card.setObjectName("Card")
        cat_card_layout = QVBoxLayout(cat_card)
        cat_card_layout.setContentsMargins(16, 16, 16, 16)
        cat_card_layout.setSpacing(12)

        cat_title = QLabel("Витрати за категоріями (7 днів)")
        cat_title.setObjectName("SectionTitle")
        cat_card_layout.addWidget(cat_title)

        self._categories_layout = QVBoxLayout()
        self._categories_layout.setSpacing(10)
        cat_card_layout.addLayout(self._categories_layout)
        cat_card_layout.addStretch()

        self._total_spent_lbl = QLabel("Разом витрачено: 0.00 ₴")
        self._total_spent_lbl.setObjectName("CardTitle")
        cat_card_layout.addWidget(self._total_spent_lbl)

        self._tx_table = QTableWidget(0, 4)
        self._tx_table.setHorizontalHeaderLabels(
            ["Дата", "Опис", "Категорія", "Сума"]
        )
        self._tx_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tx_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._tx_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tx_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tx_table.verticalHeader().setVisible(False)
        self._tx_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tx_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        layout.addWidget(cat_card, stretch=2)
        layout.addWidget(self._tx_table, stretch=3)
        return tab

    def _build_ai_chat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        top_row = QHBoxLayout()
        chat_title = QLabel("Асистент MonoPlan AI")
        chat_title.setObjectName("SectionTitle")

        clear_chat_btn = QPushButton("Очистити чат")
        clear_chat_btn.setObjectName("SecondaryBtn")
        clear_chat_btn.clicked.connect(self._on_clear_chat)

        top_row.addWidget(chat_title)
        top_row.addStretch()
        top_row.addWidget(clear_chat_btn)
        card_layout.addLayout(top_row)

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        chat_container = QWidget()
        chat_container.setObjectName("ChatContainer")
        self._chat_messages_layout = QVBoxLayout(chat_container)
        self._chat_messages_layout.setContentsMargins(6, 6, 6, 6)
        self._chat_messages_layout.setSpacing(10)
        self._chat_messages_layout.addStretch()
        self._chat_scroll.setWidget(chat_container)
        card_layout.addWidget(self._chat_scroll, stretch=1)

        chips_row = QHBoxLayout()
        chips_lbl = QLabel("Теми:")
        chips_lbl.setObjectName("SubText")
        chips_row.addWidget(chips_lbl)

        topics = [
            ("План закриття кредитів", "Склади покроковий план закриття моїх кредитів."),
            ("Аналіз витрат", "Де я можу скоротити витрати за останній тиждень?"),
            ("Цілі чи борги?", "Що зараз вигідніше: поповнювати банки чи гасити кредитний ліміт?"),
        ]
        for chip_title, prompt_text in topics:
            btn = QPushButton(chip_title)
            btn.setObjectName("SecondaryBtn")
            btn.clicked.connect(lambda _, q=prompt_text: self._send_chat_message(q))
            chips_row.addWidget(btn)
        chips_row.addStretch()
        card_layout.addLayout(chips_row)

        input_row = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText(
            "Напишіть ваше фінансове запитання (наприклад: скільки відкладати щомісяця?)..."
        )
        self._chat_input.returnPressed.connect(
            lambda: self._send_chat_message(self._chat_input.text())
        )

        self._send_chat_btn = QPushButton("Надіслати")
        self._send_chat_btn.setObjectName("PrimaryBtn")
        self._send_chat_btn.clicked.connect(
            lambda: self._send_chat_message(self._chat_input.text())
        )

        input_row.addWidget(self._chat_input, stretch=1)
        input_row.addWidget(self._send_chat_btn)
        card_layout.addLayout(input_row)

        layout.addWidget(card)
        return tab

    def _apply_jar_order(self, jars: List[SavingsJar]) -> List[SavingsJar]:
        if not self._jar_order:
            self._jar_order = [j.item_id for j in jars]
            return list(jars)

        order_map = {jar_id: idx for idx, jar_id in enumerate(self._jar_order)}
        ordered = sorted(
            jars, key=lambda j: order_map.get(j.item_id, len(self._jar_order))
        )
        self._jar_order = [j.item_id for j in ordered]
        return ordered

    def _persist_local_state(self) -> None:
        self._jar_order = [j.item_id for j in self._jars]
        has_mono_token = bool(self._current_session and self._current_session.token)
        jars_to_store = (
            [j.to_dict() for j in self._jars]
            if has_mono_token
            else [j.to_dict() for j in self._jars if j.is_custom]
        )
        manual_to_store = [m.to_dict() for m in self._manual_savings]

        if self._current_session is None:
            self._current_session = UserSession(
                client_name="Користувач MonoPlan",
                token="",
                strategy_index=self._strategy_combo.currentIndex(),
                gemini_api_key="",
                cached_jars=jars_to_store,
                jar_order=list(self._jar_order),
                manual_savings=manual_to_store,
                cached_account_balance=self._mono_account_balance,
            )
        else:
            self._current_session.cached_jars = jars_to_store
            self._current_session.jar_order = list(self._jar_order)
            self._current_session.manual_savings = manual_to_store
            self._current_session.cached_account_balance = self._mono_account_balance

        self._session_repo.save_session(self._current_session)

    def _on_move_jar_up(self, jar_id: str) -> None:
        idx = next((i for i, j in enumerate(self._jars) if j.item_id == jar_id), -1)
        if idx > 0:
            self._jars[idx], self._jars[idx - 1] = self._jars[idx - 1], self._jars[idx]
            self._persist_local_state()
            self._render_jars(self._jars)

    def _on_move_jar_down(self, jar_id: str) -> None:
        idx = next((i for i, j in enumerate(self._jars) if j.item_id == jar_id), -1)
        if 0 <= idx < len(self._jars) - 1:
            self._jars[idx], self._jars[idx + 1] = self._jars[idx + 1], self._jars[idx]
            self._persist_local_state()
            self._render_jars(self._jars)

    def _on_add_custom_jar(self) -> None:
        dialog = CustomJarDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_jar = SavingsJar(
                jar_id=f"custom_{uuid.uuid4().hex[:8]}",
                title=dialog.jar_title,
                current_balance=dialog.current_balance,
                goal_amount=dialog.goal_amount,
                is_custom=True,
            )
            self._jars.append(new_jar)
            self._persist_local_state()
            self._render_jars(self._jars)
            self._render_savings_chart()
            self._status_label.setText(f"Додано власну банку: «{new_jar.title}»")

    def _on_top_up_custom_jar(self, jar_id: str) -> None:
        jar = next(
            (j for j in self._jars if j.item_id == jar_id and j.is_custom), None
        )
        if jar is None:
            return
        dialog = TopUpJarDialog(jar, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            jar.adjust_balance(dialog.delta_amount)
            self._persist_local_state()
            self._render_jars(self._jars)
            self._render_savings_chart()
            self._status_label.setText(f"Оновлено баланс банки «{jar.title}»")

    def _on_delete_custom_jar(self, jar_id: str) -> None:
        target = next(
            (j for j in self._jars if j.item_id == jar_id and j.is_custom), None
        )
        if target is None:
            return
        self._jars = [j for j in self._jars if j.item_id != jar_id]
        self._persist_local_state()
        self._render_jars(self._jars)
        self._render_savings_chart()
        self._status_label.setText(f"Видалено власну банку «{target.title}»")

    def _on_add_manual_saving(self) -> None:
        used_colors = [
            MONO_JARS_DEFAULT_COLOR,
            MONO_ACCOUNT_DEFAULT_COLOR,
            *(m.color_hex for m in self._manual_savings if m.color_hex),
        ]
        dialog = ManualSavingDialog(used_colors=used_colors, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            entry = ManualSavingEntry(
                entry_id=f"sav_{uuid.uuid4().hex[:8]}",
                category_type=dialog.category_type,
                title=dialog.entry_title,
                amount=dialog.amount_value,
                color_hex=dialog.color_hex,
            )
            self._manual_savings.append(entry)
            self._persist_local_state()
            self._render_savings_chart()
            self._status_label.setText(f"Додано накопичення: «{entry.title}»")

    def _on_edit_manual_saving(self, entry_id: str) -> None:
        target = next(
            (m for m in self._manual_savings if m.entry_id == entry_id), None
        )
        if target is None:
            return
        used_colors = [
            MONO_JARS_DEFAULT_COLOR,
            MONO_ACCOUNT_DEFAULT_COLOR,
            *(
                m.color_hex
                for m in self._manual_savings
                if m.entry_id != entry_id and m.color_hex
            ),
        ]
        dialog = ManualSavingDialog(existing=target, used_colors=used_colors, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            target.category_type = dialog.category_type
            target.title = dialog.entry_title
            target.amount = dialog.amount_value
            target.color_hex = dialog.color_hex
            self._persist_local_state()
            self._render_savings_chart()
            self._status_label.setText(f"Оновлено запис «{target.title}»")

    def _on_manual_entry_color_changed(self, entry_id: str, new_hex: str) -> None:
        target = next(
            (m for m in self._manual_savings if m.entry_id == entry_id), None
        )
        if target is not None:
            target.color_hex = new_hex
            self._persist_local_state()
            self._render_savings_chart()

    def _on_delete_manual_saving(self, entry_id: str) -> None:
        target = next(
            (m for m in self._manual_savings if m.entry_id == entry_id), None
        )
        if target is None:
            return
        self._manual_savings = [
            m for m in self._manual_savings if m.entry_id != entry_id
        ]
        self._persist_local_state()
        self._render_savings_chart()
        self._status_label.setText(f"Видалено запис «{target.title}»")

    def _init_chat_welcome(self) -> None:
        welcome = self._chat_history.add_assistant_message(
            "Вітаю! Я ваш фінансовий асистент у MonoPlan. "
            "Я бачу ваші накопичувальні банки, залишок на рахунку Monobank, "
            "ручні заощадження в інших банках і готівкою, кредити та витрати. "
            "Можемо обговорити стратегію погашення боргів або план накопичень."
        )
        self._append_chat_bubble(welcome)

    def _on_clear_chat(self) -> None:
        self._chat_history.clear()
        self._clear_layout(self._chat_messages_layout)
        self._chat_messages_layout.addStretch()
        self._init_chat_welcome()

    def _append_chat_bubble(self, msg: ChatMessage) -> None:
        insert_pos = max(0, self._chat_messages_layout.count() - 1)
        self._chat_messages_layout.insertWidget(insert_pos, ChatBubbleWidget(msg))
        QTimer.singleShot(50, self._scroll_chat_to_bottom)

    def _scroll_chat_to_bottom(self) -> None:
        scrollbar = self._chat_scroll.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    def _send_chat_message(self, raw_text: str) -> None:
        text = raw_text.strip()
        if not text or not self._send_chat_btn.isEnabled():
            return

        self._chat_input.clear()
        user_msg = self._chat_history.add_user_message(text)
        self._append_chat_bubble(user_msg)

        typing_msg = ChatMessage(
            role="model",
            text="Аналізую ваші фінансові показники...",
            timestamp=datetime.now(),
        )
        self._typing_widget = ChatBubbleWidget(typing_msg)
        insert_pos = max(0, self._chat_messages_layout.count() - 1)
        self._chat_messages_layout.insertWidget(insert_pos, self._typing_widget)
        QTimer.singleShot(50, self._scroll_chat_to_bottom)

        self._send_chat_btn.setEnabled(False)
        self._chat_input.setEnabled(False)

        advisor: IFinancialAdvisor = (
            GeminiFinancialAdvisor()
            if DEFAULT_GEMINI_API_KEY.strip()
            else LocalHeuristicAdvisor()
        )

        self._ai_worker = AiChatThread(
            advisor=advisor,
            chat_history=self._chat_history,
            jars=self._jars,
            liabilities=self._liabilities,
            transactions=self._transactions,
            strategy_name=self._strategy.name,
            currency_rates=self._currency_rates,
            mono_account_balance=self._mono_account_balance,
            manual_savings=self._manual_savings,
        )
        self._ai_worker.reply_ready.connect(self._on_chat_reply_ready)
        self._ai_worker.error_occurred.connect(self._on_chat_error)
        self._ai_worker.start()

    def _remove_typing_indicator(self) -> None:
        if self._typing_widget is not None:
            self._typing_widget.deleteLater()
            self._typing_widget = None

    def _on_chat_reply_ready(self, reply_text: str) -> None:
        self._remove_typing_indicator()
        self._send_chat_btn.setEnabled(True)
        self._chat_input.setEnabled(True)
        self._chat_input.setFocus()

        bot_msg = self._chat_history.add_assistant_message(reply_text)
        self._append_chat_bubble(bot_msg)

    def _on_chat_error(self, error_msg: str) -> None:
        self._remove_typing_indicator()
        self._send_chat_btn.setEnabled(True)
        self._chat_input.setEnabled(True)
        self._chat_input.setFocus()

        fallback = LocalHeuristicAdvisor()
        if "manual_savings" in inspect.signature(fallback.reply).parameters:
            fallback_reply = fallback.reply(
                self._chat_history,
                self._jars,
                self._liabilities,
                self._transactions,
                self._strategy.name,
                self._currency_rates,
                self._mono_account_balance,
                self._manual_savings,
            )
        else:
            fallback_reply = fallback.reply(
                self._chat_history,
                self._jars,
                self._liabilities,
                self._transactions,
                self._strategy.name,
                self._currency_rates,
            )
        combined = f"[Хмарний AI недоступний: {error_msg}]\n\n{fallback_reply}"
        bot_msg = self._chat_history.add_assistant_message(combined)
        self._append_chat_bubble(bot_msg)

    def _restore_or_start_demo(self) -> None:
        saved = self._session_repo.load_session()
        if saved is not None:
            self._current_session = saved
            self._remember_next_login = True
            self._strategy_combo.setCurrentIndex(saved.strategy_index)
            self._jar_order = list(saved.jar_order)
            self._manual_savings = [
                ManualSavingEntry.from_dict(m) for m in saved.manual_savings
            ]
            self._mono_account_balance = float(saved.cached_account_balance)

            restored_jars = [SavingsJar.from_dict(j) for j in saved.cached_jars]

            if saved.token:
                self._jars = self._apply_jar_order(restored_jars)
                self._liabilities = [
                    CreditLiability.from_dict(d) for d in saved.cached_liabilities
                ]
                self._transactions = [
                    Transaction.from_dict(t) for t in saved.cached_transactions
                ]
                self._render_all()
                self._switch_to_authorized_ui(saved.client_name)
                self._load_data(MonobankApiAdapter(saved.token))
                return

            self._jars = [j for j in restored_jars if j.is_custom]

        self._load_data(DemoDataSource())

    def _switch_to_authorized_ui(self, client_name: str) -> None:
        self._guest_panel.setVisible(False)
        self._user_panel.setVisible(True)
        self._user_badge.setText(f"Збережений профіль: {client_name}")

    def _switch_to_guest_ui(self) -> None:
        self._user_panel.setVisible(False)
        self._guest_panel.setVisible(True)
        self._token_input.clear()

    def _on_open_qr_dialog(self) -> None:
        dialog = QrAuthDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._remember_next_login = dialog.remember_me
            self._load_data(MonobankApiAdapter(dialog.token_value))

    def _on_connect_token(self) -> None:
        token = self._token_input.text().strip()
        if not token:
            self._status_label.setText(
                "Введіть X-Token або натисніть 'Отримати токен (QR)'"
            )
            return
        self._remember_next_login = self._remember_cb.isChecked()
        self._load_data(MonobankApiAdapter(token))

    def _on_refresh_saved_user(self) -> None:
        if self._current_session and self._current_session.token:
            self._load_data(MonobankApiAdapter(self._current_session.token))

    def _on_logout(self) -> None:
        custom_jars = [j for j in self._jars if j.is_custom]
        self._jars = custom_jars
        self._session_repo.clear_session()
        self._current_session = None
        if custom_jars or self._manual_savings:
            self._persist_local_state()
        self._switch_to_guest_ui()
        self._status_label.setText("Ви вийшли з акаунту")
        self._load_data(DemoDataSource())

    def _set_controls_enabled(self, enabled: bool) -> None:
        self._qr_btn.setEnabled(enabled)
        self._connect_btn.setEnabled(enabled)
        self._demo_btn.setEnabled(enabled)
        self._refresh_btn.setEnabled(enabled)
        self._logout_btn.setEnabled(enabled)

    def _load_data(self, source: IFinancialDataSource) -> None:
        self._set_controls_enabled(False)
        self._status_label.setText("Синхронізація даних...")

        self._worker = DataLoaderThread(source)
        self._worker.data_loaded.connect(self._on_data_loaded)
        self._worker.error_occurred.connect(self._on_load_error)
        self._worker.start()

    def _on_data_loaded(self, *args) -> None:
        if len(args) == 8:
            (
                client_name,
                jars,
                liabilities,
                transactions,
                currency_rates,
                account_balance,
                warning,
                source,
            ) = args
            if currency_rates:
                self._currency_rates = currency_rates
            self._mono_account_balance = float(account_balance)
        elif len(args) == 7:
            (
                client_name,
                jars,
                liabilities,
                transactions,
                currency_rates,
                warning,
                source,
            ) = args
            if currency_rates:
                self._currency_rates = currency_rates
        else:
            client_name, jars, liabilities, transactions, warning, source = args

        self._set_controls_enabled(True)

        custom_jars = [j for j in self._jars if j.is_custom]
        self._jars = self._apply_jar_order(list(jars) + custom_jars)
        self._liabilities = liabilities

        if transactions:
            self._transactions = transactions
        elif (
            warning
            and self._current_session
            and self._current_session.cached_transactions
        ):
            warning = "виписка з кешу (ліміт API 60 сек.)"

        status_text = f"Підключено: {client_name}"
        if warning:
            status_text += f"  ({warning})"
        self._status_label.setText(status_text)

        if isinstance(source, MonobankApiAdapter) and self._remember_next_login:
            session = UserSession(
                client_name=client_name,
                token=source.token,
                strategy_index=self._strategy_combo.currentIndex(),
                gemini_api_key="",
                cached_jars=[j.to_dict() for j in self._jars],
                cached_liabilities=[d.to_dict() for d in self._liabilities],
                cached_transactions=[t.to_dict() for t in self._transactions],
                jar_order=list(self._jar_order),
                manual_savings=[m.to_dict() for m in self._manual_savings],
                cached_account_balance=self._mono_account_balance,
            )
            self._session_repo.save_session(session)
            self._current_session = session
            self._switch_to_authorized_ui(client_name)
        elif custom_jars or self._jar_order or self._manual_savings:
            self._persist_local_state()

        self._render_all()

    def _on_load_error(self, error_msg: str) -> None:
        self._set_controls_enabled(True)
        self._status_label.setText(f"Помилка: {error_msg}")

    def _on_strategy_changed(self, index: int) -> None:
        if index == 0:
            self._strategy = AvalancheStrategy()
        else:
            self._strategy = SnowballStrategy()

        if self._current_session:
            self._current_session.strategy_index = index
            self._session_repo.save_session(self._current_session)

        self._render_liabilities()

    def _render_all(self) -> None:
        self._render_jars(self._jars)
        self._render_savings_chart()
        self._render_liabilities()
        self._render_expenses(self._transactions)

    @classmethod
    def _clear_layout(cls, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                cls._clear_layout(item.layout())
                item.layout().deleteLater()

    def _render_jars(self, jars: List[SavingsJar]) -> None:
        self._clear_layout(self._jars_layout)
        if not jars:
            empty = QLabel("Активних банок поки немає. Натисніть «+», щоб створити власну.")
            empty.setObjectName("SubText")
            self._jars_layout.addWidget(empty)
        else:
            total = len(jars)
            for idx, jar in enumerate(jars):
                card = JarCardWidget(
                    jar,
                    is_first=(idx == 0),
                    is_last=(idx == total - 1),
                )
                card.move_up_requested.connect(self._on_move_jar_up)
                card.move_down_requested.connect(self._on_move_jar_down)
                card.top_up_requested.connect(self._on_top_up_custom_jar)
                card.delete_requested.connect(self._on_delete_custom_jar)
                self._jars_layout.addWidget(card)

        add_btn = AddJarButtonWidget()
        add_btn.clicked.connect(self._on_add_custom_jar)
        self._jars_layout.addWidget(add_btn)
        self._jars_layout.addStretch()

    def _render_savings_chart(self) -> None:
        mono_jars_sum = sum(
            j.current_balance for j in self._jars if not j.is_custom
        )
        custom_jars_sum = sum(
            j.current_balance for j in self._jars if j.is_custom
        )

        used_colors = [MONO_JARS_DEFAULT_COLOR, MONO_ACCOUNT_DEFAULT_COLOR]
        for m in self._manual_savings:
            if not m.color_hex:
                m.color_hex = pick_next_category_color(used_colors)
            used_colors.append(m.color_hex)

        slices: List[Tuple[str, float, str]] = [
            ("Банки Monobank (авто)", mono_jars_sum, MONO_JARS_DEFAULT_COLOR),
            ("Рахунок Monobank (авто)", self._mono_account_balance, MONO_ACCOUNT_DEFAULT_COLOR),
        ]

        for m in self._manual_savings:
            slices.append((m.title, m.amount, m.color_hex))

        if custom_jars_sum > 0:
            slices.append(("Власні цільові банки", custom_jars_sum, "#8B5CF6"))

        self._savings_pie.set_data(slices)

        self._clear_layout(self._legend_layout)
        total = sum(max(0.0, v) for _, v, _ in slices)

        for label_text, value, color_hex in slices:
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(8)

            dot = QLabel()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(
                f"background-color: {color_hex}; border-radius: 6px;"
            )

            name_lbl = QLabel(label_text)
            name_lbl.setStyleSheet("font-size: 13px; font-weight: 500; color: #F4F4F6;")

            pct = (value / total * 100.0) if total > 0 else 0.0
            val_lbl = QLabel(f"<b>{value:,.2f} ₴</b> ({pct:.1f}%)")
            val_lbl.setObjectName("SubText")

            row.addWidget(dot)
            row.addWidget(name_lbl)
            row.addStretch()
            row.addWidget(val_lbl)
            self._legend_layout.addWidget(row_widget)

        self._clear_layout(self._manual_savings_layout)
        if not self._manual_savings:
            empty = QLabel(
                "Ручних записів поки немає. Натисніть «+ Додати», щоб вказати накопичення в інших банках або готівкою."
            )
            empty.setObjectName("SubText")
            empty.setWordWrap(True)
            self._manual_savings_layout.addWidget(empty)
        else:
            for entry in self._manual_savings:
                card = ManualSavingCardWidget(entry, fallback_color="#3B82F6")
                card.edit_requested.connect(self._on_edit_manual_saving)
                card.delete_requested.connect(self._on_delete_manual_saving)
                card.color_change_requested.connect(self._on_manual_entry_color_changed)
                self._manual_savings_layout.addWidget(card)
        self._manual_savings_layout.addStretch()

    def _render_liabilities(self) -> None:
        self._clear_layout(self._debts_layout)
        if not self._liabilities:
            empty = QLabel("Кредитна заборгованість відсутня.")
            empty.setObjectName("SubText")
            self._debts_layout.addWidget(empty)
        else:
            sorted_debts = self._strategy.sort_liabilities(self._liabilities)
            for idx, debt in enumerate(sorted_debts, start=1):
                self._debts_layout.addWidget(LiabilityCardWidget(idx, debt))
        self._debts_layout.addStretch()

    def _render_expenses(self, transactions: List[Transaction]) -> None:
        self._clear_layout(self._categories_layout)

        category_totals: Dict[str, float] = {}
        total_spent = 0.0

        for tx in transactions:
            if tx.is_expense:
                amt = abs(tx.amount)
                total_spent += amt
                category_totals[tx.category] = (
                    category_totals.get(tx.category, 0.0) + amt
                )

        if not category_totals:
            lbl = QLabel("Немає даних про витрати за обраний період.")
            lbl.setObjectName("SubText")
            self._categories_layout.addWidget(lbl)
        else:
            for cat, amount in sorted(
                category_totals.items(), key=lambda x: x[1], reverse=True
            ):
                share = int((amount / total_spent) * 100) if total_spent > 0 else 0

                item_widget = QWidget()
                row = QVBoxLayout(item_widget)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(4)

                top = QHBoxLayout()
                name_lbl = QLabel(cat)
                name_lbl.setStyleSheet("font-size: 12px; font-weight: 500; color: #F4F4F6;")
                val_lbl = QLabel(f"{amount:,.2f} ₴ ({share}%)")
                val_lbl.setObjectName("SubText")
                top.addWidget(name_lbl)
                top.addStretch()
                top.addWidget(val_lbl)

                bar = QProgressBar()
                bar.setObjectName("DarkProgress")
                bar.setRange(0, 100)
                bar.setValue(share)
                bar.setTextVisible(False)
                bar.setFixedHeight(5)

                row.addLayout(top)
                row.addWidget(bar)
                self._categories_layout.addWidget(item_widget)

        self._total_spent_lbl.setText(f"Разом витрачено: {total_spent:,.2f} ₴")

        self._tx_table.setRowCount(len(transactions))
        for r, tx in enumerate(transactions):
            date_str = tx.timestamp.strftime("%d.%m %H:%M")
            sign = "+" if tx.amount > 0 else ""
            amount_item = QTableWidgetItem(f"{sign}{tx.amount:,.2f} ₴")
            amount_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            self._tx_table.setItem(r, 0, QTableWidgetItem(date_str))
            self._tx_table.setItem(r, 1, QTableWidgetItem(tx.description))
            self._tx_table.setItem(r, 2, QTableWidgetItem(tx.category))
            self._tx_table.setItem(r, 3, amount_item)