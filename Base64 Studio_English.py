# -*- coding: utf-8 -*-
import sys
import os
import base64
import zipfile
import io
import traceback

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
    """Get absolute path to resource (works for dev and PyInstaller bundled apps)."""
    if hasattr(sys, "_MEIPASS"):
        # When bundled by PyInstaller, the temp folder is available at sys._MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# --- Constants and QSS style ---
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


# --- Core text functions ---
def encode_text_to_base64(text: str) -> str:
    """Encode text to Base64 string."""
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def decode_base64_to_text(base64_str: str) -> str:
    """Decode Base64 string to text, ignoring decode errors."""
    try:
        return base64.b64decode(base64_str.encode("utf-8")).decode(
            "utf-8", errors="ignore"
        )
    except Exception:
        return ""


# --- Recursive zip helper ---
def add_to_zip(zipf, path, base_path=""):
    """Recursively add file or directory to ZIP."""
    if os.path.isfile(path):
        arcname = os.path.join(base_path, os.path.basename(path))
        zipf.write(path, arcname)
    elif os.path.isdir(path):
        # When adding a folder, preserve folder names inside the archive
        for root, dirs, files in os.walk(path):
            for file in files:
                abs_path = os.path.join(root, file)
                # rel_path keeps the folder structure relative to the selected folder's parent
                rel_path = os.path.relpath(abs_path, os.path.dirname(path))
                zipf.write(abs_path, rel_path)


