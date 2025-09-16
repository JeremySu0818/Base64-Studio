# Base64 Studio

Base64 Studio is a simple and powerful desktop tool built with **Python + PyQt5**, allowing you to:

* Convert **text ↔ Base64** in real time
* Encode **files/folders → ZIP → Base64**
* Decode **Base64 → ZIP → Extract or Save**
* Copy results quickly with one click

Two versions are provided:

* **Chinese UI** → `Base64 Studio_Chiness.exe`
* **English UI** → `Base64 Studio_English.exe`

Both versions share the same functionality.

---

## Installation

1. Download the latest release from [Releases](./releases).
2. Run the installer `Base64StudioSetup.exe`.
3. During installation, you can choose which version to install:

   * **Chinese**
   * **English**
4. A shortcut will be created on your **Desktop** and **Start Menu**.

---

## Preview

Main interface includes:

* Input area for text/Base64
* Real-time encoded/decoded output
* File & folder compression and decoding tools
* Status bar for instant feedback

---

## Build From Source

If you want to build your own `.exe`:

```bash
pip install pyqt5 pyinstaller
pyinstaller --noconsole --onefile --icon=icon.ico base64_studio_English.py
```

---

## Files in Release

* `Base64 Studio_Chiness.exe` → Chinese UI version
* `Base64 Studio_English.exe` → English UI version
* `icon.ico` → App icon
* `Base64StudioSetup.exe` → Installer with language selection

---

## License

MIT License. Free to use, modify, and distribute.

---

## Credits

Developed using **Python 3.11 + PyQt5**.
Special thanks to the open-source community.

---

# Base64 Studio (中文版)

Base64 Studio 是一款基於 **Python + PyQt5** 開發的簡單且功能強大的桌面工具，提供以下功能：

* 即時轉換 **文字 ↔ Base64**
* 壓縮並編碼 **檔案/資料夾 → ZIP → Base64**
* 解碼 **Base64 → ZIP → 解壓縮或另存**
* 一鍵快速複製結果

提供兩個版本：

* **中文介面** → `Base64 Studio_Chiness.exe`
* **英文介面** → `Base64 Studio_English.exe`

兩個版本功能完全相同。

---

## 安裝方式

1. 從 [Releases](./releases) 下載最新版本。
2. 執行安裝程式 `Base64StudioSetup.exe`。
3. 安裝過程中可選擇要安裝的版本：

   * **中文**
   * **英文**
4. 安裝完成後會在 **桌面** 和 **開始選單** 建立捷徑。

---

## 軟體介面預覽

主要介面包括：

* 輸入區（文字/Base64）
* 即時編碼/解碼輸出
* 檔案與資料夾壓縮及解碼工具
* 狀態列即時提示

---

## 原始碼編譯

若要自行編譯 `.exe` 檔案：

```bash
pip install pyqt5 pyinstaller
pyinstaller --noconsole --onefile --icon=icon.ico base64_studio_Chiness.py
```

---

## 發布檔案清單

* `Base64 Studio_Chiness.exe` → 中文介面版本
* `Base64 Studio_English.exe` → 英文介面版本
* `icon.ico` → 應用程式圖示
* `Base64StudioSetup.exe` → 可選語言版本的安裝程式

---

## 授權

MIT 授權，允許自由使用、修改與散佈。

---

## 致謝

使用 **Python 3.11 + PyQt5** 開發。
特別感謝開源社群的支持。
