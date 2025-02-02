import os
import asyncio
import requests  # Added for webhook setup
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
from pymongo import MongoClient

# Initialize Flask app
app = Flask(__name__)

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
RAILWAY_URL = os.getenv("RAILWAY_STATIC_URL")  # Public URL provided by Railway
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMINS", "").split(",") if admin_id]

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client["TelegramBot"]
users_collection = db["users"]
files_collection = db["files"]

# ========== HANDLER FUNCTIONS ==========
async def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({"user_id": user_id, "chat_id": chat_id})
    await update.message.reply_text(
        "Welcome! Send me any file, and I'll generate a shareable link for it."
    )


async def handle_file(update: Update, context: CallbackContext):
    message = update.message
    user_id = message.from_user.id
    if user_id not in ADMINS:
        await message.reply_text("You are not authorized to upload files.")
        return
    if message.document:
        file_obj = message.document
    elif message.photo:
        file_obj = message.photo[-1]
    elif message.video:
        file_obj = message.video
    else:
        await message.reply_text("Please send a valid file.")
        return
    file_data = {
        "file_id": file_obj.file_id,
        "file_unique_id": file_obj.file_unique_id,
        "uploaded_by": user_id,
    }
    files_collection.insert_one(file_data)
    persistent_link = f"https://t.me/{context.bot.username}?start={file_obj.file_unique_id}"
    await message.reply_text(
        f"File uploaded successfully!\nShareable Link: {persistent_link}"
    )


async def batch_files(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to view batch files.")
        return
    uploaded_files = list(files_collection.find({"uploaded_by": user_id}))
    if not uploaded_files:
        await update.message.reply_text("You haven't uploaded any files yet.")
        return
    buttons = [
        [
            InlineKeyboardButton(
                f"File {i + 1}",
                url=f"https://t.me/{context.bot.username}?start={file['file_unique_id']}",
            )
        ]
        for i, file in enumerate(uploaded_files)
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "Here are all your uploaded files:", reply_markup=reply_markup
    )


async def broadcast(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to broadcast messages.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    broadcast_message = " ".join(context.args)
    users = users_collection.find()
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["chat_id"], text=broadcast_message
            )
        except Exception as e:
            print(f"Failed to send message to user {user['chat_id']}: {e}")
    await update.message.reply_text("Message broadcasted successfully.")


# ========== WEBHOOK ENDPOINT ==========
@app.route("/", methods=["POST"])
async def webhook():
    global application  # Use the globally initialized application
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.create_task(application.process_update(update))
    return "ok"


# ========== AUTOMATED WEBHOOK SETUP ==========
async def set_telegram_webhook():
    """Set the Telegram bot webhook."""
    if not RAILWAY_URL or not BOT_TOKEN:
        print("Webhook setup skipped: Missing RAILWAY_URL or BOT_TOKEN.")
        return

    webhook_url = f"{RAILWAY_URL}/"
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
        json={"url": webhook_url},
    )

    if response.ok:
        print(f"Webhook set successfully: {webhook_url}")
    else:
        print(f"Failed to set webhook: {response.text}")


# ========== BOT MAIN FUNCTION ==========
async def bot_main():
    global application  # Make the application accessible globally
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_file)
    )
    application.add_handler(CommandHandler("batch", batch_files))
    application.add_handler(CommandHandler("broadcast", broadcast))

    # Initialize the application
    await application.initialize()

    # Set the webhook
    await set_telegram_webhook()

    # Run the bot until interrupted
    try:
        await application.start()
        while True:
            await asyncio.sleep(3600)  # Keep the bot running
    finally:
        await application.stop()


# ========== RUN BOT ==========
if __name__ == "__main__":
    # Initialize and run the bot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot_main())
    except KeyboardInterrupt:
        print("Stopping bot...")
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    finally:
        loop.close()
