import sys
import os
import base64
import zipfile
import io

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QTextEdit,
    QLabel,
    QMessageBox,
    QGroupBox,
    QHBoxLayout,
)
from PyQt5.QtCore import Qt


def resource_path(relative_path):
    """Get absolute path of resource file (supporting PyInstaller packaged environment)."""
    if hasattr(sys, "_MEIPASS"):
        # After PyInstaller packaging, the temporary folder exists in sys._MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# --- Constants and QSS Style ---
QSS_STYLE = """
    QWidget {
        background-color: #2e2e2e;
        color: #f0f0f0;
        font-family: "Microsoft JhengHei";
        font-size: 14px;
    }
    QPushButton {
        background-color: #444;
        color: white;
        padding: 8px 16px;
        border-radius: 6px;
    }
    QPushButton:disabled {
        background-color: #222;
        color: #888;
    }
    QPushButton:hover:!disabled {
        background-color: #666;
    }
    QPushButton#CopyButton {
        padding: 4px 12px;
        font-size: 12px;
        font-weight: bold;
    }
    QTextEdit {
        background-color: #1e1e1e;
        color: #f0f0f0;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 4px;
    }
    QLabel {
        font-weight: bold;
    }
    QGroupBox {
        border: 1px solid #555;
        border-radius: 4px;
        margin-top: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top center;
        padding: 0 3px;
    }
"""


# --- Core Functions (Text) ---
def encode_text_to_base64(text: str) -> str:
    """Encode text to Base64 string."""
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def decode_base64_to_text(base64_str: str) -> str:
    """Decode Base64 string to text, ignoring errors."""
    try:
        return base64.b64decode(base64_str.encode("utf-8")).decode(
            "utf-8", errors="ignore"
        )
    except base64.binascii.Error:
        return ""


# --- Recursive ZIP Tool ---
def add_to_zip(zipf, path, base_path=""):
    """Recursively add files or folders to ZIP."""
    if os.path.isfile(path):
        arcname = os.path.join(base_path, os.path.basename(path))
        zipf.write(path, arcname)
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, os.path.dirname(path))
                zipf.write(abs_path, rel_path)


