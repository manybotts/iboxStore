async def batch_files(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to view batch files.")
        return

    # Retrieve all files uploaded by the admin
    uploaded_files = files_collection.find({"uploaded_by": user_id})

    if not uploaded_files.count():
        await update.message.reply_text("You haven't uploaded any files yet.")
        return

    # Create a keyboard with all the file links
    buttons = [
        [InlineKeyboardButton(f"File {i + 1}", url=f"https://t.me/{context.bot.username}?start={file['file_unique_id']}")]
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
                chat_id=user["chat_id"], 
                text=broadcast_message
            )
        except Exception as e:
            print(f"Failed to send message to user {user['chat_id']}: {e}")

    await update.message.reply_text("Message broadcasted successfully.")

# Webhook endpoint for Flask
@app.route("/webhook", methods=["POST"])
async def webhook():
    application = Application.builder().token(BOT_TOKEN).build()
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"

if __name__ == "__main__":
    # Initialize the Telegram bot with ApplicationBuilder
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO,
        handle_file
    ))
    application.add_handler(CommandHandler("batch", batch_files))
    application.add_handler(CommandHandler("broadcast", broadcast))

    PORT = int(os.getenv("PORT", 8443))
    
    # For production deployment
    if os.getenv("ENV") == "production":
        await application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{HEROKU_URL}/webhook"
        )
    # For local testing
    else:
        await application.run_polling()

    app.run(host="0.0.0.0", port=PORT)
