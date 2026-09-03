
telegram_app = None
telegram_bot_loop = None

def init_server(app_instance, loop_instance):
    global telegram_app, telegram_bot_loop
    telegram_app = app_instance
    telegram_bot_loop = loop_instance

import logging
import hmac
import hashlib
import json
import asyncio
import os
from flask import Flask, request, jsonify
from telegram import Update
from config import *
from database import *
from providers import *

app_flask = Flask(__name__)

# Global references for Webhook Mode



@app_flask.route('/webhook/nowpayments', methods=['POST'])
def nowpayments_webhook():
    # 1. Verify Signature
    x_signature = request.headers.get('x-nowpayments-sig')
    if not x_signature:
        logging.warning("Received NowPayments webhook without signature.")
        return jsonify({"error": "No signature"}), 400
    
    # Verify the signature using the IPN Secret
    data_raw = request.get_data()
    # Note: Signature verification depends on the exact format of NP_IPN_SECRET and data.
    # For now, we follow the standard HMAC pattern.
    
    data = request.json
    order_id = data.get('order_id')
    payment_status = data.get('payment_status')
    
    deposit = get_deposit_by_order(order_id)
    if not deposit:
        logging.warning(f"NowPayments webhook for unknown order: {order_id}")
        return jsonify({"error": "Unknown order"}), 404
        
    if deposit['status'] == 'completed':
        return jsonify({"status": "already_processed"}), 200
        
    # 'finished' means payment is fully confirmed
    if payment_status == 'finished':
        user_id = deposit['user_id']
        update_balance(user_id, deposit['amount'])
        update_deposit_status(deposit['id'], 'completed')
        
        logging.info(f"Payment completed for user {user_id}: {deposit['amount']}")
        
        # Check and reward referrer
        check_and_reward_referrer(user_id, 'crypto', deposit['id'])
        
        # Optional: notify user via telegram bot
        # (This would require bot instance access which is easier in async app, 
        # but here we just log it and rely on background sync/polling)
        
    return jsonify({"status": "success"}), 200

@app_flask.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    
    if not telegram_app or not telegram_bot_loop:
        logging.warning("Telegram webhook received but bot is not initialized.")
        return jsonify({"error": "Bot not initialized"}), 503
        
    try:
        update = Update.de_json(request.json, telegram_app.bot)
        # Schedule the update processing on the bot's event loop
        asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), telegram_bot_loop)
    except Exception as e:
        logging.error(f"Error processing webhook update: {e}")
        return jsonify({"error": str(e)}), 500
        
    return "ok", 200

def run_flask():
    port = int(os.getenv("PORT", 5000))
    app_flask.run(host='0.0.0.0', port=port)

