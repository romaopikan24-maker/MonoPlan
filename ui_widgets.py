from typing import List, Optional, Tuple
import webbrowser

from PyQt6.QtCore import QRectF, QRegularExpression, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QRegularExpressionValidator,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_advisor import ChatMessage
from bank_api import MonobankApiAdapter
from models import CreditLiability, ManualSavingEntry, SavingsJar


CATEGORY_COLOR_PALETTE: List[str] = [
    "#2563EB",  # Синій
    "#F59E0B",  # Помаранчевий
    "#8B5CF6",  # Фіолетовий
    "#EC4899",  # Рожевий
    "#06B6D4",  # Бірюзовий
    "#EF4444",  # Червоний
    "#14B8A6",  # Смарагдовий
    "#6366F1",  # Індиго
    "#84CC16",  # Лаймовий
    "#F97316",  # Яскраво-помаранчевий
]

MONO_JARS_DEFAULT_COLOR = "#10B981"
MONO_ACCOUNT_DEFAULT_COLOR = "#111827"


def pick_next_category_color(used_colors: List[str]) -> str:
    """Автоматично підбирає наступний невикористаний колір із палітри."""
    normalized_used = {c.strip().upper() for c in used_colors if c}
    for hex_color in CATEGORY_COLOR_PALETTE:
        if hex_color.upper() not in normalized_used:
            return hex_color
    return CATEGORY_COLOR_PALETTE[len(used_colors) % len(CATEGORY_COLOR_PALETTE)]


MINIMALIST_QSS = """
QMainWindow, QDialog, QWidget#Root {
    background-color: #F7F8FA;
    font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
    color: #111827;
}
QWidget#ChatContainer {
    background-color: #FFFFFF;
}
QFrame#TopBar, QFrame#Card {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
}
QFrame#UserBubble {
    background-color: #111827;
    border-radius: 14px;
}
QFrame#AssistantBubble {
    background-color: #F3F4F6;
    border: 1px solid #E5E7EB;
    border-radius: 14px;
}
QLabel#UserBubbleText {
    font-size: 13px;
    color: #FFFFFF;
}
QLabel#UserBubbleMeta {
    font-size: 11px;
    color: #9CA3AF;
}
QLabel#AssistantBubbleText {
    font-size: 13px;
    color: #111827;
}
QLabel#AppTitle {
    font-size: 18px;
    font-weight: 700;
    color: #111827;
}
QLabel#SectionTitle {
    font-size: 14px;
    font-weight: 600;
    color: #374151;
}
QLabel#CardTitle {
    font-size: 14px;
    font-weight: 600;
    color: #111827;
}
QLabel#SubText {
    font-size: 12px;
    color: #6B7280;
}
QLabel#StatusBanner {
    font-size: 12px;
    color: #4B5563;
    padding: 4px 10px;
    background-color: #F3F4F6;
    border-radius: 6px;
}
QLabel#BadgeGreen {
    font-size: 12px;
    font-weight: 600;
    color: #059669;
    background-color: #ECFDF5;
    padding: 4px 10px;
    border-radius: 6px;
}
QLabel#BadgeCustom {
    font-size: 11px;
    font-weight: 600;
    color: #2563EB;
    background-color: #EFF6FF;
    padding: 2px 8px;
    border-radius: 6px;
}
QLabel#BadgeMono {
    font-size: 11px;
    font-weight: 700;
    color: #111827;
    background-color: #F3F4F6;
    padding: 2px 8px;
    border-radius: 6px;
}
QLabel#BadgeCash {
    font-size: 11px;
    font-weight: 600;
    color: #B45309;
    background-color: #FEF3C7;
    padding: 2px 8px;
    border-radius: 6px;
}
QLabel#PriorityBadge {
    font-size: 13px;
    font-weight: 700;
    color: #111827;
    background-color: #F3F4F6;
    border-radius: 8px;
}
QLabel#DebtAmount {
    font-size: 15px;
    font-weight: 700;
    color: #DC2626;
}
QCheckBox {
    font-size: 12px;
    color: #374151;
    spacing: 6px;
}
QLineEdit, QDoubleSpinBox {
    background-color: #F9FAFB;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    color: #111827;
}
QLineEdit:focus, QDoubleSpinBox:focus {
    border: 1px solid #111827;
    background-color: #FFFFFF;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 0px;
    height: 0px;
    border: none;
}
QPushButton#PrimaryBtn {
    background-color: #111827;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#PrimaryBtn:hover {
    background-color: #374151;
}
QPushButton#PrimaryBtn:disabled {
    background-color: #9CA3AF;
}
QPushButton#SecondaryBtn {
    background-color: #FFFFFF;
    color: #374151;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton#SecondaryBtn:hover {
    background-color: #F3F4F6;
}
QPushButton#DangerBtn {
    background-color: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FECACA;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#DangerBtn:hover {
    background-color: #FEE2E2;
}
QPushButton#IconBtn {
    background-color: #F9FAFB;
    color: #374151;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    padding: 0px 8px;
}
QPushButton#IconBtn:hover {
    background-color: #E5E7EB;
    color: #111827;
}
QPushButton#IconBtn:disabled {
    color: #D1D5DB;
    background-color: #F9FAFB;
}
QPushButton#IconDangerBtn {
    background-color: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FECACA;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    padding: 0px 6px;
}
QPushButton#IconDangerBtn:hover {
    background-color: #FEE2E2;
}
QPushButton#AddJarBtn {
    background-color: #FFFFFF;
    color: #4B5563;
    border: 2px dashed #D1D5DB;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 600;
    padding: 12px;
}
QPushButton#AddJarBtn:hover {
    background-color: #F9FAFB;
    border-color: #111827;
    color: #111827;
}
QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
    color: #111827;
}
QProgressBar#GreenProgress {
    background-color: #E5E7EB;
    border: none;
    border-radius: 3px;
}
QProgressBar#GreenProgress::chunk {
    background-color: #10B981;
    border-radius: 3px;
}
QProgressBar#DarkProgress {
    background-color: #E5E7EB;
    border: none;
    border-radius: 3px;
}
QProgressBar#DarkProgress::chunk {
    background-color: #111827;
    border-radius: 3px;
}
QTabWidget::pane {
    border: none;
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #6B7280;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 600;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #111827;
    border-bottom: 2px solid #111827;
}
QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    gridline-color: #F3F4F6;
    font-size: 13px;
}
QHeaderView::section {
    background-color: #F9FAFB;
    color: #6B7280;
    font-weight: 600;
    font-size: 12px;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #E5E7EB;
}
QScrollArea {
    border: none;
    background: transparent;
}
"""


