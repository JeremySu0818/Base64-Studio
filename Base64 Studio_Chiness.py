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
    except base64.binascii.Error:
        return ""


# --- 遞迴壓縮工具 ---
def add_to_zip(zipf, path, base_path=""):
    """遞迴將檔案或資料夾加入 ZIP"""
    if os.path.isfile(path):
        arcname = os.path.join(base_path, os.path.basename(path))
        zipf.write(path, arcname)
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, os.path.dirname(path))
                zipf.write(abs_path, rel_path)


# --- PyQt5 GUI 介面 ---
class Base64Tool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Base64 Studio")
        self.setMinimumSize(700, 600)
        self._init_ui()
        from PyQt5.QtGui import QIcon

        self.setWindowIcon(QIcon(resource_path("icon.ico")))

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

        # 檔案操作按鈕
        file_group = QGroupBox("檔案壓縮與解碼")
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

        self.setLayout(main_layout)

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

    def _on_text_changed(self):
        """根據輸入內容即時更新輸出框。"""
        input_text = self.text_input.toPlainText().strip()
        if not input_text:
            self.output_b64.clear()
            self.output_text.clear()
            self.status_label.setText("準備就緒...")
            return

        self.output_b64.setText(encode_text_to_base64(input_text))
        self.output_text.setText(decode_base64_to_text(input_text))
        self.status_label.setText("即時轉換完成")

    def _handle_base64_to_file(self):
        """Base64 → ZIP 檔案或直接解壓縮"""
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

    def _files_to_base64_zip(self):
        """選取檔案 → ZIP → Base64"""
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
                f"已壓縮 {len(file_paths)} 個檔案，長度：{len(base64_result)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))

    def _folders_to_base64_zip(self):
        """選取資料夾 → ZIP → Base64"""
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
            self.status_label.setText(f"已壓縮資料夾：{os.path.basename(folder_path)}")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_STYLE)
    window = Base64Tool()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
