import os
import re
import logging
import time
import requests
import schedule
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
from collections import defaultdict

# --- Configuration ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")   # Set your bot token in environment variable
NTFY_TOPIC = "telegram_bot_reports"               # ntfy topic name
LOG_FILE = "reports.log"                          # Path for the log file
DOWNLOAD_SITE_URL = "https://savetogallery.site/?url="

# Regex to match Instagram Reel URLs
INSTAGRAM_REEL_REGEX = r"https?:\/\/(?:www\.)?instagram\.com\/(?:reels?|p)\/[a-zA-Z0-9\-\_]+"

# --- Logging Setup ---
logger = logging.getLogger('bot_logger')
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(LOG_FILE, mode='a')
file_handler.setLevel(logging.INFO)

# Format: "2025-09-04 15:10:00 | UserID=123, Username=John, URL=https://..."
formatter = logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

# --- Helpers ---
def get_report_title():
    """Generates a title for the ntfy report with the current date."""
    today_date = datetime.now().strftime("%Y-%m-%d")
    return f"Telegram Bot Report - {today_date}"

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    await update.message.reply_markdown_v2(
        f"Hello, {user.mention_markdown_v2()}\\!\n\n"
        f"I am your Instagram Reels Downloader Bot\\. "
        f"Send me an Instagram Reel link, and I will provide you with a download link\\."
    )

async def handle_reel_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles messages containing Instagram Reel URLs."""
    user_url = update.message.text.strip()
    user = update.effective_user
    
    if re.match(INSTAGRAM_REEL_REGEX, user_url):
        # Log the interaction
        logger.info(f"UserID={user.id}, Username={user.full_name}, URL={user_url}")
        
        # Construct the download link
        response_url = f"{DOWNLOAD_SITE_URL}{user_url}"
        
        await update.message.reply_markdown_v2(
            f"Here is your download link:\n\n[Download Now]({response_url})\n\n"
            f"Simply click the link to go to the site and download your Reel\\. Happy downloading\\!"
        )
    else:
        await update.message.reply_text(
            "❌ That doesn't look like a valid Instagram Reel link. Please send a direct link to an Instagram Reel."
        )

# --- Reporting Function ---
def send_daily_report():
    try:
        if not os.path.exists(LOG_FILE):
            logging.warning("Report file does not exist, skipping daily report.")
            return

        with open(LOG_FILE, 'r') as f:
            log_lines = f.readlines()

        if not log_lines:
            logging.info("No user interactions to report, skipping daily report.")
            return

        total_interactions = 0
        unique_users = set()
        interactions_per_user = defaultdict(int)
        user_names = {}
        detailed_logs = []

        for log in log_lines:
            if "UserID=" not in log:
                continue

            total_interactions += 1
            try:
                timestamp, data = log.strip().split(" | ", 1)
            except ValueError:
                continue

            log_data = {}
            for part in data.split(", "):
                if '=' in part:
                    key, value = part.split('=', 1)
                    log_data[key.strip()] = value.strip()

            user_id = log_data.get('UserID')
            user_name = log_data.get('Username')
            url = log_data.get('URL')

            if user_id:
                unique_users.add(user_id)
                interactions_per_user[user_id] += 1
                if user_name:
                    user_names[user_id] = user_name
                detailed_logs.append(f"{timestamp} | {user_name} ({user_id}) -> {url}")

        # Construct report
        formatted_report = f"# Daily User Interaction Report ({datetime.now().strftime('%Y-%m-%d')})\n\n"
        formatted_report += f"**Total Interactions:** {total_interactions}\n"
        formatted_report += f"**Unique Users:** {len(unique_users)}\n\n"

        formatted_report += "### Interactions Per User\n"
        for user_id, count in interactions_per_user.items():
            name = user_names.get(user_id, 'N/A')
            formatted_report += f"* **User:** {name} (ID: `{user_id}`) - **Interactions:** {count}\n"

        formatted_report += "\n### Detailed Log\n"
        formatted_report += "```\n" + "\n".join(detailed_logs) + "\n```\n"

        # Save report
        report_filename = f"daily_report_{datetime.now().strftime('%Y-%m-%d')}.md"
        with open(report_filename, "w") as f:
            f.write(formatted_report)
        
        # Send to ntfy
        with open(report_filename, 'rb') as f:
            response = requests.put(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                data=f,
                headers={"Filename": get_report_title()}
            )

        if response.status_code == 200:
            logging.info("Daily report sent to ntfy successfully.")
            # Clear logs after success
            with open(LOG_FILE, 'w') as f:
                f.write("")
        else:
            logging.error(f"Failed to send report to ntfy. Status code: {response.status_code}")
            logging.error(f"Response content: {response.text}")

        os.remove(report_filename)

    except Exception as e:
        logging.error(f"Error while sending daily report: {e}")

# --- Main Bot Logic ---
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reel_url))

    # Schedule the daily report
    schedule.every().day.at("00:00").do(send_daily_report)

    # Run the bot
    application.run_polling()

    # Keep schedule running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    main()
    # send_daily_report()