def _format_initial_number(value: float) -> str:
    """Форматує початкове число без зайвих нулів після крапки для зручного редагування."""
    if value == 0:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _parse_amount(text: str, default: float = 0.0) -> float:
    """Безпечно парсить ціле або дробове число (з крапкою чи комою)."""
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    if not cleaned or cleaned in {"-", "+", ".", "-.", "+."}:
        return default
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return default


class SavingsPieChartWidget(QWidget):
    """Кільцева (кругова) діаграма структури накопичень на базі QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 250)
        self._slices: List[Tuple[str, float, str]] = []

    def set_data(self, slices: List[Tuple[str, float, str]]) -> None:
        self._slices = slices
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        diameter = min(w, h) - 24
        if diameter < 80:
            return

        rect = QRectF(
            (w - diameter) / 2.0,
            (h - diameter) / 2.0,
            diameter,
            diameter,
        )

        total = sum(max(0.0, val) for _, val, _ in self._slices)

        if total <= 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#E5E7EB"))
            painter.drawEllipse(rect)

            inner_margin = diameter * 0.27
            inner_rect = rect.adjusted(
                inner_margin, inner_margin, -inner_margin, -inner_margin
            )
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(inner_rect)

            painter.setPen(QColor("#6B7280"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            painter.drawText(
                inner_rect,
                Qt.AlignmentFlag.AlignCenter,
                "0.00 ₴\nНемає даних",
            )
            return

        start_angle_16 = 90 * 16
        active_slices = [(lbl, val, col) for lbl, val, col in self._slices if val > 0]

        for idx, (_, val, color_hex) in enumerate(active_slices):
            if idx == len(active_slices) - 1:
                span_angle_16 = (90 * 16 - 360 * 16) - start_angle_16
            else:
                span_angle_16 = -int(round((val / total) * 360 * 16))

            painter.setBrush(QColor(color_hex))
            if len(active_slices) > 1:
                painter.setPen(QPen(QColor("#FFFFFF"), 2.0))
            else:
                painter.setPen(Qt.PenStyle.NoPen)

            painter.drawPie(rect, start_angle_16, span_angle_16)
            start_angle_16 += span_angle_16

        inner_margin = diameter * 0.27
        inner_rect = rect.adjusted(
            inner_margin, inner_margin, -inner_margin, -inner_margin
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(inner_rect)

        painter.setPen(QColor("#6B7280"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        top_text_rect = QRectF(
            inner_rect.left(),
            inner_rect.top() + inner_rect.height() * 0.24,
            inner_rect.width(),
            inner_rect.height() * 0.22,
        )
        painter.drawText(top_text_rect, Qt.AlignmentFlag.AlignCenter, "Усього накопичено")

        painter.setPen(QColor("#111827"))
        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        val_text_rect = QRectF(
            inner_rect.left() + 4,
            inner_rect.top() + inner_rect.height() * 0.44,
            inner_rect.width() - 8,
            inner_rect.height() * 0.30,
        )
        painter.drawText(
            val_text_rect,
            Qt.AlignmentFlag.AlignCenter,
            f"{total:,.2f} ₴",
        )


class ManualSavingDialog(QDialog):
    """Діалог додавання або редагування накопичень з вибором кольору."""

    def __init__(
        self,
        existing: Optional[ManualSavingEntry] = None,
        used_colors: Optional[List[str]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "Редагувати накопичення" if existing else "Додати накопичення"
        )
        self.setFixedWidth(400)

        self.category_type: str = existing.category_type if existing else "other_bank"
        self.entry_title: str = existing.title if existing else ""
        self.amount_value: float = existing.amount if existing else 0.0
        self.color_hex: str = (
            existing.color_hex
            if (existing and getattr(existing, "color_hex", ""))
            else pick_next_category_color(used_colors or [])
        )

        self._swatch_buttons: List[Tuple[str, QPushButton]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        header = QLabel(
            "Редагувати запис" if existing else "Нове накопичення"
        )
        header.setObjectName("AppTitle")
        layout.addWidget(header)

        type_lbl = QLabel("Джерело зберігання:")
        type_lbl.setObjectName("SectionTitle")
        self._type_combo = QComboBox()
        self._type_combo.addItem("Інші банки (картка / депозит)", "other_bank")
        self._type_combo.addItem("Готівка", "cash")
        if existing and existing.category_type == "cash":
            self._type_combo.setCurrentIndex(1)
        layout.addWidget(type_lbl)
        layout.addWidget(self._type_combo)

        title_lbl = QLabel("Назва або примітка:")
        title_lbl.setObjectName("SectionTitle")
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText(
            "Наприклад: ПриватБанк або Готівка вдома"
        )
        if existing:
            self._title_edit.setText(existing.title)
        layout.addWidget(title_lbl)
        layout.addWidget(self._title_edit)

        amount_lbl = QLabel("Сума накопичень (у гривнях):")
        amount_lbl.setObjectName("SectionTitle")
        self._amount_edit = QLineEdit()
        self._amount_edit.setPlaceholderText("Наприклад: 15000")
        amount_regex = QRegularExpression(r"^\d{0,10}([.,]\d{0,2})?$")
        self._amount_edit.setValidator(
            QRegularExpressionValidator(amount_regex, self._amount_edit)
        )
        if existing:
            self._amount_edit.setText(_format_initial_number(existing.amount))
        layout.addWidget(amount_lbl)
        layout.addWidget(self._amount_edit)

        color_lbl = QLabel("Колір на діаграмі:")
        color_lbl.setObjectName("SectionTitle")
        layout.addWidget(color_lbl)

        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        for hex_code in CATEGORY_COLOR_PALETTE[:8]:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(hex_code)
            btn.clicked.connect(lambda _, c=hex_code: self._set_selected_color(c))
            color_row.addWidget(btn)
            self._swatch_buttons.append((hex_code, btn))

        color_row.addStretch()

        self._custom_color_btn = QPushButton("Свій...")
        self._custom_color_btn.setObjectName("SecondaryBtn")
        self._custom_color_btn.setFixedHeight(26)
        self._custom_color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._custom_color_btn.clicked.connect(self._open_color_picker)
        color_row.addWidget(self._custom_color_btn)

        layout.addLayout(color_row)
        self._refresh_color_swatches()

        btns = QHBoxLayout()
        cancel_btn = QPushButton("Скасувати")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Зберегти")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.clicked.connect(self._on_save)

        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

    def _set_selected_color(self, hex_code: str) -> None:
        self.color_hex = QColor(hex_code).name().upper()
        self._refresh_color_swatches()

    def _open_color_picker(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self.color_hex),
            self,
            "Оберіть колір категорії",
        )
        if chosen.isValid():
            self._set_selected_color(chosen.name())

    def _refresh_color_swatches(self) -> None:
        selected_upper = self.color_hex.upper()
        for hex_code, btn in self._swatch_buttons:
            is_selected = hex_code.upper() == selected_upper
            border = "2.5px solid #111827" if is_selected else "1px solid #D1D5DB"
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_code}; border: {border}; border-radius: 12px; padding: 0px; }}"
            )
        self._custom_color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self.color_hex}; color: #FFFFFF; "
            f"border: 1px solid #111827; border-radius: 8px; padding: 2px 10px; font-weight: 600; font-size: 11px; }}"
        )

    def _on_save(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            self._title_edit.setPlaceholderText("Введіть назву!")
            self._title_edit.setFocus()
            return
        raw_amount = self._amount_edit.text().strip()
        if not raw_amount:
            self._amount_edit.setPlaceholderText("Введіть суму!")
            self._amount_edit.setFocus()
            return
        self.category_type = str(self._type_combo.currentData())
        self.entry_title = title
        self.amount_value = max(0.0, _parse_amount(raw_amount, 0.0))
        self.accept()


class ManualSavingCardWidget(QFrame):
    """Картка ручного накопичення з кольоровим індикатором та можливістю швидкої зміни кольору."""

    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    color_change_requested = pyqtSignal(str, str)  # (entry_id, new_hex)

    def __init__(self, entry: ManualSavingEntry, fallback_color: str = "#2563EB"):
        super().__init__()
        self.setObjectName("Card")
        self._entry_id = entry.entry_id
        self._color_hex = getattr(entry, "color_hex", "") or fallback_color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        self._color_dot_btn = QPushButton()
        self._color_dot_btn.setFixedSize(18, 18)
        self._color_dot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_dot_btn.setToolTip("Натисніть, щоб змінити колір на діаграмі")
        self._apply_dot_style()
        self._color_dot_btn.clicked.connect(self._pick_new_color)
        layout.addWidget(self._color_dot_btn)

        title_lbl = QLabel(entry.title)
        title_lbl.setObjectName("CardTitle")
        layout.addWidget(title_lbl)

        badge = QLabel(
            "Інший банк" if entry.category_type == "other_bank" else "Готівка"
        )
        badge.setObjectName(
            "BadgeCustom" if entry.category_type == "other_bank" else "BadgeCash"
        )
        layout.addWidget(badge)

        layout.addStretch()

        amount_lbl = QLabel(f"{entry.amount:,.2f} ₴")
        amount_lbl.setObjectName("CardTitle")
        layout.addWidget(amount_lbl)

        edit_btn = QPushButton("Змінити")
        edit_btn.setObjectName("IconBtn")
        edit_btn.setFixedHeight(26)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(entry.entry_id))
        layout.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("IconDangerBtn")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Видалити запис")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(entry.entry_id))
        layout.addWidget(del_btn)

    def _apply_dot_style(self) -> None:
        self._color_dot_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self._color_hex}; border: 1.5px solid #D1D5DB; border-radius: 9px; padding: 0px; }}"
            f"QPushButton:hover {{ border: 2px solid #111827; }}"
        )

    def _pick_new_color(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self._color_hex),
            self,
            "Оберіть новий колір категорії",
        )
        if chosen.isValid():
            self._color_hex = chosen.name().upper()
            self._apply_dot_style()
            self.color_change_requested.emit(self._entry_id, self._color_hex)


class QrAuthDialog(QDialog):
    """Модальне вікно швидкої авторизації через портал Monobank."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Підключення Monobank API")
        self.setFixedWidth(420)
        self.token_value: str = ""
        self.remember_me: bool = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Підключення Monobank")
        title.setObjectName("AppTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "1. Натисніть кнопку нижче — відкриється портал api.monobank.ua.\n"
            "2. Відскануйте QR-код з екрана монітора у додатку Monobank та підтвердьте вхід.\n"
            "3. Скопіюйте токен на сайті та вставте його сюди."
        )
        subtitle.setObjectName("SubText")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        open_web_btn = QPushButton("1. Відкрити api.monobank.ua у браузері")
        open_web_btn.setObjectName("PrimaryBtn")
        open_web_btn.clicked.connect(
            lambda: webbrowser.open(MonobankApiAdapter.PORTAL_URL)
        )
        layout.addWidget(open_web_btn)

        token_row = QHBoxLayout()
        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("2. Вставте отриманий X-Token...")
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)

        paste_btn = QPushButton("Вставити")
        paste_btn.setObjectName("SecondaryBtn")
        paste_btn.clicked.connect(self._paste_from_clipboard)

        token_row.addWidget(self._token_edit, stretch=1)
        token_row.addWidget(paste_btn)
        layout.addLayout(token_row)

        self._remember_cb = QCheckBox("Запам'ятати мене на цьому комп'ютері")
        self._remember_cb.setChecked(True)
        layout.addWidget(self._remember_cb)

        btns = QHBoxLayout()
        cancel_btn = QPushButton("Скасувати")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        submit_btn = QPushButton("Увійти")
        submit_btn.setObjectName("PrimaryBtn")
        submit_btn.clicked.connect(self._on_submit)

        btns.addWidget(cancel_btn)
        btns.addWidget(submit_btn)
        layout.addLayout(btns)

    def _paste_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            text = clipboard.text().strip()
            if text:
                self._token_edit.setText(text)

    def _on_submit(self) -> None:
        token = self._token_edit.text().strip()
        if not token:
            self._token_edit.setPlaceholderText("Спочатку вставте X-Token!")
            return
        self.token_value = token
        self.remember_me = self._remember_cb.isChecked()
        self.accept()


