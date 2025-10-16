# -*- coding: utf-8 -*-
import sys
import os
import base64
import zipfile
import io
import traceback
import tempfile
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QProgressDialog

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
    """Get the absolute path to resource (supports PyInstaller environment)"""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
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
    """Encodes text to a Base64 string."""
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def decode_base64_to_text(base64_str: str) -> str:
    """Decodes a Base64 string to text, ignoring decoding errors."""
    try:
        return base64.b64decode(base64_str.encode("utf-8")).decode(
            "utf-8", errors="ignore"
        )
    except Exception:
        return ""


# --- Recursive Compression Utility ---
def add_to_zip(zipf, path, base_path=""):
    """Recursively adds a file or folder to ZIP"""
    if os.path.isfile(path):
        arcname = os.path.join(base_path, os.path.basename(path))
        zipf.write(path, arcname)
    elif os.path.isdir(path):
        # When adding a folder, keep the folder name in the archive
        for root, dirs, files in os.walk(path):
            for file in files:
                abs_path = os.path.join(root, file)
                # rel_path makes the archive contain the relative path starting from the parent of the selected folder, preserving the structure
                rel_path = os.path.relpath(abs_path, os.path.dirname(path))
                zipf.write(abs_path, rel_path)


CHUNK_SIZE = 1024 * 1024  # 1MB; adjustable


