import logging
import asyncio
import os
import threading
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import *
from database import init_db
from handlers import *
from server import run_flask, app_flask, init_server

app = None
bot_loop = None

async def main_async():
    global app, bot_loop
    bot_loop = asyncio.get_running_loop()
    
    
    app = Application.builder().token(TELEGRAM_TOKEN).read_timeout(30).connect_timeout(30).build()
    init_server(app, bot_loop)
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('profile', profile))
    app.add_handler(CommandHandler('deposit', deposit))
    app.add_handler(CommandHandler('rent', rent))
    app.add_handler(CommandHandler('buy', rent))
    app.add_handler(CommandHandler('mynumbers', mynumbers))
    app.add_handler(CommandHandler('sync', sync_numbers_command))
    app.add_handler(CommandHandler('admin', admin_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    
    await app.initialize()
    await app.start()
    
    # Set up Telegram Webhook URL
    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
    if not webhook_url:
        from urllib.parse import urlparse
        parsed = urlparse(IPN_CALLBACK_URL)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        webhook_url = f"{base_url}/webhook/telegram"
        
    logging.info(f"Setting Telegram webhook to: {webhook_url}")
    await app.bot.set_webhook(url=webhook_url)
    
    # Start auto-renewal background task
    app.job_queue.run_repeating(auto_renewal_job, interval=900, first=10)
    
    logging.info("Bot is securely running on Webhooks...")
    
    # Keep the event loop running
    stop_event = asyncio.Event()
    await stop_event.wait()

def main_polling():
    global app, bot_loop
    app = Application.builder().token(TELEGRAM_TOKEN).read_timeout(30).connect_timeout(30).build()
    init_server(app, bot_loop)
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('profile', profile))
    app.add_handler(CommandHandler('deposit', deposit))
    app.add_handler(CommandHandler('rent', rent))
    app.add_handler(CommandHandler('buy', rent))
    app.add_handler(CommandHandler('mynumbers', mynumbers))
    app.add_handler(CommandHandler('sync', sync_numbers_command))
    app.add_handler(CommandHandler('admin', admin_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    
    logging.info("Bot is securely running with long polling...")
    
    # Start auto-renewal background task using JobQueue
    app.job_queue.run_repeating(auto_renewal_job, interval=900, first=10)
    
    app.run_polling()

if __name__ == '__main__':
    # Initialize DB (runs synchronously before threads/event loops)
    init_db()

    # Start Flask in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()
    
    use_webhook = os.getenv("USE_WEBHOOK", "false").lower() == "true"
    
    logging.info(f"USE_WEBHOOK evaluated to: {use_webhook}")
    if use_webhook:
        try:
            asyncio.run(main_async())
        except KeyboardInterrupt:
            logging.info("Webhook bot stopped.")
    else:
        main_polling()