# --- PyQt5 GUI ---
class Base64Tool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Base64 Studio")
        self.setMinimumSize(700, 600)
        self._init_ui()
        from PyQt5.QtGui import QIcon

        self.setWindowIcon(QIcon(resource_path("icon.ico")))

    def _init_ui(self):
        """Initialize UI components."""
        main_layout = QVBoxLayout()

        # Input Area
        main_layout.addWidget(QLabel("Input Area: (Enter text or Base64 string)"))
        self.text_input = QTextEdit()
        self.text_input.textChanged.connect(self._on_text_changed)
        main_layout.addWidget(self.text_input)

        # Base64 Output Area
        b64_output_header_layout = QHBoxLayout()
        b64_output_header_layout.addWidget(QLabel("Base64 Encoded Output:"))
        b64_output_header_layout.addStretch()
        btn_copy_b64 = QPushButton("Copy")
        btn_copy_b64.setObjectName("CopyButton")
        btn_copy_b64.clicked.connect(self._copy_b64_output)
        b64_output_header_layout.addWidget(btn_copy_b64)
        main_layout.addLayout(b64_output_header_layout)
        self.output_b64 = QTextEdit()
        self.output_b64.setReadOnly(True)
        main_layout.addWidget(self.output_b64)

        # Decoded Text Output Area
        text_output_header_layout = QHBoxLayout()
        text_output_header_layout.addWidget(QLabel("Decoded Text Output:"))
        text_output_header_layout.addStretch()
        btn_copy_text = QPushButton("Copy")
        btn_copy_text.setObjectName("CopyButton")
        btn_copy_text.clicked.connect(self._copy_text_output)
        text_output_header_layout.addWidget(btn_copy_text)
        main_layout.addLayout(text_output_header_layout)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        main_layout.addWidget(self.output_text)

        # Status Label
        self.status_label = QLabel("Ready...")
        main_layout.addWidget(self.status_label)

        # File Operations
        file_group = QGroupBox("File Compression and Decoding")
        file_layout = QHBoxLayout()

        btn_files_to_b64 = QPushButton("Select Files → ZIP → Base64")
        btn_files_to_b64.clicked.connect(self._files_to_base64_zip)
        file_layout.addWidget(btn_files_to_b64)

        btn_folders_to_b64 = QPushButton("Select Folder → ZIP → Base64")
        btn_folders_to_b64.clicked.connect(self._folders_to_base64_zip)
        file_layout.addWidget(btn_folders_to_b64)

        btn_b64_to_file = QPushButton("Base64 → Decode to File...")
        btn_b64_to_file.clicked.connect(self._handle_base64_to_file)
        file_layout.addWidget(btn_b64_to_file)

        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        self.setLayout(main_layout)

    def _copy_b64_output(self):
        """Copy Base64 output content to clipboard."""
        content = self.output_b64.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self.status_label.setText("Base64 output copied to clipboard!")
        else:
            self.status_label.setText("Base64 output is empty, nothing to copy.")

    def _copy_text_output(self):
        """Copy decoded text output content to clipboard."""
        content = self.output_text.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self.status_label.setText("Decoded text output copied to clipboard!")
        else:
            self.status_label.setText("Decoded text output is empty, nothing to copy.")

    def _on_text_changed(self):
        """Update outputs in real time based on input content."""
        input_text = self.text_input.toPlainText().strip()
        if not input_text:
            self.output_b64.clear()
            self.output_text.clear()
            self.status_label.setText("Ready...")
            return

        self.output_b64.setText(encode_text_to_base64(input_text))
        self.output_text.setText(decode_base64_to_text(input_text))
        self.status_label.setText("Real-time conversion completed")

    def _handle_base64_to_file(self):
        """Base64 → ZIP file or extract directly."""
        base64_str = self.text_input.toPlainText().strip()
        if not base64_str:
            QMessageBox.warning(
                self, "Error", "Please paste Base64 string into the input area."
            )
            return

        try:
            zip_data = base64.b64decode(base64_str.encode("utf-8"))
            if not zipfile.is_zipfile(io.BytesIO(zip_data)):
                QMessageBox.warning(
                    self, "Format Error", "The content is not a valid ZIP file."
                )
                self.status_label.setText("Verification failed: Not a ZIP format")
                return

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("Choose Action")
            msg_box.setText(
                "Valid ZIP archive detected. How would you like to proceed?"
            )

            btn_save_zip = msg_box.addButton("Save as ZIP file", QMessageBox.ActionRole)
            btn_extract = msg_box.addButton(
                "Extract directly to folder", QMessageBox.ActionRole
            )
            btn_cancel = msg_box.addButton("Cancel", QMessageBox.RejectRole)

            msg_box.exec_()
            clicked_button = msg_box.clickedButton()
            if clicked_button == btn_save_zip:
                self._save_zip_from_data(zip_data)
            elif clicked_button == btn_extract:
                self._extract_zip_from_data(zip_data)
            else:
                self.status_label.setText("Operation canceled")

        except base64.binascii.Error:
            QMessageBox.critical(
                self, "Decoding Error", "The input is not valid Base64."
            )
            self.status_label.setText("Decoding failed")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unknown error:\n{str(e)}")

    def _save_zip_from_data(self, zip_data: bytes):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save as ZIP File", "", "ZIP Files (*.zip);;All Files (*)"
        )
        if not save_path:
            self.status_label.setText("Save operation canceled")
            return
        try:
            with open(save_path, "wb") as f:
                f.write(zip_data)
            self.text_input.clear()
            QMessageBox.information(
                self, "Success", f"File saved:\n{os.path.abspath(save_path)}"
            )
            self.status_label.setText(f"Saved: {os.path.basename(save_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            self.status_label.setText("File save failed")

    def _extract_zip_from_data(self, zip_data: bytes):
        extract_path = QFileDialog.getExistingDirectory(
            self, "Select Extraction Folder"
        )
        if not extract_path:
            self.status_label.setText("Extraction operation canceled")
            return
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zipf:
                file_list = zipf.namelist()
                zipf.extractall(extract_path)
            self.text_input.clear()
            QMessageBox.information(
                self,
                "Success",
                f"Extracted {len(file_list)} files to:\n{os.path.abspath(extract_path)}",
            )
            self.status_label.setText(f"Extracted to: {os.path.basename(extract_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Extraction Failed", str(e))
            self.status_label.setText("Extraction failed")

    def _files_to_base64_zip(self):
        """Select files → ZIP → Base64"""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Files")
        if not file_paths:
            return
        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in file_paths:
                    add_to_zip(zipf, file_path)
            zip_data = zip_buffer.getvalue()
            base64_result = base64.b64encode(zip_data).decode("utf-8")
            self.text_input.clear()
            self.output_b64.setText(base64_result)
            self.output_text.clear()
            self.status_label.setText(
                f"Compressed {len(file_paths)} files, length: {len(base64_result)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _folders_to_base64_zip(self):
        """Select folder → ZIP → Base64"""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder_path:
            return
        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                add_to_zip(zipf, folder_path)
            zip_data = zip_buffer.getvalue()
            base64_result = base64.b64encode(zip_data).decode("utf-8")
            self.text_input.clear()
            self.output_b64.setText(base64_result)
            self.output_text.clear()
            self.status_label.setText(
                f"Compressed folder: {os.path.basename(folder_path)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_STYLE)
    window = Base64Tool()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
