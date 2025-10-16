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
    """取得資源檔案的絕對路徑 (支援 pyinstaller 打包後的環境)"""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller 打包後，臨時資料夾會存在 sys._MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# --- 常數與 QSS 樣式 ---
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


# --- 核心功能 (文字部分) ---
def encode_text_to_base64(text: str) -> str:
    """將文字編碼為 Base64 字串。"""
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def decode_base64_to_text(base64_str: str) -> str:
    """將 Base64 字串解碼為文字，忽略解碼錯誤。"""
    try:
        return base64.b64decode(base64_str.encode("utf-8")).decode(
            "utf-8", errors="ignore"
        )
    except Exception:
        return ""


# --- 遞迴壓縮工具 ---
def add_to_zip(zipf, path, base_path=""):
    """遞迴將檔案或資料夾加入 ZIP"""
    if os.path.isfile(path):
        arcname = os.path.join(base_path, os.path.basename(path))
        zipf.write(path, arcname)
    elif os.path.isdir(path):
        # 當加入資料夾時，保留資料夾名稱在壓縮檔裡
        for root, dirs, files in os.walk(path):
            for file in files:
                abs_path = os.path.join(root, file)
                # rel_path 使得壓縮檔內會包含從選取資料夾的上層算起的相對路徑，保留資料夾結構
                rel_path = os.path.relpath(abs_path, os.path.dirname(path))
                zipf.write(abs_path, rel_path)


CHUNK_SIZE = 1024 * 1024  # 1MB；可依需求調整