class CustomJarDialog(QDialog):
    """Модальне вікно створення власної накопичувальної банки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Нова власна банка")
        self.setFixedWidth(380)

        self.jar_title: str = ""
        self.current_balance: float = 0.0
        self.goal_amount: float = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        header = QLabel("Створити власну банку")
        header.setObjectName("AppTitle")
        layout.addWidget(header)

        sub = QLabel("Власні цілі зберігаються локально незалежно від банок Monobank.")
        sub.setObjectName("SubText")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        title_lbl = QLabel("Назва цілі:")
        title_lbl.setObjectName("SectionTitle")
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Наприклад: Нова гума або Резервний фонд")
        layout.addWidget(title_lbl)
        layout.addWidget(self._title_edit)

        amount_regex = QRegularExpression(r"^\d{0,10}([.,]\d{0,2})?$")

        saved_lbl = QLabel("Вже накопичено (₴):")
        saved_lbl.setObjectName("SectionTitle")
        self._saved_edit = QLineEdit()
        self._saved_edit.setPlaceholderText("0")
        self._saved_edit.setValidator(
            QRegularExpressionValidator(amount_regex, self._saved_edit)
        )
        layout.addWidget(saved_lbl)
        layout.addWidget(self._saved_edit)

        goal_lbl = QLabel("Цільова сума (₴, порожньо або 0 — без ліміту):")
        goal_lbl.setObjectName("SectionTitle")
        self._goal_edit = QLineEdit()
        self._goal_edit.setPlaceholderText("5000")
        self._goal_edit.setText("5000")
        self._goal_edit.setValidator(
            QRegularExpressionValidator(amount_regex, self._goal_edit)
        )
        layout.addWidget(goal_lbl)
        layout.addWidget(self._goal_edit)

        btns = QHBoxLayout()
        cancel_btn = QPushButton("Скасувати")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        create_btn = QPushButton("Створити")
        create_btn.setObjectName("PrimaryBtn")
        create_btn.clicked.connect(self._on_create)

        btns.addWidget(cancel_btn)
        btns.addWidget(create_btn)
        layout.addLayout(btns)

    def _on_create(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            self._title_edit.setPlaceholderText("Введіть назву цілі!")
            self._title_edit.setFocus()
            return
        self.jar_title = title
        self.current_balance = max(0.0, _parse_amount(self._saved_edit.text(), 0.0))
        self.goal_amount = max(0.0, _parse_amount(self._goal_edit.text(), 0.0))
        self.accept()


class TopUpJarDialog(QDialog):
    """Діалог поповнення або коригування суми власної банки."""

    def __init__(self, jar: SavingsJar, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Зміна балансу — {jar.title}")
        self.setFixedWidth(360)
        self.delta_amount: float = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel(jar.title)
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        info = QLabel(
            f"Поточний баланс: <b>{jar.current_balance:,.2f} ₴</b>\n"
            "Введіть суму поповнення (або зі знаком мінус для зняття):"
        )
        info.setObjectName("SubText")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._amount_edit = QLineEdit()
        self._amount_edit.setPlaceholderText("500")
        self._amount_edit.setText("500")
        signed_regex = QRegularExpression(r"^-?\d{0,10}([.,]\d{0,2})?$")
        self._amount_edit.setValidator(
            QRegularExpressionValidator(signed_regex, self._amount_edit)
        )
        layout.addWidget(self._amount_edit)

        btns = QHBoxLayout()
        cancel_btn = QPushButton("Скасувати")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton("Застосувати")
        apply_btn.setObjectName("PrimaryBtn")
        apply_btn.clicked.connect(self._on_apply)

        btns.addWidget(cancel_btn)
        btns.addWidget(apply_btn)
        layout.addLayout(btns)

    def _on_apply(self) -> None:
        self.delta_amount = _parse_amount(self._amount_edit.text(), 0.0)
        self.accept()


class AddJarButtonWidget(QPushButton):
    """Кнопка '+' під списком банок для додавання власної цілі."""

    def __init__(self, parent=None):
        super().__init__("+   Додати власну банку", parent)
        self.setObjectName("AddJarBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(52)


class JarCardWidget(QFrame):
    """Мінімалістична картка накопичувальної 'Банки' з кнопками сортування."""

    move_up_requested = pyqtSignal(str)
    move_down_requested = pyqtSignal(str)
    top_up_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(
        self,
        jar: SavingsJar,
        is_first: bool = False,
        is_last: bool = False,
    ):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)

        title_lbl = QLabel(jar.title)
        title_lbl.setObjectName("CardTitle")
        header.addWidget(title_lbl)

        if jar.is_custom:
            source_badge = QLabel("Власна")
            source_badge.setObjectName("BadgeCustom")
        else:
            source_badge = QLabel("mono")
            source_badge.setObjectName("BadgeMono")
        header.addWidget(source_badge)

        header.addStretch()

        if jar.is_custom:
            top_up_btn = QPushButton("+ ₴")
            top_up_btn.setObjectName("IconBtn")
            top_up_btn.setFixedHeight(26)
            top_up_btn.setToolTip("Поповнити або змінити баланс")
            top_up_btn.clicked.connect(
                lambda: self.top_up_requested.emit(jar.item_id)
            )
            header.addWidget(top_up_btn)

            del_btn = QPushButton("✕")
            del_btn.setObjectName("IconDangerBtn")
            del_btn.setFixedSize(26, 26)
            del_btn.setToolTip("Видалити власну банку")
            del_btn.clicked.connect(
                lambda: self.delete_requested.emit(jar.item_id)
            )
            header.addWidget(del_btn)

        up_btn = QPushButton("▲")
        up_btn.setObjectName("IconBtn")
        up_btn.setFixedSize(26, 26)
        up_btn.setEnabled(not is_first)
        up_btn.setToolTip("Перемістити вище")
        up_btn.clicked.connect(lambda: self.move_up_requested.emit(jar.item_id))
        header.addWidget(up_btn)

        down_btn = QPushButton("▼")
        down_btn.setObjectName("IconBtn")
        down_btn.setFixedSize(26, 26)
        down_btn.setEnabled(not is_last)
        down_btn.setToolTip("Перемістити нижче")
        down_btn.clicked.connect(
            lambda: self.move_down_requested.emit(jar.item_id)
        )
        header.addWidget(down_btn)

        percent = jar.get_progress_percent()
        pct_lbl = QLabel(f"{percent}%")
        pct_lbl.setObjectName("BadgeGreen")
        header.addWidget(pct_lbl)

        layout.addLayout(header)

        progress = QProgressBar()
        progress.setObjectName("GreenProgress")
        progress.setRange(0, 100)
        progress.setValue(percent)
        progress.setTextVisible(False)
        progress.setFixedHeight(6)
        layout.addWidget(progress)

        footer = QHBoxLayout()
        if jar.goal_amount > 0:
            amounts_text = (
                f"Накопичено: <b>{jar.current_balance:,.2f} ₴</b> з {jar.goal_amount:,.2f} ₴"
            )
            rem_text = f"Залишилось: {jar.get_remaining_amount():,.2f} ₴"
        else:
            amounts_text = f"Накопичено: <b>{jar.current_balance:,.2f} ₴</b>"
            rem_text = "Без цільового ліміту"

        lbl_left = QLabel(amounts_text)
        lbl_left.setObjectName("SubText")
        lbl_right = QLabel(rem_text)
        lbl_right.setObjectName("SubText")

        footer.addWidget(lbl_left)
        footer.addStretch()
        footer.addWidget(lbl_right)
        layout.addLayout(footer)


class LiabilityCardWidget(QFrame):
    """Мінімалістична картка кредитного зобов'язання з пріоритетом."""

    def __init__(self, priority: int, liability: CreditLiability):
        super().__init__()
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        rank_lbl = QLabel(f"#{priority}")
        rank_lbl.setObjectName("PriorityBadge")
        rank_lbl.setFixedSize(32, 32)
        rank_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(rank_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        title_lbl = QLabel(liability.title)
        title_lbl.setObjectName("CardTitle")
        sub_lbl = QLabel(
            f"Ставка: {liability.annual_rate}% річних  •  Ліміт: {liability.credit_limit:,.0f} ₴"
        )
        sub_lbl.setObjectName("SubText")
        info_layout.addWidget(title_lbl)
        info_layout.addWidget(sub_lbl)
        layout.addLayout(info_layout)

        layout.addStretch()

        debt_lbl = QLabel(f"-{liability.get_remaining_amount():,.2f} ₴")
        debt_lbl.setObjectName("DebtAmount")
        layout.addWidget(debt_lbl)


class ChatBubbleWidget(QWidget):
    """Мінімалістична бульбашка повідомлення в чаті (користувач праворуч, AI ліворуч)."""

    def __init__(self, message: ChatMessage):
        super().__init__()
        is_user = message.role == "user"

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)

        bubble = QFrame()
        bubble.setObjectName("UserBubble" if is_user else "AssistantBubble")
        bubble.setMaximumWidth(620)

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        bubble_layout.setSpacing(4)

        header_lbl = QLabel(
            f"{'Ви' if is_user else 'MonoPlan AI'}  •  {message.timestamp.strftime('%H:%M')}"
        )
        header_lbl.setObjectName("UserBubbleMeta" if is_user else "SubText")

        body_lbl = QLabel(message.text)
        body_lbl.setObjectName("UserBubbleText" if is_user else "AssistantBubbleText")
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        bubble_layout.addWidget(header_lbl)
        bubble_layout.addWidget(body_lbl)

        if is_user:
            outer.addStretch()
            outer.addWidget(bubble)
        else:
            outer.addWidget(bubble)
            outer.addStretch()