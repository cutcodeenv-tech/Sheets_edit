from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
except ImportError as exc:  # pragma: no cover - user environment specific
    raise SystemExit(
        "PyQt6 не установлен. Установите его командой 'pip install PyQt6' и повторите."
    ) from exc

from toolbox_core import PROJECT_ROOT, PYTHON, SCRIPTS, ScriptConfig, ScriptField


class GlassCard(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        effect = QtWidgets.QGraphicsDropShadowEffect(self)
        effect.setColor(QtGui.QColor(0, 0, 0, 120))
        effect.setOffset(0, 18)
        effect.setBlurRadius(42)
        self.setGraphicsEffect(effect)


class ToolboxWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Edit-from-Sheet Studio")
        self.resize(1120, 640)
        self.setMinimumSize(980, 560)
        self.setWindowIcon(QtGui.QIcon.fromTheme("applications-system"))

        self.selected_script: ScriptConfig = SCRIPTS[0]
        self.field_widgets: Dict[str, QtWidgets.QWidget] = {}
        self.process: Optional[QtCore.QProcess] = None

        self._build_ui()
        self._apply_style()
        self._populate_scripts()
        self._render_form()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        gradient = QtGui.QLinearGradient(0, 0, 0, 1)
        gradient.setCoordinateMode(QtGui.QGradient.CoordinateMode.ObjectMode)
        gradient.setColorAt(0.0, QtGui.QColor("#1c1d26"))
        gradient.setColorAt(1.0, QtGui.QColor("#090a10"))
        palette = central.palette()
        palette.setBrush(
            QtGui.QPalette.ColorRole.Window, QtGui.QBrush(gradient)
        )
        central.setAutoFillBackground(True)
        central.setPalette(palette)

        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Sidebar
        self.scene_list = QtWidgets.QListWidget()
        self.scene_list.setObjectName("SceneList")
        self.scene_list.setSpacing(6)
        self.scene_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scene_list.currentRowChanged.connect(self._on_script_change)
        self.scene_list.setMinimumWidth(210)
        self.scene_list.setMaximumWidth(240)
        self.scene_list.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.scene_list)

        # Right panel
        right_panel = QtWidgets.QVBoxLayout()
        right_panel.setSpacing(18)

        # Description card + form
        self.form_card = GlassCard()
        form_layout = QtWidgets.QVBoxLayout(self.form_card)
        form_layout.setContentsMargins(24, 24, 24, 24)
        form_layout.setSpacing(16)

        self.description_label = QtWidgets.QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setObjectName("DescriptionLabel")
        form_layout.addWidget(self.description_label)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll_content = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QFormLayout(self.scroll_content)
        self.scroll_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.scroll_layout.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.setVerticalSpacing(18)
        self.scroll_layout.setHorizontalSpacing(22)
        self.scroll_area.setWidget(self.scroll_content)
        form_layout.addWidget(self.scroll_area)

        right_panel.addWidget(self.form_card, 5)

        # Control row
        control_card = GlassCard()
        controls_layout = QtWidgets.QHBoxLayout(control_card)
        controls_layout.setContentsMargins(20, 16, 20, 16)
        controls_layout.setSpacing(12)

        self.run_button = QtWidgets.QPushButton("Запустить")
        self.run_button.clicked.connect(self.run_script)
        controls_layout.addWidget(self.run_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self.clear_button = QtWidgets.QPushButton("Очистить лог")
        self.clear_button.clicked.connect(self.clear_log)
        controls_layout.addWidget(self.clear_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        controls_layout.addItem(spacer)

        right_panel.addWidget(control_card, 0)

        # Log panel
        self.log_card = GlassCard()
        log_layout = QtWidgets.QVBoxLayout(self.log_card)
        log_layout.setContentsMargins(20, 16, 20, 20)
        log_layout.setSpacing(8)

        log_label = QtWidgets.QLabel("Лог")
        log_label.setObjectName("SectionLabel")
        log_layout.addWidget(log_label)

        self.log_output = QtWidgets.QPlainTextEdit()
        self.log_output.setObjectName("LogOutput")
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)

        right_panel.addWidget(self.log_card, 2)

        layout.addLayout(right_panel, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-family: "SF Pro Display";
                color: #f5f7ff;
                font-size: 14px;
            }
            #SceneList {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
                padding: 12px;
            }
            #SceneList::item {
                padding: 10px 14px;
                margin: 3px;
                border-radius: 12px;
            }
            #SceneList::item:selected {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(98,164,255,0.8), stop:1 rgba(139,92,246,0.9));
            }
            #GlassCard {
                background: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 26px;
            }
            QScrollArea {
                background: transparent;
            }
            QLineEdit, QComboBox {
                background: rgba(5, 6, 14, 0.55);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
                padding: 10px 14px;
            }
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #7b5bff, stop:1 #60a5fa);
                border: none;
                padding: 10px 24px;
                border-radius: 999px;
                font-weight: 600;
            }
            QPushButton:disabled {
                background: rgba(255,255,255,0.2);
            }
            QCheckBox {
                spacing: 12px;
            }
            QPlainTextEdit#LogOutput {
                background: rgba(5, 6, 14, 0.6);
                border-radius: 18px;
                padding: 12px;
            }
            QLabel#DescriptionLabel {
                color: rgba(245,247,255,0.85);
                font-size: 15px;
            }
            QLabel#SectionLabel {
                font-weight: 600;
                letter-spacing: 0.4px;
                margin-bottom: 4px;
            }
            """
        )

    def _populate_scripts(self) -> None:
        self.scene_list.clear()
        for cfg in SCRIPTS:
            item = QtWidgets.QListWidgetItem(cfg.title)
            self.scene_list.addItem(item)
        self.scene_list.setCurrentRow(0)

    def _on_script_change(self, index: int) -> None:
        if index < 0 or index >= len(SCRIPTS):
            return
        self.selected_script = SCRIPTS[index]
        self._render_form()

    def _render_form(self) -> None:
        while self.scroll_layout.rowCount():
            self.scroll_layout.removeRow(0)

        cfg = self.selected_script
        self.description_label.setText(cfg.description)
        self.field_widgets.clear()

        for field in cfg.fields:
            label = QtWidgets.QLabel(field.label)
            label.setWordWrap(True)

            if field.field_type == "bool":
                widget = QtWidgets.QCheckBox()
                widget.setChecked(field.default in {"1", True})
            elif field.field_type == "choice" and field.options:
                widget = QtWidgets.QComboBox()
                widget.addItems(field.options)
                widget.setCurrentText(field.default or field.options[0])
            else:
                wrapper = QtWidgets.QWidget()
                wrapper_layout = QtWidgets.QHBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(0, 0, 0, 0)
                wrapper_layout.setSpacing(8)
                line = QtWidgets.QLineEdit()
                line.setText(str(field.default or ""))
                wrapper_layout.addWidget(line)
                needs_picker = field.dialog_type or field.field_type in {"file", "dir"}
                if needs_picker:
                    picker_mode = field.dialog_type or field.field_type
                    browse = QtWidgets.QPushButton("Выбрать")
                    browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                    browse.setMinimumWidth(96)
                    browse.setMaximumWidth(120)
                    browse.clicked.connect(
                        lambda _, ln=line, fld=field, mode=picker_mode: self._open_dialog(ln, fld, mode)
                    )
                    wrapper_layout.addWidget(browse)
                widget = wrapper

            self.field_widgets[field.key] = widget
            self.scroll_layout.addRow(label, widget)

            if field.help_text:
                help_label = QtWidgets.QLabel(field.help_text)
                help_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
                help_label.setWordWrap(True)
                self.scroll_layout.addRow(QtWidgets.QLabel(""), help_label)

    def _open_dialog(self, line_edit: QtWidgets.QLineEdit, field: ScriptField, mode: str) -> None:
        initial_dir = line_edit.text().strip() or str(Path.home())
        path = ""
        if mode == "file":
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите файл", initial_dir)
        elif mode == "dir":
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Выберите папку", initial_dir)
        if path:
            line_edit.setText(path)

    def _collect_values(self) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for field in self.selected_script.fields:
            widget = self.field_widgets.get(field.key)
            if widget is None:
                continue
            if field.field_type == "bool":
                value = "1" if widget.isChecked() else "0"
            elif field.field_type == "choice" and isinstance(widget, QtWidgets.QComboBox):
                value = widget.currentText()
            else:
                line_edit = widget.findChild(QtWidgets.QLineEdit)
                line = line_edit if line_edit else widget
                value = line.text().strip()

            if field.field_type == "int" and value:
                if not value.lstrip("-").isdigit():
                    raise ValueError(f"Поле '{field.label}' должно быть числом.")
            if field.required and not value and field.field_type != "bool":
                raise ValueError(f"Поле '{field.label}' обязательно для заполнения.")
            values[field.key] = value
        return values

    def run_script(self) -> None:
        if self.process and self.process.state() == QtCore.QProcess.ProcessState.Running:
            QtWidgets.QMessageBox.information(self, "Выполнение", "Скрипт уже запущен.")
            return

        cfg = self.selected_script
        if not cfg.script_path.exists():
            QtWidgets.QMessageBox.critical(
                self, "Ошибка", f"Файл скрипта не найден:\n{cfg.script_path}"
            )
            return

        try:
            values = self._collect_values()
            args = cfg.args_builder(values) if cfg.args_builder else []
            stdin_payload = cfg.stdin_builder(values) if cfg.stdin_builder else None
        except ValueError as exc:
            QtWidgets.QMessageBox.critical(self, "Ошибка ввода", str(exc))
            return

        command_preview = " ".join([PYTHON, str(cfg.script_path), *args])
        self.append_log(f"$ {command_preview}\n")

        self.process = QtCore.QProcess(self)
        self.process.setProgram(PYTHON)
        self.process.setArguments([str(cfg.script_path), *args])
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.readyReadStandardError.connect(self._read_output)
        self.process.finished.connect(self._execution_finished)
        self.process.start()

        if stdin_payload:
            self.process.write(stdin_payload.encode("utf-8"))
            self.process.closeWriteChannel()

        self.run_button.setEnabled(False)

    def _read_output(self) -> None:
        if not self.process:
            return
        data = self.process.readAll().data().decode("utf-8", errors="ignore")
        if data:
            self.append_log(data)

    def _execution_finished(self, code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        self.append_log(f"\n[Завершено] Код возврата: {code}\n")
        self.run_button.setEnabled(True)

    def append_log(self, text: str) -> None:
        self.log_output.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self.log_output.insertPlainText(text)
        self.log_output.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def clear_log(self) -> None:
        self.log_output.clear()


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = ToolboxWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