class ZipAndEncodeWorker(QObject):
    # stage: displays current stage text; rangeChanged: sets max value; progress: updates current value (bytes)
    stage = pyqtSignal(str)
    rangeChanged = pyqtSignal(int)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)  # Returns the output file path (Base64.txt)
    error = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, items, base_dir, save_path):
        """
        items: List[Tuple[abs_path:str, arcname:str]]
        base_dir: Base directory for relative root during compression
        save_path: Base64.txt desired output path
        """
        super().__init__()
        self.items = items
        self.base_dir = base_dir
        self.save_path = save_path
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def _calc_total_bytes(self):
        total = 0
        for abs_path, _ in self.items:
            if os.path.isfile(abs_path):
                try:
                    total += os.path.getsize(abs_path)
                except Exception:
                    pass
        return total

    def run(self):
        tmp_zip = None
        try:
            # -------- Stage 1: ZIP (Stream write, read-while-compressing) --------
            self.stage.emit("Compressing files/folders...")
            total_bytes = self._calc_total_bytes()
            self.rangeChanged.emit(max(1, total_bytes))
            processed = 0

            fd, tmp_zip = tempfile.mkstemp(suffix=".zip")
            os.close(fd)  # We open with ZipFile, close fd here

            with zipfile.ZipFile(
                tmp_zip, "w", compression=zipfile.ZIP_DEFLATED
            ) as zipf:
                for abs_path, arcname in self.items:
                    if self._cancel:
                        self._cleanup(tmp_zip, self.save_path)
                        self.canceled.emit()
                        return
                    if os.path.isdir(abs_path):
                        # Directories should theoretically not appear in items (we flattened to files); skip as a safeguard
                        continue

                    # Stream write single file
                    try:
                        with open(abs_path, "rb") as src, zipf.open(
                            arcname, "w", force_zip64=True
                        ) as dst:
                            while True:
                                if self._cancel:
                                    self._cleanup(tmp_zip, self.save_path)
                                    self.canceled.emit()
                                    return
                                chunk = src.read(CHUNK_SIZE)
                                if not chunk:
                                    break
                                dst.write(chunk)
                                processed += len(chunk)
                                self.progress.emit(min(processed, total_bytes))
                    except Exception as e:
                        self.error.emit(f"Error compressing file: {abs_path}\n{e}")
                        self._cleanup(tmp_zip, self.save_path)
                        return

            # -------- Stage 2: Base64 stream encoding to file --------
            self.stage.emit("Performing Base64 encoding and writing to file...")
            zip_size = os.path.getsize(tmp_zip)
            self.rangeChanged.emit(max(1, zip_size))
            processed = 0

            # We perform stream encoding ourselves (handling 3-byte boundary) to report progress
            remain = b""
            with open(tmp_zip, "rb") as fin, open(self.save_path, "wb") as fout:
                while True:
                    if self._cancel:
                        self._cleanup(tmp_zip, self.save_path)
                        self.canceled.emit()
                        return
                    chunk = fin.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    buf = remain + chunk
                    # Encode only up to a multiple of 3; the remainder is for the next round
                    full_len = (len(buf) // 3) * 3
                    if full_len:
                        out = base64.b64encode(buf[:full_len])
                        fout.write(out)
                    remain = buf[full_len:]
                    processed += len(chunk)
                    self.progress.emit(min(processed, zip_size))
                # Finalize
                if remain:
                    fout.write(base64.b64encode(remain))

            # Success
            try:
                os.remove(tmp_zip)
            except Exception:
                pass
            self.finished.emit(self.save_path)

        except Exception as e:
            self._cleanup(tmp_zip, self.save_path)
            self.error.emit(str(e))

    def _cleanup(self, tmp_zip, save_path):
        for p in (tmp_zip, save_path):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


class DecodeBase64Worker(QObject):
    stage = pyqtSignal(str)
    rangeChanged = pyqtSignal(int)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)  # Returns temp zip path
    error = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, base64_path):
        super().__init__()
        self.base64_path = base64_path
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def run(self):
        tmp_zip = None
        try:
            # -------- Stage 1: Read Base64 file and stream decode to ZIP --------
            self.stage.emit("Decoding Base64 (Reading)...")
            total = os.path.getsize(self.base64_path)
            self.rangeChanged.emit(max(1, total))
            processed = 0

            fd, tmp_zip = tempfile.mkstemp(suffix=".zip")
            os.close(fd)

            remain = b""
            with open(self.base64_path, "rb") as fin, open(tmp_zip, "wb") as fout:
                while True:
                    if self._cancel:
                        self._cleanup(tmp_zip)
                        self.canceled.emit()
                        return
                    chunk = fin.read(CHUNK_SIZE * 2)  # Read larger chunks for text
                    if not chunk:
                        break
                    buf = remain + chunk
                    # Base64 is grouped in 4 characters
                    full = (len(buf) // 4) * 4
                    if full:
                        fout.write(base64.b64decode(buf[:full], validate=False))
                    remain = buf[full:]
                    processed += len(chunk)
                    self.progress.emit(min(processed, total))
                # Finalize
                if remain:
                    try:
                        fout.write(base64.b64decode(remain, validate=False))
                    except Exception:
                        # May be non-base64 characters like newline at the end, ignore
                        pass

            # -------- Stage 2: Validate ZIP --------
            self.stage.emit("Validating ZIP file...")
            self.rangeChanged.emit(1)
            self.progress.emit(0)
            ok = zipfile.is_zipfile(tmp_zip)
            self.progress.emit(1)
            if not ok:
                self._cleanup(tmp_zip)
                self.error.emit("Decoded content is not a valid ZIP archive.")
                return

            self.finished.emit(tmp_zip)

        except Exception as e:
            self._cleanup(tmp_zip)
            self.error.emit(str(e))

    def _cleanup(self, tmp_zip):
        try:
            if tmp_zip and os.path.exists(tmp_zip):
                os.remove(tmp_zip)
        except Exception:
            pass


# --- PyQt5 GUI Interface ---
class Base64Tool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Base64 Studio")
        self.setMinimumSize(820, 700)
        self._init_ui()
        from PyQt5.QtGui import QIcon

        # If icon.ico is missing, not critical, resource_path returns the path
        try:
            self.setWindowIcon(QIcon(resource_path("icon.ico")))
        except Exception:
            pass

    def _init_ui(self):
        """Initializes user interface components."""
        main_layout = QVBoxLayout()

        # Input Area
        main_layout.addWidget(QLabel("Input Area: (Enter Text or Base64 String)"))
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

        # Text Decoded Output Area
        text_output_header_layout = QHBoxLayout()
        text_output_header_layout.addWidget(QLabel("Text Decoded Output:"))
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

        # Original File Operations Group (Standard)
        file_group = QGroupBox("File Compression & Decoding (Standard)")
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

        # New Large File Handling Group (Behavior: compress directly asks to save Base64.txt; decode reads from Base64.txt)
        large_group = QGroupBox("Large File Processing (Stream Save/Load Base64.txt)")
        large_layout = QHBoxLayout()

        btn_large_files_to_b64 = QPushButton("Select Files → Save Base64.txt")
        btn_large_files_to_b64.clicked.connect(self._large_files_to_base64_save)
        large_layout.addWidget(btn_large_files_to_b64)

        btn_large_folders_to_b64 = QPushButton("Select Folder → Save Base64.txt")
        btn_large_folders_to_b64.clicked.connect(self._large_folders_to_base64_save)
        large_layout.addWidget(btn_large_folders_to_b64)

        btn_large_b64_to_file = QPushButton("Decode from Base64.txt to File")
        btn_large_b64_to_file.clicked.connect(self._large_base64_file_to_file)
        large_layout.addWidget(btn_large_b64_to_file)

        large_group.setLayout(large_layout)
        main_layout.addWidget(large_group)

        self.setLayout(main_layout)

    def _on_large_save_done(self, progress, thread, worker, status_text):
        progress.close()
        thread.quit()
        thread.wait()
        worker.deleteLater()
        QMessageBox.information(self, "Success", "Operation completed!")
        self.status_label.setText(status_text)
        self.text_input.clear()
        self.output_b64.clear()
        self.output_text.clear()

    def _on_large_error(self, progress, thread, worker, msg):
        progress.close()
        thread.quit()
        thread.wait()
        worker.deleteLater()
        QMessageBox.critical(self, "Error", msg)
        self.status_label.setText("Processing failed")

    def _on_large_canceled(self, progress, thread, worker):
        progress.close()
        thread.quit()
        thread.wait()
        worker.deleteLater()
        QMessageBox.information(
            self, "Canceled", "Operation stopped and partial files cleaned up."
        )
        self.status_label.setText("Operation canceled")

    def _make_progress_dialog(self, title: str) -> QProgressDialog:
        dlg = QProgressDialog(title, "Cancel", 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setMinimumDuration(0)
        return dlg

    def _save_zip_from_path(self, zip_path: str):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save as ZIP File", "", "ZIP Files (*.zip);;All Files (*)"
        )
        if not save_path:
            self.status_label.setText("Save operation canceled")
            return False
        try:
            with open(zip_path, "rb") as fin, open(save_path, "wb") as fout:
                while True:
                    buf = fin.read(CHUNK_SIZE)
                    if not buf:
                        break
                    fout.write(buf)
            QMessageBox.information(
                self, "Success", f"File saved:\n{os.path.abspath(save_path)}"
            )
            self.status_label.setText(f"Saved: {os.path.basename(save_path)}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            self.status_label.setText("File save failed")
            return False

    def _extract_zip_from_path(self, zip_path: str):
        extract_path = QFileDialog.getExistingDirectory(
            self, "Select Extraction Folder"
        )
        if not extract_path:
            self.status_label.setText("Extraction operation canceled")
            return False
        try:
            with zipfile.ZipFile(zip_path, "r") as zipf:
                file_list = zipf.namelist()
                zipf.extractall(extract_path)
            QMessageBox.information(
                self,
                "Success",
                f"Extracted {len(file_list)} files to:\n{os.path.abspath(extract_path)}",
            )
            self.status_label.setText(f"Extracted to: {os.path.basename(extract_path)}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Extraction Failed", str(e))
            self.status_label.setText("Extraction failed")
            return False

    # ---------- Copy Button Functions ----------
    def _copy_b64_output(self):
        """Copies the content of the Base64 output box to the clipboard."""
        content = self.output_b64.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self.status_label.setText("Base64 output copied to clipboard!")
        else:
            self.status_label.setText("Base64 output area is empty, nothing to copy.")

    def _copy_text_output(self):
        """Copies the content of the text decoded output box to the clipboard."""
        content = self.output_text.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self.status_label.setText("Text decoded output copied to clipboard!")
        else:
            self.status_label.setText(
                "Text decoded output area is empty, nothing to copy."
            )

    # ---------- Real-time Text Conversion ----------
    def _on_text_changed(self):
        """Updates output boxes in real-time based on input content."""
        input_text = self.text_input.toPlainText().strip()
        if not input_text:
            self.output_b64.clear()
            self.output_text.clear()
            self.status_label.setText("Ready...")
            return

        # Update both outputs: one is text encoded to Base64, the other attempts to decode input as Base64 back to text
        try:
            self.output_b64.setText(encode_text_to_base64(input_text))
            self.output_text.setText(decode_base64_to_text(input_text))
            self.status_label.setText("Real-time conversion complete")
        except Exception:
            self.output_b64.clear()
            self.output_text.clear()
            self.status_label.setText("Error during conversion")

    # ---------- Original Files / Folder → Base64 (Display in GUI) ----------
    def _files_to_base64_zip(self):
        """Select Files → ZIP → Base64 (Result displayed in output_b64)"""
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
                f"Compressed {len(file_paths)} files, Base64 length: {len(base64_result)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Compression failed")

    def _folders_to_base64_zip(self):
        """Select Folder → ZIP → Base64 (Result displayed in output_b64)"""
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
                f"Compressed folder: {os.path.basename(folder_path)}, Base64 length: {len(base64_result)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText("Compression failed")

    def _handle_base64_to_file(self):
        """Base64 (from text input box) → ZIP file or direct extraction (Original behavior)"""
        base64_str = self.text_input.toPlainText().strip()
        if not base64_str:
            QMessageBox.warning(
                self, "Error", "Please paste Base64 encoding in the input area."
            )
            return

        try:
            zip_data = base64.b64decode(base64_str.encode("utf-8"))
            if not zipfile.is_zipfile(io.BytesIO(zip_data)):
                QMessageBox.warning(
                    self, "Format Error", "Content is not a valid ZIP archive."
                )
                self.status_label.setText("Validation failed: Not ZIP format")
                return

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("Select Operation")
            msg_box.setText(
                "Successfully validated as a ZIP archive. What would you like to do?"
            )

            btn_save_zip = msg_box.addButton("Save as ZIP File", QMessageBox.ActionRole)
            btn_extract = msg_box.addButton(
                "Extract Directly to Folder", QMessageBox.ActionRole
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
                self, "Decoding Error", "Input is not valid Base64 encoding."
            )
            self.status_label.setText("Decoding failed")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unknown error:\n{str(e)}")
            self.status_label.setText("Decoding failed")

    # ---------- Original Save and Extract Methods ----------
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

    # ---------- Large File Section: Compress and Save Directly to Base64.txt ----------
    def _large_files_to_base64_save(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Files to Compress (Multi-select supported)"
        )
        if not file_paths:
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save as Base64.txt",
            "archive_base64.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not save_path:
            self.status_label.setText("Save Base64.txt canceled")
            return

        # Construct items: (abs_path, arcname)
        items = [(p, os.path.basename(p)) for p in file_paths]
        base_dir = (
            os.path.commonpath([os.path.dirname(p) for p in file_paths])
            if file_paths
            else "."
        )

        worker = ZipAndEncodeWorker(items, base_dir, save_path)
        thread = QThread(self)
        worker.moveToThread(thread)

        progress = self._make_progress_dialog("Processing (Non-blocking UI)...")
        progress.setLabelText("Preparing...")
        progress.setRange(0, 0)  # Unknown range initially

        # Connect signals
        worker.stage.connect(progress.setLabelText)
        worker.rangeChanged.connect(lambda m: progress.setRange(0, m))
        worker.progress.connect(progress.setValue)
        worker.finished.connect(
            lambda p: self._on_large_save_done(
                progress, thread, worker, f"Base64 saved: {os.path.basename(p)}"
            )
        )
        worker.error.connect(
            lambda msg: self._on_large_error(progress, thread, worker, msg)
        )
        worker.canceled.connect(
            lambda: self._on_large_canceled(progress, thread, worker)
        )

        progress.canceled.connect(worker.request_cancel)

        thread.started.connect(worker.run)
        thread.start()

    def _large_folders_to_base64_save(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Folder to Compress"
        )
        if not folder_path:
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save as Base64.txt",
            f"{os.path.basename(folder_path)}_base64.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not save_path:
            self.status_label.setText("Save Base64.txt canceled")
            return

        # Flatten all files in the folder, preserving relative paths
        items = []
        base_dir = os.path.dirname(folder_path)
        for root, _, files in os.walk(folder_path):
            for name in files:
                abs_path = os.path.join(root, name)
                arcname = os.path.relpath(abs_path, base_dir)
                items.append((abs_path, arcname))

        worker = ZipAndEncodeWorker(items, base_dir, save_path)
        thread = QThread(self)
        worker.moveToThread(thread)

        progress = self._make_progress_dialog("Processing (Non-blocking UI)...")
        progress.setLabelText("Preparing...")
        progress.setRange(0, 0)

        worker.stage.connect(progress.setLabelText)
        worker.rangeChanged.connect(lambda m: progress.setRange(0, m))
        worker.progress.connect(progress.setValue)
        worker.finished.connect(
            lambda p: self._on_large_save_done(
                progress, thread, worker, f"Base64 saved: {os.path.basename(p)}"
            )
        )
        worker.error.connect(
            lambda msg: self._on_large_error(progress, thread, worker, msg)
        )
        worker.canceled.connect(
            lambda: self._on_large_canceled(progress, thread, worker)
        )

        progress.canceled.connect(worker.request_cancel)

        thread.started.connect(worker.run)
        thread.start()

    def _large_base64_file_to_file(self):
        base64_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Base64.txt File (Generated by Large File Section)",
            "",
            "Text Files (*.txt);;All Files (*)",
        )
        if not base64_path:
            return

        worker = DecodeBase64Worker(base64_path)
        thread = QThread(self)
        worker.moveToThread(thread)

        progress = self._make_progress_dialog("Processing (Non-blocking UI)...")
        progress.setLabelText("Preparing...")
        progress.setRange(0, 0)

        worker.stage.connect(progress.setLabelText)
        worker.rangeChanged.connect(lambda m: progress.setRange(0, m))
        worker.progress.connect(progress.setValue)

        def on_finished(tmp_zip_path: str):
            # Close progress dialog, return to main thread for subsequent interaction
            progress.close()
            thread.quit()
            thread.wait()
            worker.deleteLater()

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("Select Operation")
            msg_box.setText(
                "Successfully validated as a ZIP archive. What would you like to do?"
            )
            btn_save_zip = msg_box.addButton("Save as ZIP File", QMessageBox.ActionRole)
            btn_extract = msg_box.addButton(
                "Extract Directly to Folder", QMessageBox.ActionRole
            )
            btn_cancel = msg_box.addButton("Cancel", QMessageBox.RejectRole)
            msg_box.exec_()

            clicked_button = msg_box.clickedButton()
            done = False
            try:
                if clicked_button == btn_save_zip:
                    done = self._save_zip_from_path(tmp_zip_path)
                elif clicked_button == btn_extract:
                    done = self._extract_zip_from_path(tmp_zip_path)
                else:
                    self.status_label.setText("Operation canceled")
            finally:
                # Clean up temp zip
                try:
                    if os.path.exists(tmp_zip_path):
                        os.remove(tmp_zip_path)
                except Exception:
                    pass

            if done:
                self.text_input.clear()
                self.output_b64.clear()
                self.output_text.clear()

        worker.finished.connect(on_finished)
        worker.error.connect(
            lambda msg: self._on_large_error(progress, thread, worker, msg)
        )
        worker.canceled.connect(
            lambda: self._on_large_canceled(progress, thread, worker)
        )

        progress.canceled.connect(worker.request_cancel)

        thread.started.connect(worker.run)
        thread.start()


# ---------- Application Startup ----------
def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_STYLE)
    window = Base64Tool()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
