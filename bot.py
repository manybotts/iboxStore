import os
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
)
from pymongo import MongoClient

# Initialize Flask app
app = Flask(__name__)

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
HEROKU_URL = os.getenv("HEROKU_URL")  # Replace with your Heroku/Koyeb URL
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMINS", "").split(",")]  # Admin list

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client["TelegramBot"]
users_collection = db["users"]
files_collection = db["files"]

# Start command handler
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id

    # Add user to the database if not already present
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({"user_id": user_id, "chat_id": chat_id})

    update.message.reply_text(
        "Welcome! Send me any file, and I'll generate a shareable link for it."
    )

# Handle file uploads
def handle_file(update: Update, context: CallbackContext):
    message = update.message
    user_id = message.from_user.id

    # Check if the user is an admin
    if user_id not in ADMINS:
        message.reply_text("You are not authorized to upload files.")
        return

    # Check if the message contains a document or media
    if message.document:
        file_obj = message.document
    elif message.photo:
        file_obj = message.photo[-1]  # Get the highest quality photo
    elif message.video:
        file_obj = message.video
    else:
        message.reply_text("Please send a valid file.")
        return

    # Get the file ID and unique ID
    file_id = file_obj.file_id
    file_unique_id = file_obj.file_unique_id

    # Store file metadata in MongoDB
    file_data = {
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "uploaded_by": user_id,
    }
    files_collection.insert_one(file_data)

    # Generate a persistent link using file_unique_id
    persistent_link = f"https://t.me/{context.bot.username}?start={file_unique_id}"

    # Reply with the generated link
    message.reply_text(
        f"Your file has been uploaded successfully!\n\n"
        f"Shareable Link: {persistent_link}"
    )

# Handle batch file sharing
def batch_files(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    # Check if the user is an admin
    if user_id not in ADMINS:
        update.message.reply_text("You are not authorized to view batch files.")
        return

    # Retrieve all files uploaded by the admin
    uploaded_files = files_collection.find({"uploaded_by": user_id})

    if not uploaded_files.count():
        update.message.reply_text("You haven't uploaded any files yet.")
        return

    # Create a keyboard with all the file links
    buttons = [
        [InlineKeyboardButton(f"File {i + 1}", url=f"https://t.me/{context.bot.username}?start={file['file_unique_id']}")]
        for i, file in enumerate(uploaded_files)
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    update.message.reply_text(
        "Here are all your uploaded files:", reply_markup=reply_markup
    )

# Broadcast messages to all users
def broadcast(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    # Check if the user is an admin
    if user_id not in ADMINS:
        update.message.reply_text("You are not authorized to broadcast messages.")
        return

    # Get the message to broadcast
    if not context.args:
        update.message.reply_text("Usage: /broadcast <message>")
        return

    broadcast_message = " ".join(context.args)

    # Retrieve all user chat IDs from the database
    users = users_collection.find()
    for user in users:
        try:
            context.bot.send_message(chat_id=user["chat_id"], text=broadcast_message)
        except Exception as e:
            print(f"Failed to send message to user {user['chat_id']}: {e}")

    update.message.reply_text("Message broadcasted successfully.")

# Webhook endpoint for Flask
@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return "ok"

# Main function
if __name__ == "__main__":
    # Initialize the Telegram bot
    updater = Updater(token=BOT_TOKEN)  # Remove use_context=True for v20.x+
    dispatcher = updater.dispatcher

    # Add handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO,  # Updated filters
        handle_file
    ))
    dispatcher.add_handler(CommandHandler("batch", batch_files))
    dispatcher.add_handler(CommandHandler("broadcast", broadcast))

    # Set up webhook
    PORT = int(os.getenv("PORT", "8443"))
    HEROKU_APP_NAME = os.getenv("HEROKU_APP_NAME")

    # For production deployment (uncomment these lines)
    # updater.start_webhook(
    #     listen="0.0.0.0",
    #     port=PORT,
    #     webhook_url=f"{HEROKU_URL}/webhook"
    # )

    # For local testing (uncomment this line)
    # updater.start_polling()

    # Start the Flask app
    app.run(host="0.0.0.0", port=PORT)