class ZipAndEncodeWorker(QObject):
    # stage: 顯示當前階段文字；rangeChanged: 設定最大值；progress: 更新目前值（bytes）
    stage = pyqtSignal(str)
    rangeChanged = pyqtSignal(int)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)  # 傳回輸出檔路徑（Base64.txt）
    error = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, items, base_dir, save_path):
        """
        items: List[Tuple[abs_path:str, arcname:str]]
        base_dir: 壓縮時作為相對根目錄的基準
        save_path: Base64.txt 欲輸出路徑
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
            # -------- Stage 1: ZIP（串流寫入，邊讀邊壓）--------
            self.stage.emit("正在壓縮檔案/資料夾…")
            total_bytes = self._calc_total_bytes()
            self.rangeChanged.emit(max(1, total_bytes))
            processed = 0

            fd, tmp_zip = tempfile.mkstemp(suffix=".zip")
            os.close(fd)  # 我們用 ZipFile 打開，這裡先關閉 fd

            with zipfile.ZipFile(
                tmp_zip, "w", compression=zipfile.ZIP_DEFLATED
            ) as zipf:
                for abs_path, arcname in self.items:
                    if self._cancel:
                        self._cleanup(tmp_zip, self.save_path)
                        self.canceled.emit()
                        return
                    if os.path.isdir(abs_path):
                        # 目錄理論上不會出現在 items（我們展平為檔案）；保險起見跳過
                        continue

                    # 串流寫入單一檔案
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
                        self.error.emit(f"壓縮檔案時發生錯誤：{abs_path}\n{e}")
                        self._cleanup(tmp_zip, self.save_path)
                        return

            # -------- Stage 2: Base64 串流編碼到檔案 --------
            self.stage.emit("正在進行 Base64 編碼並寫入檔案…")
            zip_size = os.path.getsize(tmp_zip)
            self.rangeChanged.emit(max(1, zip_size))
            processed = 0

            # 我們自己做串流編碼（處理 3-byte 邊界），以便回報進度
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
                    # 只編碼到 3 的整數倍；尾端留到下一輪
                    full_len = (len(buf) // 3) * 3
                    if full_len:
                        out = base64.b64encode(buf[:full_len])
                        fout.write(out)
                    remain = buf[full_len:]
                    processed += len(chunk)
                    self.progress.emit(min(processed, zip_size))
                # 收尾
                if remain:
                    fout.write(base64.b64encode(remain))

            # 成功
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
    finished = pyqtSignal(str)  # 傳回暫存 zip 路徑
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
            # -------- Stage 1: 讀取 Base64 檔並串流解碼為 ZIP --------
            self.stage.emit("正在解碼 Base64（讀取中）…")
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
                    chunk = fin.read(CHUNK_SIZE * 2)  # 文字較小，讀大塊點
                    if not chunk:
                        break
                    buf = remain + chunk
                    # Base64 以 4 字元為一組
                    full = (len(buf) // 4) * 4
                    if full:
                        fout.write(base64.b64decode(buf[:full], validate=False))
                    remain = buf[full:]
                    processed += len(chunk)
                    self.progress.emit(min(processed, total))
                # 收尾
                if remain:
                    try:
                        fout.write(base64.b64decode(remain, validate=False))
                    except Exception:
                        # 可能是最後有換行等非 base64 字元，忽略
                        pass

            # -------- Stage 2: 驗證 ZIP --------
            self.stage.emit("正在驗證 ZIP 檔…")
            self.rangeChanged.emit(1)
            self.progress.emit(0)
            ok = zipfile.is_zipfile(tmp_zip)
            self.progress.emit(1)
            if not ok:
                self._cleanup(tmp_zip)
                self.error.emit("解碼後內容不是有效的 ZIP 壓縮檔。")
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


# --- PyQt5 GUI 介面 ---
class Base64Tool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Base64 Studio")
        self.setMinimumSize(820, 700)
        self._init_ui()
        from PyQt5.QtGui import QIcon

        # 若沒有 icon.ico 也不致命，resource_path 會回傳路徑
        try:
            self.setWindowIcon(QIcon(resource_path("icon.ico")))
        except Exception:
            pass

    def _init_ui(self):
        """初始化使用者介面元件。"""
        main_layout = QVBoxLayout()

        # 輸入區
        main_layout.addWidget(QLabel("輸入區：(輸入文字或 Base64 字串)"))
        self.text_input = QTextEdit()
        self.text_input.textChanged.connect(self._on_text_changed)
        main_layout.addWidget(self.text_input)

        # Base64 輸出區
        b64_output_header_layout = QHBoxLayout()
        b64_output_header_layout.addWidget(QLabel("Base64 編碼輸出："))
        b64_output_header_layout.addStretch()
        btn_copy_b64 = QPushButton("複製")
        btn_copy_b64.setObjectName("CopyButton")
        btn_copy_b64.clicked.connect(self._copy_b64_output)
        b64_output_header_layout.addWidget(btn_copy_b64)
        main_layout.addLayout(b64_output_header_layout)
        self.output_b64 = QTextEdit()
        self.output_b64.setReadOnly(True)
        main_layout.addWidget(self.output_b64)

        # 文字解碼輸出區
        text_output_header_layout = QHBoxLayout()
        text_output_header_layout.addWidget(QLabel("文字解碼輸出："))
        text_output_header_layout.addStretch()
        btn_copy_text = QPushButton("複製")
        btn_copy_text.setObjectName("CopyButton")
        btn_copy_text.clicked.connect(self._copy_text_output)
        text_output_header_layout.addWidget(btn_copy_text)
        main_layout.addLayout(text_output_header_layout)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        main_layout.addWidget(self.output_text)

        # 狀態標籤
        self.status_label = QLabel("準備就緒...")
        main_layout.addWidget(self.status_label)

        # 原本的檔案操作按鈕區（與你現有邏輯相同）
        file_group = QGroupBox("檔案壓縮與解碼（一般）")
        file_layout = QHBoxLayout()

        btn_files_to_b64 = QPushButton("選檔案壓縮 → Base64")
        btn_files_to_b64.clicked.connect(self._files_to_base64_zip)
        file_layout.addWidget(btn_files_to_b64)

        btn_folders_to_b64 = QPushButton("選資料夾壓縮 → Base64")
        btn_folders_to_b64.clicked.connect(self._folders_to_base64_zip)
        file_layout.addWidget(btn_folders_to_b64)

        btn_b64_to_file = QPushButton("Base64 → 解碼為檔案...")
        btn_b64_to_file.clicked.connect(self._handle_base64_to_file)
        file_layout.addWidget(btn_b64_to_file)

        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # 新增的大檔案處理專區（行為：壓縮直接詢問存 Base64.txt；解碼從 Base64.txt 讀取）
        large_group = QGroupBox(
            "大檔案處理專區（專為大檔案，直接存成 Base64.txt / 從 Base64.txt 解碼）"
        )
        large_layout = QHBoxLayout()

        btn_large_files_to_b64 = QPushButton("選檔案壓縮 → 儲存 Base64.txt")
        btn_large_files_to_b64.clicked.connect(self._large_files_to_base64_save)
        large_layout.addWidget(btn_large_files_to_b64)

        btn_large_folders_to_b64 = QPushButton("選資料夾壓縮 → 儲存 Base64.txt")
        btn_large_folders_to_b64.clicked.connect(self._large_folders_to_base64_save)
        large_layout.addWidget(btn_large_folders_to_b64)

        btn_large_b64_to_file = QPushButton("從 Base64.txt 解碼為檔案")
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
        QMessageBox.information(self, "成功", "作業完成！")
        self.status_label.setText(status_text)
        self.text_input.clear()
        self.output_b64.clear()
        self.output_text.clear()

    def _on_large_error(self, progress, thread, worker, msg):
        progress.close()
        thread.quit()
        thread.wait()
        worker.deleteLater()
        QMessageBox.critical(self, "錯誤", msg)
        self.status_label.setText("處理失敗")

    def _on_large_canceled(self, progress, thread, worker):
        progress.close()
        thread.quit()
        thread.wait()
        worker.deleteLater()
        QMessageBox.information(self, "已取消", "已停止並清除半成品。")
        self.status_label.setText("操作已取消")

    def _make_progress_dialog(self, title: str) -> QProgressDialog:
        dlg = QProgressDialog(title, "取消", 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setMinimumDuration(0)
        return dlg

    def _save_zip_from_path(self, zip_path: str):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "儲存為 ZIP 檔案", "", "ZIP 檔案 (*.zip);;所有檔案 (*)"
        )
        if not save_path:
            self.status_label.setText("儲存操作已取消")
            return False
        try:
            with open(zip_path, "rb") as fin, open(save_path, "wb") as fout:
                while True:
                    buf = fin.read(CHUNK_SIZE)
                    if not buf:
                        break
                    fout.write(buf)
            QMessageBox.information(
                self, "成功", f"檔案已儲存：\n{os.path.abspath(save_path)}"
            )
            self.status_label.setText(f"已儲存：{os.path.basename(save_path)}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "儲存失敗", str(e))
            self.status_label.setText("檔案儲存失敗")
            return False

    def _extract_zip_from_path(self, zip_path: str):
        extract_path = QFileDialog.getExistingDirectory(self, "選擇解壓縮資料夾")
        if not extract_path:
            self.status_label.setText("解壓縮操作已取消")
            return False
        try:
            with zipfile.ZipFile(zip_path, "r") as zipf:
                file_list = zipf.namelist()
                zipf.extractall(extract_path)
            QMessageBox.information(
                self,
                "成功",
                f"已解壓縮 {len(file_list)} 個檔案至：\n{os.path.abspath(extract_path)}",
            )
            self.status_label.setText(f"已解壓縮至：{os.path.basename(extract_path)}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "解壓縮失敗", str(e))
            self.status_label.setText("解壓縮失敗")
            return False

    # ---------- 複製按鈕功能 ----------
    def _copy_b64_output(self):
        """複製 Base64 輸出框的內容到剪貼簿。"""
        content = self.output_b64.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self.status_label.setText("Base64 輸出已複製到剪貼簿！")
        else:
            self.status_label.setText("Base64 輸出區為空，無可複製內容。")

    def _copy_text_output(self):
        """複製文字解碼輸出框的內容到剪貼簿。"""
        content = self.output_text.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self.status_label.setText("文字解碼輸出已複製到剪貼簿！")
        else:
            self.status_label.setText("文字解碼輸出區為空，無可複製內容。")

    # ---------- 文字即時轉換 ----------
    def _on_text_changed(self):
        """根據輸入內容即時更新輸出框。"""
        input_text = self.text_input.toPlainText().strip()
        if not input_text:
            self.output_b64.clear()
            self.output_text.clear()
            self.status_label.setText("準備就緒...")
            return

        # 更新兩個輸出：一個為文字編成 Base64，另一個嘗試以 Base64 解回文字
        try:
            self.output_b64.setText(encode_text_to_base64(input_text))
            self.output_text.setText(decode_base64_to_text(input_text))
            self.status_label.setText("即時轉換完成")
        except Exception:
            self.output_b64.clear()
            self.output_text.clear()
            self.status_label.setText("轉換時發生錯誤")

    # ---------- 原本的檔案 / 資料夾 → Base64（顯示在 GUI） ----------
    def _files_to_base64_zip(self):
        """選取檔案 → ZIP → Base64（結果顯示在 output_b64）"""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "選擇檔案")
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
                f"已壓縮 {len(file_paths)} 個檔案，Base64 長度：{len(base64_result)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))
            self.status_label.setText("壓縮失敗")

    def _folders_to_base64_zip(self):
        """選取資料夾 → ZIP → Base64（結果顯示在 output_b64）"""
        folder_path = QFileDialog.getExistingDirectory(self, "選擇資料夾")
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
                f"已壓縮資料夾：{os.path.basename(folder_path)}，Base64 長度：{len(base64_result)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))
            self.status_label.setText("壓縮失敗")

    def _handle_base64_to_file(self):
        """Base64（從文字輸入框）→ ZIP 檔案或直接解壓縮（原本行為）"""
        base64_str = self.text_input.toPlainText().strip()
        if not base64_str:
            QMessageBox.warning(self, "錯誤", "請在輸入區貼上 Base64 編碼。")
            return

        try:
            zip_data = base64.b64decode(base64_str.encode("utf-8"))
            if not zipfile.is_zipfile(io.BytesIO(zip_data)):
                QMessageBox.warning(self, "格式錯誤", "內容不是有效的 ZIP 壓縮檔。")
                self.status_label.setText("驗證失敗：不是 ZIP 格式")
                return

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("請選擇操作")
            msg_box.setText("已成功驗證為 ZIP 壓縮檔，您想如何處理？")

            btn_save_zip = msg_box.addButton("另存為 ZIP 檔案", QMessageBox.ActionRole)
            btn_extract = msg_box.addButton(
                "直接解壓縮到資料夾", QMessageBox.ActionRole
            )
            btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)

            msg_box.exec_()
            clicked_button = msg_box.clickedButton()
            if clicked_button == btn_save_zip:
                self._save_zip_from_data(zip_data)
            elif clicked_button == btn_extract:
                self._extract_zip_from_data(zip_data)
            else:
                self.status_label.setText("操作已取消")

        except base64.binascii.Error:
            QMessageBox.critical(self, "解碼錯誤", "輸入的並非有效的 Base64 編碼。")
            self.status_label.setText("解碼失敗")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"未知錯誤：\n{str(e)}")
            self.status_label.setText("解碼失敗")

    # ---------- 原本的保存與解壓方法 ----------
    def _save_zip_from_data(self, zip_data: bytes):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "儲存為 ZIP 檔案", "", "ZIP 檔案 (*.zip);;所有檔案 (*)"
        )
        if not save_path:
            self.status_label.setText("儲存操作已取消")
            return
        try:
            with open(save_path, "wb") as f:
                f.write(zip_data)
            self.text_input.clear()
            QMessageBox.information(
                self, "成功", f"檔案已儲存：\n{os.path.abspath(save_path)}"
            )
            self.status_label.setText(f"已儲存：{os.path.basename(save_path)}")
        except Exception as e:
            QMessageBox.critical(self, "儲存失敗", str(e))
            self.status_label.setText("檔案儲存失敗")

    def _extract_zip_from_data(self, zip_data: bytes):
        extract_path = QFileDialog.getExistingDirectory(self, "選擇解壓縮資料夾")
        if not extract_path:
            self.status_label.setText("解壓縮操作已取消")
            return
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zipf:
                file_list = zipf.namelist()
                zipf.extractall(extract_path)
            self.text_input.clear()
            QMessageBox.information(
                self,
                "成功",
                f"已解壓縮 {len(file_list)} 個檔案至：\n{os.path.abspath(extract_path)}",
            )
            self.status_label.setText(f"已解壓縮至：{os.path.basename(extract_path)}")
        except Exception as e:
            QMessageBox.critical(self, "解壓縮失敗", str(e))
            self.status_label.setText("解壓縮失敗")

    # ---------- 大檔案專區：壓縮後直接儲存為 Base64.txt ----------
    def _large_files_to_base64_save(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "選擇要壓縮的檔案（可多選）")
        if not file_paths:
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "儲存為 Base64.txt",
            "archive_base64.txt",
            "文字檔 (*.txt);;所有檔案 (*)",
        )
        if not save_path:
            self.status_label.setText("儲存 Base64.txt 已取消")
            return

        # 構造 items: (abs_path, arcname)
        items = [(p, os.path.basename(p)) for p in file_paths]
        base_dir = (
            os.path.commonpath([os.path.dirname(p) for p in file_paths])
            if file_paths
            else "."
        )

        worker = ZipAndEncodeWorker(items, base_dir, save_path)
        thread = QThread(self)
        worker.moveToThread(thread)

        progress = self._make_progress_dialog("處理中（不會卡 UI）…")
        progress.setLabelText("準備中…")
        progress.setRange(0, 0)  # 先未知

        # 連線
        worker.stage.connect(progress.setLabelText)
        worker.rangeChanged.connect(lambda m: progress.setRange(0, m))
        worker.progress.connect(progress.setValue)
        worker.finished.connect(
            lambda p: self._on_large_save_done(
                progress, thread, worker, f"已儲存 Base64：{os.path.basename(p)}"
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
        folder_path = QFileDialog.getExistingDirectory(self, "選擇要壓縮的資料夾")
        if not folder_path:
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "儲存為 Base64.txt",
            f"{os.path.basename(folder_path)}_base64.txt",
            "文字檔 (*.txt);;所有檔案 (*)",
        )
        if not save_path:
            self.status_label.setText("儲存 Base64.txt 已取消")
            return

        # 展平資料夾內全部檔案，保留相對路徑
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

        progress = self._make_progress_dialog("處理中（不會卡 UI）…")
        progress.setLabelText("準備中…")
        progress.setRange(0, 0)

        worker.stage.connect(progress.setLabelText)
        worker.rangeChanged.connect(lambda m: progress.setRange(0, m))
        worker.progress.connect(progress.setValue)
        worker.finished.connect(
            lambda p: self._on_large_save_done(
                progress, thread, worker, f"已儲存 Base64：{os.path.basename(p)}"
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
            "選擇 Base64.txt 檔案（由大檔案專區產生）",
            "",
            "文字檔 (*.txt);;所有檔案 (*)",
        )
        if not base64_path:
            return

        worker = DecodeBase64Worker(base64_path)
        thread = QThread(self)
        worker.moveToThread(thread)

        progress = self._make_progress_dialog("處理中（不會卡 UI）…")
        progress.setLabelText("準備中…")
        progress.setRange(0, 0)

        worker.stage.connect(progress.setLabelText)
        worker.rangeChanged.connect(lambda m: progress.setRange(0, m))
        worker.progress.connect(progress.setValue)

        def on_finished(tmp_zip_path: str):
            # 關掉進度條，回主執行緒做後續互動
            progress.close()
            thread.quit()
            thread.wait()
            worker.deleteLater()

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("請選擇操作")
            msg_box.setText("已成功驗證為 ZIP 壓縮檔，您想如何處理？")
            btn_save_zip = msg_box.addButton("另存為 ZIP 檔案", QMessageBox.ActionRole)
            btn_extract = msg_box.addButton(
                "直接解壓縮到資料夾", QMessageBox.ActionRole
            )
            btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)
            msg_box.exec_()

            clicked_button = msg_box.clickedButton()
            try:
                if clicked_button == btn_save_zip:
                    done = self._save_zip_from_path(tmp_zip_path)
                elif clicked_button == btn_extract:
                    done = self._extract_zip_from_path(tmp_zip_path)
                else:
                    self.status_label.setText("操作已取消")
                    done = False
            finally:
                # 清掉暫存 zip
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


# ---------- 應用程式啟動 ----------
def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_STYLE)
    window = Base64Tool()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