# --- PyQt5 GUI ---
class Base64Tool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Base64 Studio")
        self.setMinimumSize(820, 700)
        self._init_ui()
        from PyQt5.QtGui import QIcon

        # Not fatal if icon.ico is missing; resource_path will still return a path
        try:
            self.setWindowIcon(QIcon(resource_path("icon.ico")))
        except Exception:
            pass

    def _init_ui(self):
        """Initialize UI components."""
        main_layout = QVBoxLayout()

        # Input area
        main_layout.addWidget(QLabel("Input Area: (Enter text or Base64 string)"))
        self.text_input = QTextEdit()
        self.text_input.textChanged.connect(self._on_text_changed)
        main_layout.addWidget(self.text_input)

        # Base64 output area
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

        # Decoded text output area
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

        # Status label
        self.status_label = QLabel("Ready...")
        main_layout.addWidget(self.status_label)

        # Original file operation buttons (same behavior as original logic)
        file_group = QGroupBox("File Compression & Decode (Standard)")
        file_layout = QHBoxLayout()

        btn_files_to_b64 = QPushButton("Select Files → Compress → Base64")
        btn_files_to_b64.clicked.connect(self._files_to_base64_zip)
        file_layout.addWidget(btn_files_to_b64)

        btn_folders_to_b64 = QPushButton("Select Folder → Compress → Base64")
        btn_folders_to_b64.clicked.connect(self._folders_to_base64_zip)
        file_layout.addWidget(btn_folders_to_b64)

        btn_b64_to_file = QPushButton("Base64 → Decode to File...")
        btn_b64_to_file.clicked.connect(self._handle_base64_to_file)
        file_layout.addWidget(btn_b64_to_file)

        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # New large-file handling area (behavior: compress then ask to save Base64.txt; decode from Base64.txt)
        large_group = QGroupBox(
            "Large File Handling Area (save as Base64.txt / decode from Base64.txt)"
        )
        large_layout = QHBoxLayout()

        btn_large_files_to_b64 = QPushButton("Select Files → Save as Base64.txt")
        btn_large_files_to_b64.clicked.connect(self._large_files_to_base64_save)
        large_layout.addWidget(btn_large_files_to_b64)

        btn_large_folders_to_b64 = QPushButton("Select Folder → Save as Base64.txt")
        btn_large_folders_to_b64.clicked.connect(self._large_folders_to_base64_save)
        large_layout.addWidget(btn_large_folders_to_b64)

        btn_large_b64_to_file = QPushButton("Decode from Base64.txt to Files")
        btn_large_b64_to_file.clicked.connect(self._large_base64_file_to_file)
        large_layout.addWidget(btn_large_b64_to_file)

        large_group.setLayout(large_layout)
        main_layout.addWidget(large_group)

        self.setLayout(main_layout)

    # ---------- Copy button functions ----------
    def _copy_b64_output(self):
        """Copy Base64 output area content to clipboard."""
        content = self.output_b64.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self.status_label.setText("Base64 output copied to clipboard!")
        else:
            self.status_label.setText("Base64 output area is empty; nothing to copy.")

    def _copy_text_output(self):
        """Copy decoded text output area content to clipboard."""
        content = self.output_text.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self.status_label.setText("Decoded text output copied to clipboard!")
        else:
            self.status_label.setText(
                "Decoded text output area is empty; nothing to copy."
            )

    # ---------- Realtime text conversion ----------
    def _on_text_changed(self):
        """Update output areas in real time based on input content."""
        input_text = self.text_input.toPlainText().strip()
        if not input_text:
            self.output_b64.clear()
            self.output_text.clear()
            self.status_label.setText("Ready...")
            return

        # Update both outputs: one encodes text to Base64, the other attempts to decode input as Base64
        try:
            self.output_b64.setText(encode_text_to_base64(input_text))
            self.output_text.setText(decode_base64_to_text(input_text))
            self.status_label.setText("Realtime conversion completed")
        except Exception:
            self.output_b64.clear()
            self.output_text.clear()
            self.status_label.setText("Conversion error")

    # ---------- Files/Folders -> Base64 (displayed in GUI) ----------
    def _files_to_base64_zip(self):
        """Select files -> ZIP -> Base64 (result displayed in output_b64)"""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select files")
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
                f"Compressed {len(file_paths)} files, Base64 length: {len(base64_result)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Compression failed")

    def _folders_to_base64_zip(self):
        """Select folder -> ZIP -> Base64 (result displayed in output_b64)"""
        folder_path = QFileDialog.getExistingDirectory(self, "Select folder")
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
                f"Compressed folder: {os.path.basename(folder_path)}, Base64 length: {len(base64_result)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Compression failed")

    def _handle_base64_to_file(self):
        """Base64 (from input area) -> ZIP file or direct extract (original behavior)"""
        base64_str = self.text_input.toPlainText().strip()
        if not base64_str:
            QMessageBox.warning(
                self, "Error", "Please paste Base64 encoded data into the input area."
            )
            return

        try:
            zip_data = base64.b64decode(base64_str.encode("utf-8"))
            if not zipfile.is_zipfile(io.BytesIO(zip_data)):
                QMessageBox.warning(
                    self, "Format Error", "The content is not a valid ZIP archive."
                )
                self.status_label.setText("Validation failed: not ZIP format")
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
                self.status_label.setText("Operation cancelled")

        except base64.binascii.Error:
            QMessageBox.critical(
                self, "Decode Error", "The input is not valid Base64 encoded data."
            )
            self.status_label.setText("Decode failed")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unknown error:\n{str(e)}")
            self.status_label.setText("Decode failed")

    # ---------- Save and extract helpers ----------
    def _save_zip_from_data(self, zip_data: bytes):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save as ZIP file", "", "ZIP files (*.zip);;All files (*)"
        )
        if not save_path:
            self.status_label.setText("Save operation cancelled")
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
            self, "Select extraction folder"
        )
        if not extract_path:
            self.status_label.setText("Extraction operation cancelled")
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

    # ---------- Large-file area: compress then save as Base64.txt ----------
    def _large_files_to_base64_save(self):
        """Large files: select files to compress, then ask where to save Base64.txt (write directly)"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select files to compress (multi-select allowed)"
        )
        if not file_paths:
            return
        try:
            # Create zip and get binary data
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in file_paths:
                    add_to_zip(zipf, file_path)
            zip_data = zip_buffer.getvalue()

            # Ask where to save Base64.txt
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save as Base64.txt",
                "archive_base64.txt",
                "Text files (*.txt);;All files (*)",
            )
            if not save_path:
                self.status_label.setText("Save Base64.txt cancelled")
                return

            # Write in a streaming-friendly way (here zip_data is already in memory; encode and write)
            try:
                with open(save_path, "wb") as f_out:
                    encoded = base64.b64encode(zip_data)
                    f_out.write(encoded)
                QMessageBox.information(
                    self, "Success", f"Base64 file saved:\n{os.path.abspath(save_path)}"
                )
                self.status_label.setText(
                    f"Saved Base64: {os.path.basename(save_path)}"
                )
                self.text_input.clear()
                self.output_b64.clear()
                self.output_text.clear()
            except Exception as e:
                QMessageBox.critical(self, "Write Failed", str(e))
                self.status_label.setText("Base64 write failed")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Compression failed")

    def _large_folders_to_base64_save(self):
        """Large files: select folder to compress, then ask where to save Base64.txt"""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select folder to compress"
        )
        if not folder_path:
            return
        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                add_to_zip(zipf, folder_path)
            zip_data = zip_buffer.getvalue()

            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save as Base64.txt",
                f"{os.path.basename(folder_path)}_base64.txt",
                "Text files (*.txt);;All files (*)",
            )
            if not save_path:
                self.status_label.setText("Save Base64.txt cancelled")
                return

            try:
                with open(save_path, "wb") as f_out:
                    encoded = base64.b64encode(zip_data)
                    f_out.write(encoded)
                QMessageBox.information(
                    self, "Success", f"Base64 file saved:\n{os.path.abspath(save_path)}"
                )
                self.status_label.setText(
                    f"Saved Base64: {os.path.basename(save_path)}"
                )
                self.text_input.clear()
                self.output_b64.clear()
                self.output_text.clear()
            except Exception as e:
                QMessageBox.critical(self, "Write Failed", str(e))
                self.status_label.setText("Base64 write failed")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Compression failed")

    def _large_base64_file_to_file(self):
        """
        Large-file area: read from Base64.txt, decode to ZIP or extract.
        Behavior: user selects Base64.txt, program decodes and validates ZIP, then offers options (save as zip or extract).
        """
        # Select Base64.txt file
        base64_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Base64.txt file (generated by Large File area)",
            "",
            "Text files (*.txt);;All files (*)",
        )
        if not base64_path:
            return

        try:
            # Read file content (binary read because we stored b64 bytes)
            with open(base64_path, "rb") as f:
                b64_bytes = f.read()

            # Attempt decode
            try:
                zip_data = base64.b64decode(b64_bytes)
            except Exception:
                QMessageBox.critical(
                    self,
                    "Decode Error",
                    "The selected file is not valid Base64 encoded data.",
                )
                self.status_label.setText("Base64 decode failed")
                return

            # Check if it's a zip
            if not zipfile.is_zipfile(io.BytesIO(zip_data)):
                QMessageBox.warning(
                    self,
                    "Format Error",
                    "Decoded content is not a valid ZIP archive; cannot save or extract.",
                )
                self.status_label.setText("Validation failed: not ZIP format")
                return

            # Same behavior as original: ask user to save as zip or extract
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
                # Use the same save flow as original
                self._save_zip_from_data(zip_data)
            elif clicked_button == btn_extract:
                self._extract_zip_from_data(zip_data)
            else:
                self.status_label.setText("Operation cancelled")

        except Exception as e:
            # Including traceback in the message helps debugging (but keep concise)
            tb = traceback.format_exc()
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while processing:\n{str(e)}\n\nDetails have been logged.",
            )
            self.status_label.setText("Processing failed")


# ---------- Application startup ----------
def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_STYLE)
    window = Base64Tool()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
