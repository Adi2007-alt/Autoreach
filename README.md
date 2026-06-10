# AutoReach V14 - WhatsApp Bulk Messenger

AutoReach is a robust, Python-based desktop application designed for automated WhatsApp bulk messaging. It utilizes precise visual pixel-scanning and system-level window management to achieve reliable, mouse-free text dispatch directly through WhatsApp Web.

## Features

- **Visual Screen Analysis**: Uses the `ScreenAnalyser` engine to verify page loading via green brand-color pixel scanning, avoiding unreliable DOM hooks.
- **High-DPI Awareness**: Automatically scales UI interactions across 125%, 150%, and 200% monitor display scaling factors using OS-level detection.
- **Queue & Rate Limits**: Fully built-in scheduler with daily/hourly limits and human-like Gaussian jitter delays to prevent account flagging.
- **Adapter Architecture**: Easily test broadcasts with a `DryRunAdapter` before using the `WhatsAppWebAdapter` on real contacts.
- **Data Persistence**: Uses a local SQLite database (`autoreach.db`) for automatic crash-recovery, retaining drafts, and detailed campaign audits.
- **Modern Tkinter UI**: Sleek dark mode dashboard with live progress monitoring and exportable reports.

## Prerequisites

- **Python 3.9+**
- **Google Chrome** or **Microsoft Edge** installed.
- Ensure your WhatsApp account is logged into WhatsApp Web in your default browser profile so that the QR code is pre-authorized.

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/autoreach.git
   cd autoreach
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Start the application by running the main entry script:

```bash
python autoreach_v14.py
```

### Quick Guide:
1. **Settings**: Head to the `⚙ Settings` tab to configure your Daily Limits and Delay intervals.
2. **Send**: Navigate to the `✉ Send` tab to compose your message.
3. **Import**: Import a `.txt` or `.csv` file containing the target phone numbers.
4. **Broadcast**: Click `▶ START BROADCAST` to execute the queue. Monitor progress in the Live Dashboard!

## Disclaimer

This software is intended for educational purposes and responsible outreach. Ensure you comply with WhatsApp's Terms of Service regarding bulk messaging and user consent. The developer is not responsible for any account bans.
