import os
import asyncio
from threading import Thread
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
from waitress import serve

# Initialize Flask app
app = Flask(__name__)

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
HEROKU_URL = os.getenv("HEROKU_URL")
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMINS", "").split(",")]

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client["TelegramBot"]
users_collection = db["users"]
files_collection = db["files"]

# Start command handler
async def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id

    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({"user_id": user_id, "chat_id": chat_id})

    await update.message.reply_text(
        "Welcome! Send me any file, and I'll generate a shareable link for it."
    )

# Handle file uploads
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

# Handle batch file sharing
async def batch_files(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to view batch files.")
        return

    uploaded_files = files_collection.find({"uploaded_by": user_id})

    if not uploaded_files.count():
        await update.message.reply_text("You haven't uploaded any files yet.")
        return

    buttons = [
        [InlineKeyboardButton(f"File {i + 1}", url=f"https://t.me/{context.bot.username}?start={file['file_unique_id']}")]
        for i, file in enumerate(uploaded_files)
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        "Here are all your uploaded files:", reply_markup=reply_markup
    )

# Broadcast messages
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
                chat_id=user["chat_id"], 
                text=broadcast_message
            )
        except Exception as e:
            print(f"Failed to send message to user {user['chat_id']}: {e}")

    await update.message.reply_text("Message broadcasted successfully.")

# Webhook endpoint
@app.route("/webhook", methods=["POST"])
async def webhook():
    application = Application.builder().token(BOT_TOKEN).build()
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"

def run_flask():
    """Run Flask production server"""
    serve(app, host="0.0.0.0", port=int(os.getenv("PORT", 8443)))

async def run_bot():
    """Run Telegram bot"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO,
        handle_file
    ))
    application.add_handler(CommandHandler("batch", batch_files))
    application.add_handler(CommandHandler("broadcast", broadcast))

    if os.getenv("ENV") == "production":
        await application.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 8443)),
            webhook_url=f"{HEROKU_URL}/webhook"
        )
    else:
        await application.start()
        await application.updater.start_polling()
        await application.stop()

def run_async_tasks():
    """Run async tasks in separate event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

if __name__ == "__main__":
    # Start Flask in separate thread
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Start Telegram bot in main thread
    run_async_tasks()
