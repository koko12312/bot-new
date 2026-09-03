import logging
import asyncio
import datetime
import time
import random
import os
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application
import textverified
from config import *
from database import *
from providers import *

# --- TELEGRAM COMMANDS ---

async def show_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇺🇸 English", callback_data="set_lang_en"),
         InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang_ar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = STRINGS['en']['select_lang']
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tg_username = update.effective_user.username
    tg_first_name = update.effective_user.first_name
    referrer_code = None
    if context.args:
        arg = context.args[0]
        if arg == 'portfolio_demo':
            portfolio_msg = (
                "👋 **Welcome, Recruiter!**\n\n"
                "You have triggered the portfolio demo mode! This bot is a production-ready system featuring:\n"
                "• Asynchronous processing & Multi-threading\n"
                "• Webhook Integration via Flask\n"
                "• Multi-provider API integration\n"
                "• Clean, modular architecture\n\n"
                "Feel free to explore the menus below!"
            )
            await update.message.reply_text(portfolio_msg, parse_mode='Markdown')
        else:
            referrer_code = arg

    user = await asyncio.to_thread(get_user, user_id)
    is_new_user = False
    if not user:
        user = await asyncio.to_thread(create_user, user_id, tg_username, tg_first_name, referrer_code)
        is_new_user = True
        logging.info(f"New user created: {user_id} (@{tg_username}) via ref: {referrer_code}")
    else:
        # Sync user info
        await asyncio.to_thread(update_user_info, user_id, username=tg_username, first_name=tg_first_name)
        user = await asyncio.to_thread(get_user, user_id)

    # If new user, show language selection first
    if is_new_user:
        await show_language_selection(update, context)
        return

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    referral_link = build_referral_link(user)
    escaped_referral_link = referral_link.replace("_", "\\_")
    
    keyboard = [
        [InlineKeyboardButton(s['btn_rent'], callback_data="main_rent")],
        [InlineKeyboardButton(s['btn_deposit'], callback_data="main_deposit")],
        [InlineKeyboardButton(s['btn_profile'], callback_data="main_profile"),
         InlineKeyboardButton(s['btn_numbers'], callback_data="main_numbers")],
        [InlineKeyboardButton(s['btn_lang'], callback_data="main_lang")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_name = user['username'] or user['first_name'] or s['fallback_name']
    if user['username']:
        welcome_name = "@" + welcome_name.replace('_', '\\_')
    
    await update.effective_message.reply_text(
        s['welcome'].format(
            name=welcome_name,
            balance=format_currency(user['balance']),
            bonus=format_currency(REFERRAL_BONUS),
            link=escaped_referral_link
        ),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        user = await asyncio.to_thread(create_user, user_id, update.effective_user.username)

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    referral_link = build_referral_link(user)
    escaped_referral_link = referral_link.replace("_", "\\_")
    
    text = (
        f"{s['profile_title']}\n\n{format_user_profile(user, lang)}\n\n"
        f"{s['label_ref_link']}\n{escaped_referral_link}"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, parse_mode='Markdown')

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        user = await asyncio.to_thread(create_user, user_id, update.effective_user.username)

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    keyboard = [
        [InlineKeyboardButton(s['deposit_crypto'], callback_data="deposit_method_crypto")],
        [InlineKeyboardButton(s['deposit_shamcash'], callback_data="deposit_method_shamcash")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_text(
        s['deposit_title'],
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def rent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        user = await asyncio.to_thread(create_user, user_id, update.effective_user.username)

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    keyboard = [
        [InlineKeyboardButton(s['btn_provider_tv'].format(price=format_currency(SERVICE_PRICE)), callback_data="rent_tv")],
        [InlineKeyboardButton(s['btn_provider_pva'].format(price=format_currency(PVADEALS_PRICE)), callback_data="rent_pva")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = s['rent_select_provider']
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def process_rent(update: Update, context: ContextTypes.DEFAULT_TYPE, provider: str):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    lang = user['language'] or 'en'
    s = STRINGS[lang]
    
    query = update.callback_query
    
    price = PVADEALS_PRICE if provider == 'pva' else SERVICE_PRICE
    
    if user['balance'] < price:
        keyboard = [[InlineKeyboardButton(s['btn_deposit'], callback_data="main_deposit")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            s['rent_low_balance'].format(price=format_currency(price)),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    await query.edit_message_text(s['rent_purchasing'])
    
    order = None
    if provider == 'tv':
        services = await asyncio.to_thread(get_services)
        whatsapp_targets = [s_item for s_item in services if 'whatsapp' in s_item.get('name', '').lower()]
        if not whatsapp_targets:
            await query.edit_message_text(s['rent_no_service'])
            return
        order = await asyncio.to_thread(purchase_number, whatsapp_targets[0]['id'])
    else:
        # PVADeals logic
        try:
            # We need to find the serviceId for WhatsApp on PVADeals
            res_services = await asyncio.to_thread(pva_client.get_services)
            svc_list = res_services.get('data', {}).get('services', []) if isinstance(res_services, dict) else []
            
            whatsapp_svc = next((svc for svc in svc_list if 'whatsapp' in svc.get('name', '').lower()), None)
            
            if not whatsapp_svc:
                await query.edit_message_text(s['rent_no_service'])
                return
                
            res = await asyncio.to_thread(pva_client.purchase_ltr, whatsapp_svc['_id'])
            if res and res.get('success'):
                data = res.get('data', {})
                # Strip '+' from number if present to avoid ++ in UI
                pva_number = data.get('number', '')
                if pva_number.startswith('+'):
                    pva_number = pva_number[1:]
                    
                order = {
                    "id": data.get('_id'),
                    "number": pva_number,
                    "status": data.get('status', 'active'),
                    "expires_at": data.get('endTime')
                }
        except Exception as e:
            logging.error(f"PVADeals purchase failed: {e}")

    if not order or 'id' not in order or not order.get('number'):
        await query.edit_message_text(s['rent_fail'])
        return

    await asyncio.to_thread(update_balance, user_id, -price)
    
    # Update add_number_record to include provider
    await asyncio.to_thread(add_number_record, user_id, order.get('number'), str(order.get('id')), 'whatsapp', order.get('expires_at'), order.get('status', 'active'), provider)

    expiry_date = datetime.datetime.fromisoformat(order.get('expires_at')).strftime('%Y-%m-%d')
    await query.edit_message_text(
        s['rent_success'].format(
            number=order.get('number'),
            price=format_currency(price),
            expiry=expiry_date
        ),
        parse_mode='Markdown'
    )

async def mynumbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        await update.effective_message.reply_text("You don't have an account yet. Use /start first.")
        return

    lang = user['language'] or 'en'
    s = STRINGS[lang]

    numbers = await asyncio.to_thread(get_user_numbers, user_id)
    if not numbers:
        if update.callback_query:
            await update.callback_query.edit_message_text(s['mynumbers_empty'])
        else:
            await update.effective_message.reply_text(s['mynumbers_empty'])
        return

    if update.callback_query:
        await update.callback_query.edit_message_text(s['mynumbers_title'], parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(s['mynumbers_title'], parse_mode='Markdown')

    for raw_number in numbers:
        number = await asyncio.to_thread(sync_single_number, raw_number)
        status_icon = "✅" if number['status'] in ['active', 'renewableActive'] else "❌"
        auto_renew_status = s['status_active'] if number['auto_renew'] else s['status_disabled']
        expiry_info = ""
        
        if number['expires_at']:
            try:
                import dateutil.parser
                expiry_dt = dateutil.parser.parse(number['expires_at'])
                expiry_date = expiry_dt.strftime('%Y-%m-%d')
                
                # Calculate time left
                now = datetime.datetime.now(expiry_dt.tzinfo) if expiry_dt.tzinfo else datetime.datetime.now(datetime.UTC)
                diff = expiry_dt - now
                
                if diff.total_seconds() <= 0:
                    time_left = s['label_expired']
                elif diff.days > 0:
                    time_left = f"{diff.days}d {s['label_left']}"
                else:
                    hours = int(diff.total_seconds() // 3600)
                    time_left = f"{hours}h {s['label_left']}"
                
                expiry_info = f"\n{s['label_expires']}: `{expiry_date}` ({time_left})"
            except Exception as e:
                logging.error(f"Date parsing failed for {number['number']}: {e}")
                expiry_info = f"\n{s['label_expires']}: `{number['expires_at'][:10]}`"

        text = (
            f"{status_icon} {s['label_number']}: `+{number['number']}`\n"
            f"{s['label_service']}: {number['service'].capitalize()}\n"
            f"{s['label_auto_renew']}: {auto_renew_status}"
            f"{expiry_info}"
        )

        buttons = [
            [InlineKeyboardButton(s['btn_get_code'], callback_data=f"code_{number['id']}"),
             InlineKeyboardButton(s['btn_refund'], callback_data=f"sub_refund_{number['id']}")]
        ]

        if number['auto_renew']:
            buttons.append([InlineKeyboardButton(s['btn_cancel_sub'], callback_data=f"sub_cancel_{number['id']}")])
        else:
            buttons.append([InlineKeyboardButton(s['btn_enable_renew'], callback_data=f"sub_enable_{number['id']}")])

        reply_markup = InlineKeyboardMarkup(buttons)
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def sync_numbers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    if not user:
        await update.effective_message.reply_text("You don't have an account yet.")
        return

    await update.effective_message.reply_text("🔄 Refreshing your numbers... please wait.")
    
    try:
        # Get user's numbers from local DB
        local_numbers = await asyncio.to_thread(get_user_numbers, user_id)
        if not local_numbers:
            await update.effective_message.reply_text("You don't have any active numbers to sync.")
            return

        sync_count = 0
        for num in local_numbers:
            provider = num['provider'] if 'provider' in num.keys() and num['provider'] else 'textverified'
            try:
                status = None
                expiry = None
                
                if provider in ['textverified', 'tv']:
                    # Fetch latest details from TV for THIS specific number
                    details = await asyncio.to_thread(textverified.reservations.details, num['verification_id'])
                    status = details.state.value
                    
                    # Get actual expiry from TV billing cycle
                    if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                        try:
                            cycle = await asyncio.to_thread(textverified.billing_cycles.get, details.billing_cycle_id)
                            expiry = cycle.billing_cycle_ends_at.isoformat()
                        except: pass
                elif provider == 'pva':
                    res = await asyncio.to_thread(pva_client.get_ltr_details, num['verification_id'])
                    if res and res.get('success'):
                        data = res.get('data', {})
                        server_status = data.get('status', '').upper()
                        if server_status in ['FLAGGED', 'CANCELLED', 'EXPIRED']:
                            status = 'deleted'
                        else:
                            status = 'active'
                        expiry = data.get('expiryDate') or data.get('expiresAt') or data.get('endTime')

                if status:
                    # Update local DB
                    def update_num_db(s, exp, v_id):
                        conn = get_db_connection()
                        conn.execute(
                            "UPDATE numbers SET status = ?, expires_at = ? WHERE verification_id = ?",
                            (s, exp, v_id)
                        )
                        conn.commit()
                        conn.close()
                    
                    await asyncio.to_thread(update_num_db, status, expiry, num['verification_id'])
                    sync_count += 1
            except Exception as e:
                # Check for 404 error to mark as deleted
                is_404 = False
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code == 404:
                        is_404 = True
                elif "404" in str(e) or "Not Found" in str(e) or "Request not found" in str(e):
                    is_404 = True
                    
                if is_404:
                    logging.warning(f"Number {num['number']} ({provider}) returned 404 on sync. Marking as deleted.")
                    def mark_del():
                        conn = get_db_connection()
                        conn.execute("UPDATE numbers SET status = 'deleted' WHERE verification_id = ?", (num['verification_id'],))
                        conn.commit()
                        conn.close()
                    await asyncio.to_thread(mark_del)
                    sync_count += 1
                else:
                    logging.warning(f"Could not sync number {num['number']}: {e}")

        await update.effective_message.reply_text(f"✅ Refresh complete! Updated {sync_count} numbers.")
        await mynumbers(update, context)

    except Exception as e:
        logging.error(f"Sync failed: {e}")
        await update.effective_message.reply_text("❌ Refresh failed. Please try again later.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await asyncio.to_thread(get_user, user_id)
    lang = user['language'] or 'en'
    s = STRINGS[lang]
    
    if context.user_data and context.user_data.get('user_action') == 'shamcash_pdf':
        doc = update.message.document
        if doc.mime_type != 'application/pdf':
            await update.effective_message.reply_text("❌ Please upload the receipt as a **PDF file**.")
            return
            
        amt = context.user_data.pop('sham_amt')
        context.user_data.pop('user_action')
        
        # Save to DB
        def save_sham_request():
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO manual_deposits (user_id, amount, receipt_file_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, amt, doc.file_id, get_timestamp(), get_timestamp())
            )
            conn.commit()
            conn.close()
            
        await asyncio.to_thread(save_sham_request)
        
        await update.effective_message.reply_text(s['shamcash_submitted'].format(amount=format_currency(amt)), parse_mode='Markdown')
        
        # Notify Admin
        if ADMIN_ID:
            user_name = f"@{user['username']}" if user['username'] else f"`{user_id}`"
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 *New ShamCash Deposit Request*\n\nUser: {user_name}\nAmount: {format_currency(amt)}\n\nReview it in the /admin panel.",
                parse_mode='Markdown'
            )
        return

    await update.effective_message.reply_text("I didn't expect a document. Use the menu or /help.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.effective_message.reply_text("You are not authorized to use admin commands.")
        return

    args = context.args
    if not args:
        # Show hybrid inline admin menu
        keyboard = [
            [InlineKeyboardButton("👥 All Users List", callback_data="admin_list_users_recent")],
            [InlineKeyboardButton("📋 View User Profile", callback_data="admin_menu_view"),
             InlineKeyboardButton("➕ Link New Number", callback_data="admin_menu_addnumber")],
            [InlineKeyboardButton("➕ Add Credit", callback_data="admin_menu_credit"),
             InlineKeyboardButton("➖ Remove Credit", callback_data="admin_menu_debit")],
            [InlineKeyboardButton("📱 View Numbers", callback_data="admin_menu_numbers"),
             InlineKeyboardButton("🗑 Remove Number", callback_data="admin_menu_removenum")],
            [InlineKeyboardButton("📥 Pending ShamCash", callback_data="admin_pending_shamcash")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Quick stats
        def get_stats():
            conn = get_db_connection()
            u_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            a_nums = conn.execute("SELECT COUNT(*) FROM numbers WHERE status IN ('active', 'renewableActive')").fetchone()[0]
            conn.close()
            return u_count, a_nums

        user_count, active_nums = await asyncio.to_thread(get_stats)

        text = (
            f"👨‍💼 *Admin Dashboard*\n\n"
            f"👥 *Total Users:* `{user_count}`\n"
            f"📱 *Active Rentals:* `{active_nums}`\n\n"
            f"Select an action or use `/admin help` for text commands:"
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return

    action = args[0].lower()
    
    if action == 'help':
        help_text = (
            "📖 *Admin Text Commands:*\n\n"
            "`/admin view <ID/@user>` - View profile\n"
            "`/admin credit <ID/@user> <amt>` - Add credit\n"
            "`/admin debit <ID/@user> <amt>` - Remove credit\n"
            "`/admin numbers <ID/@user>` - View active numbers\n"
            "`/admin addnumber <ID/@user> <num> <verif_id> [tv/pva]` - Link number manually"
        )
        await update.effective_message.reply_text(help_text, parse_mode='Markdown')
        return

    if action not in ['view', 'credit', 'debit', 'numbers', 'addnumber']:
        await update.effective_message.reply_text("Unknown admin action. Use `/admin help` for commands.")
        return

    if len(args) < 2:
        await update.effective_message.reply_text("Please provide a user ID or username.")
        return

    target = args[1]
    target_user = await asyncio.to_thread(resolve_user, target)
    if not target_user:
        await update.effective_message.reply_text("❌ User not found.")
        return

    if action == 'view':
        await update.effective_message.reply_text(
            f"👤 *User Profile*\n\n{format_user_profile(target_user)}",
            parse_mode='Markdown'
        )
        return

    if action in ['credit', 'debit']:
        if len(args) < 3 or not args[2].replace('.', '', 1).isdigit():
            await update.effective_message.reply_text("Please provide a valid amount.")
            return
        amount = float(args[2])
        if action == 'debit':
            amount = -amount
        await asyncio.to_thread(update_balance, target_user['user_id'], amount)
        await update.effective_message.reply_text(
            f"✅ Updated balance for user `{target_user['user_id']}` by {format_currency(amount)}."
        )
        return

    if action == 'numbers':
        numbers = await asyncio.to_thread(get_user_numbers, target_user['user_id'])
        if not numbers:
            await update.effective_message.reply_text("This user has no active rented numbers.")
            return
        lines = [f"📱 *Numbers for `{target_user['user_id']}`:*\n"]
        for number in numbers:
            lines.append(f"• `+{number['number']}` — status: {number['status']} — id: {number['id']}")
        await update.effective_message.reply_text("\n".join(lines), parse_mode='Markdown')
        return

    if action == 'addnumber':
        if len(args) < 4:
            await update.effective_message.reply_text("Usage: `/admin addnumber <target> <number> <verification_id> [tv/pva]`")
            return
        phone_number = args[2]
        verification_id = args[3]
        provider = args[4].lower() if len(args) > 4 else 'tv'
        
        if provider not in ['tv', 'pva']:
            await update.effective_message.reply_text("❌ Provider must be 'tv' or 'pva'.")
            return

        expiry = None
        status = 'active'
        
        try:
            if provider == 'tv':
                details = await asyncio.to_thread(textverified.reservations.details, verification_id)
                status = details.state.value
                if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                    cycle = await asyncio.to_thread(textverified.billing_cycles.get, details.billing_cycle_id)
                    expiry = cycle.billing_cycle_ends_at.isoformat()
            else:
                res = await asyncio.to_thread(pva_client.get_ltr_details, verification_id)
                if res and res.get('success'):
                    data = res.get('data', {})
                    status = data.get('status', 'active')
                    expiry = data.get('expiryDate') or data.get('expiresAt') or data.get('endTime')
        except Exception as e:
            logging.warning(f"Manual add sync failed: {e}")
            
        if not expiry:
            expiry = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)).isoformat()
            
        await asyncio.to_thread(add_number_record, target_user['user_id'], phone_number, verification_id, expires_at=expiry, status=status, provider=provider)
        
        await update.effective_message.reply_text(
            f"✅ Manually linked number `+{phone_number}` ({provider.upper()}) to user `{target_user['user_id']}`.\n"
            f"Status: `{status}`\nExpiry: `{expiry[:10]}`",
            parse_mode='Markdown'
        )
        return

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE, sort_by: str = 'created_at'):
    users = await asyncio.to_thread(get_all_users, sort_by=sort_by, limit=20)
    
    if not users:
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")]]
        if update.callback_query:
            await update.callback_query.edit_message_text("👥 *User List*\n\nNo users found in the system.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.effective_message.reply_text("👥 *User List*\n\nNo users found in the system.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    text = "👥 *User List* (Recent 20)\n"
    if sort_by == 'balance':
        text = "💰 *User List* (Top Balance)\n"
    
    keyboard = []
    for u in users:
        # Self-healing label logic
        if u['username']:
            name = u['username']
        elif u['first_name']:
            name = u['first_name']
        else:
            name = f"🆕 New User ({u['user_id']})"
            
        balance = format_currency(u['balance'])
        
        # Handle missing created_at timestamp
        joined = "Unknown"
        if u['created_at']:
            joined = u['created_at'][:10]
        
        button_text = f"{name} | {balance} | {joined}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"admin_user_manage_{u['user_id']}")])

    # Sorting options
    keyboard.append([
        InlineKeyboardButton("🆕 Recent", callback_data="admin_list_users_recent"),
        InlineKeyboardButton("💰 Top Balance", callback_data="admin_list_users_balance")
    ])
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_manage_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    user = await asyncio.to_thread(get_user, target_user_id)
    if not user:
        keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_list_users_recent")]]
        await update.callback_query.edit_message_text(f"❌ User `{target_user_id}` not found.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Referral count is called inside format_user_profile, which is blocking. 
    # Let's wrap the whole profile formatting if it does DB calls.
    profile_text = await asyncio.to_thread(format_user_profile, user)
    text = f"👤 *Managing User*\n\n{profile_text}"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Credit", callback_data=f"admin_credit_prompt_{target_user_id}"),
         InlineKeyboardButton("➖ Remove Credit", callback_data=f"admin_debit_prompt_{target_user_id}")],
        [InlineKeyboardButton("📱 View Their Numbers", callback_data=f"admin_view_nums_{target_user_id}")],
        [InlineKeyboardButton("🔢 Manage Numbers (Add/Rem)", callback_data=f"admin_nums_menu_{target_user_id}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="admin_list_users_recent")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_nums_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    user = await asyncio.to_thread(get_user, target_user_id)
    text = f"📱 *Number Management for `{user['first_name'] or target_user_id}`*"
    
    keyboard = [
        [InlineKeyboardButton("➕ Link New Number", callback_data=f"admin_addnum_prompt_{target_user_id}")],
        [InlineKeyboardButton("🗑 Remove Existing Number", callback_data=f"admin_removenum_prompt_{target_user_id}")],
        [InlineKeyboardButton("🔙 Back to User", callback_data=f"admin_user_manage_{target_user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Available commands:\n"
        "/start - Main menu\n"
        "/profile - View your balance and referral link\n"
        "/deposit - Add funds to your account\n"
        "/rent - Purchase a WhatsApp rental\n"
        "/mynumbers - Manage your numbers and retrieve codes\n"
        "/sync - Refresh your numbers status\n"
        "/help - Show this message"
    )

def sync_and_renew_worker(app: Application, loop: asyncio.AbstractEventLoop):
    """Worker function to handle auto-renewals in a separate thread."""
    try:
        logging.info("Checking for auto-renewals and syncing numbers for all providers (Background Thread)...")
        conn = get_db_connection()
        # Find all numbers that aren't marked as deleted/inactive
        numbers = conn.execute(
            "SELECT * FROM numbers WHERE status NOT IN ('deleted', 'expired', 'canceled')"
        ).fetchall()
        conn.close()

        for num in numbers:
            user_id = num['user_id']
            verification_id = num['verification_id']
            
            # CRITICAL FIX: Get provider directly from the database record
            provider = num['provider'] if 'provider' in num.keys() and num['provider'] else 'textverified'
            
            try:
                if provider in ['textverified', 'tv']:
                    # Fetch latest details from TextVerified
                    details = None
                    try:
                        details = textverified.reservations.details(verification_id)
                    except Exception as e:
                        is_404 = False
                        if hasattr(e, 'response') and e.response is not None:
                            if e.response.status_code == 404:
                                is_404 = True
                        elif "404" in str(e) or "Not Found" in str(e):
                            is_404 = True

                        if is_404:
                            logging.warning(f"Number {num['number']} not found on TextVerified (404). Marking as deleted.")
                            conn = get_db_connection()
                            conn.execute("UPDATE numbers SET status = 'deleted' WHERE id = ?", (num['id'],))
                            conn.commit()
                            conn.close()
                        else:
                            logging.error(f"Failed to sync TextVerified details for {num['number']} (temporary error): {e}")
                        continue

                    # 1. Sync Auto-Renew Status from Server
                    tv_auto_renew = getattr(details, 'is_included_for_next_renewal', None)
                    if tv_auto_renew is None:
                        tv_auto_renew = getattr(details, 'include_for_renewal', None)
                    if tv_auto_renew is None:
                        tv_auto_renew = getattr(details, 'renewable', None)
                    if tv_auto_renew is not None:
                        tv_auto_renew_int = 1 if tv_auto_renew else 0
                        if tv_auto_renew_int != num['auto_renew']:
                            logging.info(f"Syncing TV auto-renew for {num['number']}: {num['auto_renew']} -> {tv_auto_renew_int}")
                            update_auto_renew(num['id'], user_id, tv_auto_renew_int)
                            num = dict(num)
                            num['auto_renew'] = tv_auto_renew_int

                    # 2. Sync Expiry Date
                    tv_expiry = None
                    tv_expiry_dt = None
                    if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                        try:
                            cycle = textverified.billing_cycles.get(details.billing_cycle_id)
                            tv_expiry = cycle.billing_cycle_ends_at.isoformat()
                            tv_expiry_dt = cycle.billing_cycle_ends_at
                        except:
                            pass
                    
                    # --- PROACTIVE SAFETY CHECK for TextVerified ---
                    user = get_user(user_id)
                    lang = user['language'] or 'en'
                    
                    if not tv_expiry_dt and num['expires_at']:
                        try:
                            import dateutil.parser
                            tv_expiry_dt = dateutil.parser.parse(num['expires_at'])
                        except:
                            pass
                            
                    if tv_expiry_dt and num['auto_renew']:
                        now = datetime.datetime.now(tv_expiry_dt.tzinfo) if tv_expiry_dt.tzinfo else datetime.datetime.now(datetime.UTC)
                        time_diff = tv_expiry_dt - now
                        if time_diff.total_seconds() <= 86400: # <= 24 hours
                            if user['balance'] < SERVICE_PRICE:
                                logging.warning(f"Low balance for TV {num['number']}. Disabling server-side auto-renew.")
                                try:
                                    textverified.reservations.update_renewable(verification_id, include_for_renewal=False)
                                    update_auto_renew(num['id'], user_id, 0)
                                    num = dict(num)
                                    num['auto_renew'] = 0
                                    
                                    warning_msg = (
                                        f"⚠️ *Auto-Renewal Warning!*\n\nAuto-renew is disabled and subscription will be cancelled in 1 day for `+{num['number']}`."
                                        if lang == 'en' else
                                        f"⚠️ *تحذير التجديد التلقائي!*\n\nتم تعطيل التجديد التلقائي وسيتم إلغاء الاشتراك خلال يوم واحد للرقم `+{num['number']}`."
                                    )
                                    asyncio.run_coroutine_threadsafe(
                                        app.bot.send_message(chat_id=user_id, text=warning_msg, parse_mode='Markdown'),
                                        loop
                                    )
                                except Exception as e:
                                    logging.error(f"Failed to turn off server-side renewal for TV: {e}")
                                    
                    if tv_expiry and tv_expiry != num['expires_at']:
                        logging.info(f"Syncing expiry for {num['number']}: {num['expires_at']} -> {tv_expiry}")
                        
                        user = get_user(user_id)
                        lang = user['language'] or 'en'
                        
                        old_expiry_str = num['expires_at']
                        if old_expiry_str:
                            old_expiry = datetime.datetime.fromisoformat(old_expiry_str)
                            new_expiry = datetime.datetime.fromisoformat(tv_expiry)
                            
                            if new_expiry > old_expiry:
                                # If auto-renew was ON in the bot, check balance and deduct
                                if num['auto_renew']:
                                    if user['balance'] >= SERVICE_PRICE:
                                        update_balance(user_id, -SERVICE_PRICE)
                                        update_number_expiry(num['id'], tv_expiry)
                                        
                                        renewal_msg = (
                                            f"🔄 *Auto-Renewal Success!*\n\nYour WhatsApp number `+{num['number']}` has been renewed.\n💰 Cost: {format_currency(SERVICE_PRICE)}\n📅 New Expiry: `{tv_expiry[:10]}`"
                                            if lang == 'en' else
                                            f"🔄 *تم التجديد التلقائي بنجاح!*\n\nتم تجديد رقم الواتساب الخاص بك `+{num['number']}`.\n💰 التكلفة: {format_currency(SERVICE_PRICE)}\n📅 تنتهي الصلاحية في: `{tv_expiry[:10]}`"
                                        )
                                        
                                        asyncio.run_coroutine_threadsafe(
                                            app.bot.send_message(chat_id=user_id, text=renewal_msg, parse_mode='Markdown'),
                                            loop
                                        )
                                    else:
                                        # Insufficient balance (fallback)
                                        try:
                                            textverified.reservations.update_renewable(verification_id, include_for_renewal=False)
                                        except Exception as e:
                                            logging.error(f"Failed to disable server-side auto-renew for TV: {e}")
                                        update_auto_renew(num['id'], user_id, 0)
                                        
                                        warning_msg = (
                                            f"⚠️ *Auto-Renewal Warning!*\n\nAuto-renew is disabled and subscription will be cancelled in 1 day for `+{num['number']}`."
                                            if lang == 'en' else
                                            f"⚠️ *تحذير التجديد التلقائي!*\n\nتم تعطيل التجديد التلقائي وسيتم إلغاء الاشتراك خلال يوم واحد للرقم `+{num['number']}`."
                                        )
                                        
                                        asyncio.run_coroutine_threadsafe(
                                            app.bot.send_message(chat_id=user_id, text=warning_msg, parse_mode='Markdown'),
                                            loop
                                        )
                                else:
                                    # User turned off auto-renew in bot, but TV renewed it?
                                    update_number_expiry(num['id'], tv_expiry)
                            else:
                                update_number_expiry(num['id'], tv_expiry)

                    # 2. Sync Status
                    current_tv_status = details.state.value
                    if current_tv_status != num['status']:
                        logging.info(f"Status changed for {num['number']}: {num['status']} -> {current_tv_status}")
                        conn = get_db_connection()
                        conn.execute("UPDATE numbers SET status = ? WHERE id = ?", (current_tv_status, num['id']))
                        conn.commit()
                        conn.close()
                
                elif provider == 'pva':
                    # PVADeals renewal logic aligned with TextVerified
                    try:
                        res = pva_client.get_ltr_details(verification_id)
                        if res and res.get('success'):
                            data = res.get('data', {})
                            
                            # 1. Sync Auto-Renew Status from Server
                            server_auto_renew = data.get('autoRenewEnable')
                            if server_auto_renew is not None:
                                server_auto_renew_int = 1 if server_auto_renew else 0
                                if server_auto_renew_int != num['auto_renew']:
                                    logging.info(f"Syncing PVA auto-renew for {num['number']}: {num['auto_renew']} -> {server_auto_renew_int}")
                                    update_auto_renew(num['id'], user_id, server_auto_renew_int)
                                    # Update local num copy for subsequent checks in this loop
                                    num = dict(num)
                                    num['auto_renew'] = server_auto_renew_int

                            # 2. Sync Expiry Date
                            server_expiry = data.get('expiryDate') or data.get('expiresAt') or data.get('endTime')
                            
                            # 3. Sync Status (NEW: Hide flagged/expired numbers)
                            server_status = data.get('status', '').upper()
                            if server_status in ['FLAGGED', 'CANCELLED', 'EXPIRED']:
                                logging.info(f"PVA number {num['number']} is {server_status} on server. Marking as deleted.")
                                def mark_inactive():
                                    conn = get_db_connection()
                                    conn.execute("UPDATE numbers SET status = 'deleted' WHERE id = ?", (num['id'],))
                                    conn.commit()
                                    conn.close()
                                mark_inactive()
                                continue # Skip renewal checks for inactive numbers

                            if server_expiry:
                                import dateutil.parser
                                server_expiry_dt = dateutil.parser.parse(server_expiry)
                                now = datetime.datetime.now(server_expiry_dt.tzinfo) if server_expiry_dt.tzinfo else datetime.datetime.now(datetime.UTC)
                                
                                # --- PROACTIVE SAFETY CHECK (1 day before) ---
                                # If expiring within 24h, auto-renew is ON, but balance is low -> TURN OFF server side
                                user = get_user(user_id)
                                lang = user['language'] or 'en'
                                time_diff = server_expiry_dt - now
                                
                                if time_diff.total_seconds() <= 86400 and num['auto_renew']:
                                    if user['balance'] < PVADEALS_PRICE:
                                        logging.warning(f"Low balance for PVA {num['number']}. Disabling server-side auto-renew.")
                                        try:
                                            pva_client.set_auto_renew(verification_id, False)
                                            update_auto_renew(num['id'], user_id, 0)
                                            num = dict(num)
                                            num['auto_renew'] = 0
                                            
                                            warning_msg = (
                                                f"⚠️ *Auto-Renewal Warning!*\n\nAuto-renew is disabled and subscription will be cancelled in 1 day for `+{num['number']}`."
                                                if lang == 'en' else
                                                f"⚠️ *تحذير التجديد التلقائي!*\n\nتم تعطيل التجديد التلقائي وسيتم إلغاء الاشتراك خلال يوم واحد للرقم `+{num['number']}`."
                                            )
                                            asyncio.run_coroutine_threadsafe(
                                                app.bot.send_message(chat_id=user_id, text=warning_msg, parse_mode='Markdown'),
                                                loop
                                            )
                                        except Exception as e:
                                            logging.error(f"Failed to turn off server-side renewal for PVA: {e}")

                                # --- SYNC & RENEWAL DETECTION ---
                                if server_expiry != num['expires_at']:
                                    logging.info(f"Syncing PVADeals expiry for {num['number']}: {num['expires_at']} -> {server_expiry}")
                                    
                                    old_expiry_str = num['expires_at']
                                    if old_expiry_str:
                                        old_dt = dateutil.parser.parse(old_expiry_str)
                                        
                                        if server_expiry_dt > old_dt:
                                            # Server renewed it!
                                            if num['auto_renew']:
                                                if user['balance'] >= PVADEALS_PRICE:
                                                    update_balance(user_id, -PVADEALS_PRICE)
                                                    update_number_expiry(num['id'], server_expiry)
                                                    
                                                    renewal_msg = (
                                                        f"🔄 *Auto-Renewal Success!*\n\nYour WhatsApp number `+{num['number']}` (Basic) has been renewed.\n💰 Cost: {format_currency(PVADEALS_PRICE)}\n📅 New Expiry: `{server_expiry[:10]}`"
                                                        if lang == 'en' else
                                                        f"🔄 *تم التجديد التلقائي بنجاح!*\n\nتم تجديد رقم الواتساب (عادي) الخاص بك `+{num['number']}`.\n💰 التكلفة: {format_currency(PVADEALS_PRICE)}\n📅 تنتهي الصلاحية في: `{server_expiry[:10]}`"
                                                    )
                                                    
                                                    asyncio.run_coroutine_threadsafe(
                                                        app.bot.send_message(chat_id=user_id, text=renewal_msg, parse_mode='Markdown'),
                                                        loop
                                                    )
                                                else:
                                                    # Insufficient balance (server already renewed it? Disable server renewal and notify user)
                                                    try:
                                                        res_det = pva_client.get_ltr_details(verification_id)
                                                        if res_det and res_det.get('success'):
                                                            current_state = res_det.get('data', {}).get('autoRenewEnable', False)
                                                            if current_state:
                                                                pva_client.set_auto_renew(verification_id)
                                                    except Exception as e:
                                                        logging.error(f"Failed to disable server-side auto-renew for PVA: {e}")
                                                    update_auto_renew(num['id'], user_id, 0)
                                                    update_number_expiry(num['id'], server_expiry)
                                                    
                                                    warning_msg = (
                                                        f"⚠️ *Auto-Renewal Warning!*\n\nAuto-renew is disabled and subscription will be cancelled in 1 day for `+{num['number']}`."
                                                        if lang == 'en' else
                                                        f"⚠️ *تحذير التجديد التلقائي!*\n\nتم تعطيل التجديد التلقائي وسيتم إلغاء الاشتراك خلال يوم واحد للرقم `+{num['number']}`."
                                                    )
                                                    asyncio.run_coroutine_threadsafe(
                                                        app.bot.send_message(chat_id=user_id, text=warning_msg, parse_mode='Markdown'),
                                                        loop
                                                    )
                                            else:
                                                # Sync anyway if renewed externally
                                                update_number_expiry(num['id'], server_expiry)
                                        else:
                                            # Dates match or server is behind? Just sync if server is newer
                                            update_number_expiry(num['id'], server_expiry)
                                    else:
                                        # No local date? Set it.
                                        update_number_expiry(num['id'], server_expiry)

                    except Exception as e:
                        is_404 = False
                        if hasattr(e, 'response') and e.response is not None:
                            if e.response.status_code == 404:
                                is_404 = True
                        elif "404" in str(e) or "Request not found" in str(e):
                            is_404 = True

                        if is_404:
                            logging.warning(f"PVA number {num['number']} not found on PVADeals (404). Marking as deleted.")
                            conn = get_db_connection()
                            conn.execute("UPDATE numbers SET status = 'deleted' WHERE id = ?", (num['id'],))
                            conn.commit()
                            conn.close()
                        else:
                            logging.error(f"PVADeals sync failed for {num['number']}: {e}")

            except Exception as e:
                logging.error(f"Error syncing number {num['number']}: {e}")

    except Exception as e:
        logging.error(f"Error in sync_and_renew_worker: {e}")

async def auto_renewal_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job to handle auto-renewals and sync numbers for all providers."""
    app = context.application
    loop = asyncio.get_running_loop()
    threading.Thread(target=sync_and_renew_worker, args=(app, loop), daemon=True).start()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    logging.info(f"Button clicked by {user_id}: {data}")
    
    # Self-healing user identification: capture missing info on every interaction
    await asyncio.to_thread(update_user_info, user_id, username=update.effective_user.username, first_name=update.effective_user.first_name)
    
    user = await asyncio.to_thread(get_user, user_id)
    lang = user['language'] if user and user['language'] else 'en'
    s = STRINGS[lang]

    if data == 'main_lang':
        await show_language_selection(update, context)
        return

    if data.startswith('set_lang_'):
        new_lang = data.split('_')[2]
        await asyncio.to_thread(set_user_lang, user_id, new_lang)
        await query.edit_message_text(f"✅ Language set to {new_lang.upper()} / تم تغيير اللغة إلى {new_lang.upper()}!")
        await start(update, context)
        return

    if data.startswith('admin_nums_menu_'):
        target_id = int(data.split('_')[3])
        await admin_nums_menu(update, context, target_id)
        return

    if data.startswith('admin_addnum_prompt_'):
        target_id = int(data.split('_')[3])
        context.user_data['admin_target_id'] = target_id
        
        keyboard = [
            [InlineKeyboardButton("Premium (TextVerified)", callback_data=f"admin_select_prov_tv_{target_id}"),
             InlineKeyboardButton("Basic (PVADeals)", callback_data=f"admin_select_prov_pva_{target_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"admin_nums_menu_{target_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"➕ *Step 1: Select Provider for `{target_id}`*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    if data.startswith('admin_select_prov_'):
        parts = data.split('_')
        provider = parts[3]
        target_id = int(parts[4])
        
        context.user_data['admin_action'] = 'addnumber'
        context.user_data['admin_provider'] = provider
        context.user_data['admin_target_id'] = target_id
        
        prov_name = "Premium (TV)" if provider == 'tv' else "Basic (PVA)"
        hint = (
            "\n💡 *Hint:* For PVA, you can find the ID in your dashboard under 'Long Term Rentals' (it's the code in the URL)."
            if provider == 'pva' else ""
        )
        await query.edit_message_text(
            f"➕ *Step 2: Enter Details ({prov_name})*\n\nTarget User: `{target_id}`\n\nPlease type the number and verification ID in this format:\n`NUMBER VERIF_ID`\n(e.g., `1234567890 {('TV_123' if provider == 'tv' else 'PVA_123')}`){hint}",
            parse_mode='Markdown'
        )
        return

    if data.startswith('admin_credit_prompt_') or data.startswith('admin_debit_prompt_'):
        parts = data.split('_')
        action = parts[1] # credit or debit
        t_id = int(parts[3])
        
        context.user_data['admin_action'] = f'credit_{action}'
        context.user_data['admin_target_id'] = t_id
        
        action_title = "Add Credit to" if action == 'credit' else "Remove Credit from"
        action_emoji = "➕" if action == 'credit' else "➖"
        
        amounts = [5, 10, 25, 50, 100]
        keyboard = []
        row = []
        for amt in amounts:
            row.append(InlineKeyboardButton(f"${amt}", callback_data=f"admin_{action}_{t_id}_{amt}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"admin_user_manage_{t_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg_text = (
            f"{action_emoji} *{action_title} User `{t_id}`*\n\n"
            f"Please **type the exact amount** in chat (e.g. `12.5` or `3`), or select a quick preset below:"
        )
        await query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode='Markdown')
        return

    if data.startswith('admin_view_nums_'):
        t_id = int(data.split('_')[3])
        numbers = await asyncio.to_thread(get_user_numbers, t_id)
        
        # 1. Edit the callback query message to act as the header
        text = f"📱 *Numbers for User `{t_id}`:*"
        if not numbers:
            text += "\n\nThis user has no active numbers."
            keyboard = [[InlineKeyboardButton("🔙 Back to User", callback_data=f"admin_user_manage_{t_id}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
            
        keyboard = [[InlineKeyboardButton("🔙 Back to User", callback_data=f"admin_user_manage_{t_id}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        # 2. Get admin language settings
        admin_user = await asyncio.to_thread(get_user, user_id)
        admin_lang = admin_user['language'] if admin_user and admin_user['language'] else 'en'
        s = STRINGS[admin_lang]

        # 3. Send each number as a separate message with control buttons
        for number in numbers:
            status_icon = "✅" if number['status'] in ['active', 'renewableActive'] else "❌"
            auto_renew_status = s['status_active'] if number['auto_renew'] else s['status_disabled']
            expiry_info = ""
            
            if number['expires_at']:
                try:
                    import dateutil.parser
                    expiry_dt = dateutil.parser.parse(number['expires_at'])
                    expiry_date = expiry_dt.strftime('%Y-%m-%d')
                    
                    # Calculate time left
                    now = datetime.datetime.now(expiry_dt.tzinfo) if expiry_dt.tzinfo else datetime.datetime.now(datetime.UTC)
                    diff = expiry_dt - now
                    
                    if diff.total_seconds() <= 0:
                        time_left = s['label_expired']
                    elif diff.days > 0:
                        time_left = f"{diff.days}d {s['label_left']}"
                    else:
                        hours = int(diff.total_seconds() // 3600)
                        time_left = f"{hours}h {s['label_left']}"
                    
                    expiry_info = f"\n{s['label_expires']}: `{expiry_date}` ({time_left})"
                except Exception as e:
                    logging.error(f"Date parsing failed for {number['number']}: {e}")
                    expiry_info = f"\n{s['label_expires']}: `{number['expires_at'][:10]}`"

            number_text = (
                f"{status_icon} {s['label_number']}: `+{number['number']}`\n"
                f"{s['label_service']}: {number['service'].capitalize()}\n"
                f"{s['label_auto_renew']}: {auto_renew_status}"
                f"{expiry_info}"
            )

            # Define admin callbacks that encode number id and target user id
            buttons = [
                [InlineKeyboardButton(s['btn_get_code'], callback_data=f"admin_code_{number['id']}_{t_id}"),
                 InlineKeyboardButton(s['btn_refund'], callback_data=f"admin_refund_{number['id']}_{t_id}")]
            ]

            if number['auto_renew']:
                buttons.append([InlineKeyboardButton(s['btn_cancel_sub'], callback_data=f"admin_cancel_{number['id']}_{t_id}")])
            else:
                buttons.append([InlineKeyboardButton(s['btn_enable_renew'], callback_data=f"admin_enable_{number['id']}_{t_id}")])

            reply_markup = InlineKeyboardMarkup(buttons)
            await context.bot.send_message(chat_id=user_id, text=number_text, reply_markup=reply_markup, parse_mode='Markdown')
        return

    if data.startswith('admin_removenum_prompt_'):
        t_id = int(data.split('_')[3])
        numbers = await asyncio.to_thread(get_user_numbers, t_id)
        if not numbers:
            text = f"🗑 *Remove Number for `{t_id}`:*\n\nThis user has no active numbers to remove."
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=f"admin_user_manage_{t_id}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        keyboard = []
        for number in numbers:
            keyboard.append([InlineKeyboardButton(f"❌ Remove +{number['number']}", callback_data=f"admin_do_remove_{number['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"admin_user_manage_{t_id}")])
        await query.edit_message_text(f"🗑 Select number to remove for `{t_id}`:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith('admin_menu_'):
        action = data.split('_')[2]
        context.user_data['admin_action'] = action
        await query.edit_message_text(
            f"🔍 *Admin: {action.capitalize()} User*\n\nPlease type the User ID or @username of the target user:",
            parse_mode='Markdown'
        )
        return

    if data.startswith('admin_do_remove_'):
        number_id = int(data.split('_')[3])
        
        def remove_number():
            conn = get_db_connection()
            num = conn.execute("SELECT * FROM numbers WHERE id = ?", (number_id,)).fetchone()
            if num:
                conn.execute("UPDATE numbers SET status = 'deleted' WHERE id = ?", (number_id,))
                conn.commit()
            conn.close()
            return num

        num_row = await asyncio.to_thread(remove_number)
        if num_row:
            await query.edit_message_text(f"✅ Number `+{num_row['number']}` has been removed from user `{num_row['user_id']}` locally.")
        else:
            keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_list_users_recent")]]
            await query.edit_message_text("❌ Number not found or already removed.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith('admin_credit_') or data.startswith('admin_debit_'):
        context.user_data.pop('admin_action', None)
        context.user_data.pop('admin_target_id', None)
        
        parts = data.split('_')
        action_type = parts[1] # credit or debit
        target_id = int(parts[2])
        amount = float(parts[3])
        
        target_user = await asyncio.to_thread(get_user, target_id)
        if not target_user:
            keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_list_users_recent")]]
            await query.edit_message_text("❌ User no longer exists.", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if action_type == 'debit':
            amount = -amount

        await asyncio.to_thread(update_balance, target_id, amount)
        new_balance = (await asyncio.to_thread(get_user, target_id))['balance']
        
        await query.edit_message_text(
            f"✅ *Balance Updated*\n\n"
            f"User: @{target_user['username']} (`{target_id}`)\n"
            f"Action: {action_type.capitalize()} {format_currency(abs(amount))}\n"
            f"New Balance: *{format_currency(new_balance)}*",
            parse_mode='Markdown'
        )
        return

    if data == 'deposit_method_crypto':
        keyboard = []
        row = []
        for amt in DEPOSIT_AMOUNTS:
            row.append(InlineKeyboardButton(f"${amt}", callback_data=f"deposit_amt_{amt}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            s['deposit_select_amt'],
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    if data == 'deposit_method_shamcash':
        await query.edit_message_text(
            s['shamcash_info'],
            parse_mode='Markdown'
        )
        context.user_data['user_action'] = 'shamcash_amt'
        return

    # --- ADMIN ACTIONS ---
    if data == 'admin_pending_shamcash':
        def get_pending_shamcash():
            conn = get_db_connection()
            p = conn.execute("SELECT * FROM manual_deposits WHERE status = 'pending' ORDER BY created_at DESC").fetchall()
            conn.close()
            return p

        pending = await asyncio.to_thread(get_pending_shamcash)

        if not pending:
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")]]
            await query.edit_message_text("📥 *ShamCash Requests*\n\nNo pending ShamCash requests.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        keyboard = []
        for req in pending:
            user_target = await asyncio.to_thread(get_user, req['user_id'])
            user_name = f"@{user_target['username']}" if user_target and user_target['username'] else f"{user_target['first_name'] or 'User'} ({req['user_id']})"
            btn_text = f"👤 {user_name} - {format_currency(req['amount'])} ({req['created_at'][:10]})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"admin_sham_view_{req['id']}")])
            
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")])
        
        await query.edit_message_text(
            f"📥 *Pending ShamCash Requests ({len(pending)}):*\n\nSelect a request to view details and receipt:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

    if data.startswith('admin_sham_view_'):
        req_id = int(data.split('_')[3])
        
        def get_shamcash_request(r_id):
            conn = get_db_connection()
            r = conn.execute("SELECT * FROM manual_deposits WHERE id = ?", (r_id,)).fetchone()
            conn.close()
            return r

        req = await asyncio.to_thread(get_shamcash_request, req_id)
        if not req:
            keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_pending_shamcash")]]
            await query.edit_message_text("❌ Request not found.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        user_target = await asyncio.to_thread(get_user, req['user_id'])
        user_name = f"@{user_target['username']}" if user_target and user_target['username'] else f"{user_target['first_name'] or 'User'} ({req['user_id']})"
        
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"admin_sham_approve_{req['id']}"),
             InlineKeyboardButton("❌ Decline", callback_data=f"admin_sham_decline_{req['id']}")],
            [InlineKeyboardButton("🔙 Back to List", callback_data="admin_pending_shamcash")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"📥 *Pending ShamCash Request Details*\n\n"
            f"👤 *User:* {user_name}\n"
            f"💰 *Amount:* {format_currency(req['amount'])}\n"
            f"📅 *Date:* `{req['created_at'][:19]}`\n"
            f"🆔 *Request ID:* `{req['id']}`\n\n"
            "The receipt (PDF) has been sent below.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        try:
            await context.bot.send_document(
                chat_id=ADMIN_ID, 
                document=req['receipt_file_id'], 
                caption=f"Receipt for User {user_name} - {format_currency(req['amount'])}"
            )
        except Exception as e:
            logging.error(f"Failed to send PDF receipt: {e}")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❌ Failed to display receipt document on Telegram: {e}"
            )
        return

    if data == 'admin_list_users_recent':
        logging.info("Admin: Listing users sorted by recent")
        await admin_list_users(update, context, sort_by='created_at')
        return

    if data == 'admin_list_users_balance':
        logging.info("Admin: Listing users sorted by balance")
        await admin_list_users(update, context, sort_by='balance')
        return

    if data == 'admin_main':
        logging.info(f"Admin: Back to main menu for {user_id}")
        await admin_command(update, context)
        return

    if data.startswith('admin_user_manage_'):
        t_id = int(data.split('_')[3])
        await admin_manage_user_menu(update, context, t_id)
        return

    if data.startswith('admin_sham_approve_') or data.startswith('admin_sham_decline_'):
        parts = data.split('_')
        is_approve = parts[2] == 'approve'
        req_id = int(parts[3])

        def process_shamcash():
            conn = get_db_connection()
            r = conn.execute("SELECT * FROM manual_deposits WHERE id = ?", (req_id,)).fetchone()
            
            if not r or r['status'] != 'pending':
                conn.close()
                return None, "Request already processed or not found."
            
            if is_approve:
                conn.execute("UPDATE manual_deposits SET status = 'approved', updated_at = ? WHERE id = ?", (get_timestamp(), req_id))
            else:
                conn.execute("UPDATE manual_deposits SET status = 'declined', updated_at = ? WHERE id = ?", (get_timestamp(), req_id))
            
            conn.commit()
            conn.close()
            return r, None

        req, error = await asyncio.to_thread(process_shamcash)

        if error:
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")]]
            await query.edit_message_text(f"❌ {error}", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        user_target = await asyncio.to_thread(get_user, req['user_id'])
        u_lang = user_target['language'] or 'en'

        keyboard = [[InlineKeyboardButton("🔙 Back to Pending List", callback_data="admin_pending_shamcash")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if is_approve:
            await asyncio.to_thread(update_balance, req['user_id'], req['amount'])
            await asyncio.to_thread(check_and_reward_referrer, req['user_id'], 'manual', req_id)
            await context.bot.send_message(chat_id=req['user_id'], text=STRINGS[u_lang]['shamcash_approved_msg'].format(amount=format_currency(req['amount'])))
            await query.edit_message_text(f"✅ Approved {format_currency(req['amount'])} for user `{req['user_id']}`", reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=req['user_id'], text=STRINGS[u_lang]['shamcash_declined_msg'])
            await query.edit_message_text(f"❌ Declined request from user `{req['user_id']}`", reply_markup=reply_markup)
        return

    if data.startswith('deposit_amt_'):
        amount_str = data.split('_')[2]
        amount = float(amount_str)
        invoice_data = await asyncio.to_thread(create_invoice, amount, user_id)
        if not invoice_data:
            await query.edit_message_text("Unable to create a deposit right now. Please try again later.")
            return

        invoice_url = invoice_data.get('invoice_url') or invoice_data.get('invoiceUrl')
        await query.edit_message_text(
            s['deposit_created'].format(
                amount=format_currency(amount),
                url=invoice_url
            ),
            parse_mode='Markdown',
            disable_web_page_preview=False
        )
        return

    if data == 'main_rent':
        await rent(update, context)
        return
    if data == 'rent_tv':
        await process_rent(update, context, 'tv')
        return
    if data == 'rent_pva':
        await process_rent(update, context, 'pva')
        return
    if data == 'main_deposit':
        await deposit(update, context)
        return
    if data == 'main_profile':
        await profile(update, context)
        return
    if data == 'main_numbers':
        await mynumbers(update, context)
        return

    if data.startswith('admin_code_') or data.startswith('admin_refund_') or data.startswith('admin_cancel_') or data.startswith('admin_enable_'):
        # Guard: only admin can execute admin callbacks
        if not is_admin(user_id):
            await query.answer("Access denied.", show_alert=True)
            return

        parts = data.split('_')
        action = parts[1] # code, refund, cancel, or enable
        number_id = int(parts[2])
        t_id = int(parts[3])
        
        number_row = await asyncio.to_thread(get_number_record, number_id, t_id)
        if not number_row:
            await query.edit_message_text("❌ Number not found.")
            return

        admin_user = await asyncio.to_thread(get_user, user_id)
        admin_lang = admin_user['language'] if admin_user and admin_user['language'] else 'en'
        s = STRINGS[admin_lang]

        if action == 'code':
            request_time = datetime.datetime.now(datetime.timezone.utc)
            await asyncio.to_thread(mark_code_requested, number_row['id'])
            sms_data = await poll_sms_code(
                number_row['verification_id'], 
                provider=dict(number_row).get('provider', 'tv'),
                query=query,
                number_str=number_row['number'],
                lang=admin_lang,
                min_timestamp=request_time
            )

            if sms_data and sms_data.get('code'):
                await query.edit_message_text(
                    s['code_received'].format(
                        number=number_row['number'],
                        code=sms_data['code'],
                        sms=sms_data['sms']
                    ),
                    parse_mode='Markdown'
                )
            else:
                total_secs = SMS_POLL_ATTEMPTS * SMS_POLL_DELAY
                if admin_lang == 'ar':
                    no_code_text = (
                        f"❌ *لم يتم استلام الكود*\n\n"
                        f"تم فحص الكود لمدة {total_secs} ثانية ولم يصل رمز التحقق للرقم `+{number_row['number']}`.\n\n"
                        f"👉 يرجى المحاولة مرة أخرى."
                    )
                else:
                    no_code_text = (
                        f"❌ *No Code Received*\n\n"
                        f"Checked for {total_secs} seconds but no code arrived for `+{number_row['number']}`.\n\n"
                        f"👉 Please try again."
                    )
                await query.edit_message_text(no_code_text, parse_mode='Markdown')
            return

        elif action == 'refund':
            await query.edit_message_text("⏳ Processing refund on server...")
            try:
                price = SERVICE_PRICE
                if number_row['provider'] in ['textverified', 'tv']:
                    await asyncio.to_thread(textverified.reservations.refund_renewable, number_row['verification_id'])
                else:
                    price = PVADEALS_PRICE
                    await asyncio.to_thread(pva_client.flag_number, number_row['verification_id'])
                    
                def mark_refunded():
                    conn = get_db_connection()
                    conn.execute("UPDATE numbers SET status = 'refunded' WHERE id = ?", (number_id,))
                    conn.commit()
                    conn.close()

                await asyncio.to_thread(mark_refunded)
                await asyncio.to_thread(update_balance, t_id, price)
                
                await query.edit_message_text(
                    f"✅ Number `+{number_row['number']}` has been refunded.\n💰 {format_currency(price)} credited to user `{t_id}`.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logging.error(f"Admin refund failed: {e}")
                await query.edit_message_text(f"❌ Refund failed for +{number_row['number']}: {e}")
            return

        elif action in ['cancel', 'enable']:
            status_val = 1 if action == 'enable' else 0
            if number_row['provider'] in ['textverified', 'tv']:
                try:
                    await asyncio.to_thread(
                        textverified.reservations.update_renewable,
                        number_row['verification_id'],
                        include_for_renewal=(action == 'enable')
                    )
                except Exception as e:
                    logging.error(f"Admin failed to update TV renewal: {e}")
            elif number_row['provider'] == 'pva':
                try:
                    res = await asyncio.to_thread(pva_client.get_ltr_details, number_row['verification_id'])
                    if res and res.get('success'):
                        current_state = res.get('data', {}).get('autoRenewEnable', False)
                        target_state = (action == 'enable')
                        if current_state != target_state:
                            await asyncio.to_thread(pva_client.set_auto_renew, number_row['verification_id'])
                except Exception as e:
                    logging.error(f"Admin failed to update PVA renewal: {e}")
            
            await asyncio.to_thread(update_auto_renew, number_id, t_id, status_val)
            msg = f"🔄 *Auto-Renewal Enabled for user `{t_id}`*" if action == 'enable' else f"🛑 *Subscription Cancelled for user `{t_id}`*"
            await query.edit_message_text(msg, parse_mode='Markdown')
            return

    if data.startswith('sub_cancel_'):
        number_id = int(data.split('_')[2])
        number_row = await asyncio.to_thread(get_number_record, number_id, user_id)
        
        if number_row:
            if number_row['provider'] in ['textverified', 'tv']:
                try:
                    await asyncio.to_thread(
                        textverified.reservations.update_renewable,
                        number_row['verification_id'], 
                        include_for_renewal=False
                    )
                except Exception as e:
                    logging.error(f"Failed to cancel subscription on TV: {e}")
            elif number_row['provider'] == 'pva':
                try:
                    # PVA is a toggle, so check current state first
                    res = await asyncio.to_thread(pva_client.get_ltr_details, number_row['verification_id'])
                    if res and res.get('success'):
                        current_state = res.get('data', {}).get('autoRenewEnable', False)
                        if current_state: # Only toggle if it's currently ON
                            await asyncio.to_thread(pva_client.set_auto_renew, number_row['verification_id'])
                except Exception as e:
                    logging.error(f"Failed to cancel subscription on PVA: {e}")
            
            await asyncio.to_thread(update_auto_renew, number_id, user_id, 0)
            
            await query.edit_message_text(
                "🛑 *Subscription Cancelled*" if lang == 'en' else "🛑 *تم إلغاء الاشتراك*",
                parse_mode='Markdown'
            )
        return

    if data.startswith('sub_enable_'):
        number_id = int(data.split('_')[2])
        number_row = await asyncio.to_thread(get_number_record, number_id, user_id)
        
        if number_row:
            if number_row['provider'] in ['textverified', 'tv']:
                try:
                    await asyncio.to_thread(
                        textverified.reservations.update_renewable,
                        number_row['verification_id'], 
                        include_for_renewal=True
                    )
                except Exception as e:
                    logging.error(f"Failed to enable subscription on TV: {e}")
            elif number_row['provider'] == 'pva':
                try:
                    # PVA is a toggle, so check current state first
                    res = await asyncio.to_thread(pva_client.get_ltr_details, number_row['verification_id'])
                    if res and res.get('success'):
                        current_state = res.get('data', {}).get('autoRenewEnable', False)
                        if not current_state: # Only toggle if it's currently OFF
                            await asyncio.to_thread(pva_client.set_auto_renew, number_row['verification_id'])
                except Exception as e:
                    logging.error(f"Failed to enable subscription on PVA: {e}")
            
            await asyncio.to_thread(update_auto_renew, number_id, user_id, 1)
            
            await query.edit_message_text(
                "🔄 *Auto-Renewal Enabled*" if lang == 'en' else "🔄 *تم تفعيل التجديد*",
                parse_mode='Markdown'
            )
        return

    if data.startswith('sub_refund_'):
        number_id = int(data.split('_')[2])
        number_row = await asyncio.to_thread(get_number_record, number_id, user_id)
        
        if not number_row:
            await query.edit_message_text("❌ Number not found or does not belong to you.")
            return

        # NEW REFUND SAFETY CHECK
        code_requested = number_row['code_requested'] if 'code_requested' in number_row.keys() else 0
        code_received = number_row['code_received'] if 'code_received' in number_row.keys() else 0
        
        if not code_requested:
            msg = (
                "❌ *Refund Denied*\n\nYou can only request a refund after trying to retrieve a code using the 'Get Code' button."
                if lang == 'en' else
                "❌ *تم رفض استرداد الأموال*\n\nيمكنك طلب استرداد الأموال فقط بعد محاولة الحصول على الرمز باستخدام زر 'الحصول على الكود'."
            )
            await query.edit_message_text(msg, parse_mode='Markdown')
            return
            
        if code_received:
            msg = (
                "❌ *Refund Denied*\n\nThis number has already received a code. Refunds are only allowed if no code was received."
                if lang == 'en' else
                "❌ *تم رفض استرداد الأموال*\n\nلقد تلقى هذا الرقم رمزاً بالفعل. يسمح بالاسترداد فقط إذا لم يتم استلام أي رمز."
            )
            await query.edit_message_text(msg, parse_mode='Markdown')
            return

        await query.edit_message_text(s['refund_processing'])
        
        try:
            price = SERVICE_PRICE
            if number_row['provider'] == 'tv':
                await asyncio.to_thread(textverified.reservations.refund_renewable, number_row['verification_id'])
            else:
                price = PVADEALS_PRICE
                # PVADeals flagging/refund logic
                await asyncio.to_thread(pva_client.flag_number, number_row['verification_id'])
            
            def mark_refunded():
                conn = get_db_connection()
                conn.execute("UPDATE numbers SET status = 'refunded' WHERE id = ?", (number_id,))
                conn.commit()
                conn.close()

            await asyncio.to_thread(mark_refunded)
            await asyncio.to_thread(update_balance, user_id, price)
            
            await query.edit_message_text(
                s['refund_success'].format(
                    number=number_row['number'],
                    price=format_currency(price)
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"Refund failed for {number_row['number']}: {e}")
            await query.edit_message_text(
                s['refund_fail'].format(number=number_row['number']),
                parse_mode='Markdown'
            )
        return

    if data.startswith('code_'):
        number_id = int(data.split('_', 1)[1])
        number_row = await asyncio.to_thread(get_number_record, number_id, user_id)
        if not number_row:
            await query.edit_message_text("This number is not found or does not belong to you.")
            return

        request_time = datetime.datetime.now(datetime.timezone.utc)
        await asyncio.to_thread(mark_code_requested, number_id)
        sms_data = await poll_sms_code(
            number_row['verification_id'], 
            provider=dict(number_row).get('provider', 'tv'),
            query=query,
            number_str=number_row['number'],
            lang=lang,
            min_timestamp=request_time
        )

        if sms_data and sms_data.get('code'):
            await query.edit_message_text(
                s['code_received'].format(
                    number=number_row['number'],
                    code=sms_data['code'],
                    sms=sms_data['sms']
                ),
                parse_mode='Markdown'
            )
        else:
            total_secs = SMS_POLL_ATTEMPTS * SMS_POLL_DELAY
            if lang == 'ar':
                no_code_text = (
                    f"❌ *لم يتم استلام الكود*\n\n"
                    f"تم فحص الكود لمدة {total_secs} ثانية ولم يصل رمز التحقق للرقم `+{number_row['number']}`.\n\n"
                    f"👉 إذا كنت قد طلبت كود الواتساب للتو، يرجى الانتظار بضع ثوان والضغط على **📩 طلب الكود** مرة أخرى."
                )
            else:
                no_code_text = (
                    f"❌ *No Code Received*\n\n"
                    f"We checked for {total_secs} seconds but no verification code arrived for `+{number_row['number']}`.\n\n"
                    f"👉 If you just requested the code in WhatsApp, please wait a few seconds and tap **📩 Get Code** again."
                )
            await query.edit_message_text(no_code_text, parse_mode='Markdown')
        return

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Self-healing user identification: capture missing info on every interaction
    await asyncio.to_thread(update_user_info, user_id, username=update.effective_user.username, first_name=update.effective_user.first_name)
    
    user = await asyncio.to_thread(get_user, user_id)
    lang = user['language'] or 'en'
    s = STRINGS[lang]
    
    # --- USER ACTIONS ---
    if context.user_data and context.user_data.get('user_action'):
        action = context.user_data.pop('user_action')
        if action == 'shamcash_amt':
            try:
                amt = float(update.message.text.strip())
                context.user_data['sham_amt'] = amt
                
                # Send QR Code and Instructions
                if os.path.exists(SHAMCASH_QR_PATH):
                    with open(SHAMCASH_QR_PATH, 'rb') as photo:
                        await update.effective_message.reply_photo(
                            photo=photo,
                            caption=s['shamcash_payment_info'].format(
                                amount=format_currency(amt),
                                id=SHAMCASH_ID
                            ),
                            parse_mode='Markdown'
                        )
                else:
                    await update.effective_message.reply_text(
                        s['shamcash_payment_info'].format(
                            amount=format_currency(amt),
                            id=SHAMCASH_ID
                        ),
                        parse_mode='Markdown'
                    )
                
                await update.effective_message.reply_text(s['shamcash_receipt'], parse_mode='Markdown')
                context.user_data['user_action'] = 'shamcash_pdf'
            except ValueError:
                await update.effective_message.reply_text("❌ Please enter a valid number.")
            return

    # --- ADMIN STATE HANDLING ---
    if context.user_data and context.user_data.get('admin_action'):
        if not is_admin(user_id):
            logging.warning(f"Unauthorized admin state access by {user_id}")
            context.user_data.clear()
            return

        action = context.user_data.get('admin_action')
        logging.info(f"Admin action '{action}' in progress for {user_id}")
        target_user_id = context.user_data.get('admin_target_id')
        
        # Flow B: Target user already known from button click (e.g., credit input or addnumber)
        if target_user_id and action in ['credit_credit', 'credit_debit']:
            context.user_data.pop('admin_action', None)
            context.user_data.pop('admin_target_id', None)
            
            target_user = await asyncio.to_thread(get_user, target_user_id)
            if not target_user:
                await update.effective_message.reply_text("❌ Target user no longer exists.")
                return
            
            t_id = target_user['user_id']
            t_name = target_user['username'] or target_user['first_name'] or str(t_id)
            
            try:
                raw_text = update.message.text.strip().replace('$', '')
                amount = float(raw_text)
                if amount <= 0:
                    await update.effective_message.reply_text("❌ Amount must be greater than 0.")
                    return
                
                if action == 'credit_debit':
                    amount = -amount
                
                await asyncio.to_thread(update_balance, t_id, amount)
                updated_user = await asyncio.to_thread(get_user, t_id)
                new_bal = updated_user['balance']
                
                action_word = "Added" if amount > 0 else "Removed"
                formatted_amt = format_currency(abs(amount))
                formatted_new_bal = format_currency(new_bal)
                
                await update.effective_message.reply_text(
                    f"✅ *Balance Updated*\n\n"
                    f"User: `{t_name}` (`{t_id}`)\n"
                    f"Action: {action_word} {formatted_amt}\n"
                    f"New Balance: *{formatted_new_bal}*",
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.effective_message.reply_text("❌ Invalid amount. Please enter a valid number (e.g., `10` or `12.50`).", parse_mode='Markdown')
            return

        if target_user_id and action == 'addnumber':
            context.user_data.pop('admin_action')
            context.user_data.pop('admin_target_id')
            
            target_user = await asyncio.to_thread(get_user, target_user_id)
            if not target_user:
                await update.effective_message.reply_text("❌ Target user no longer exists.")
                return
            
            t_id = target_user['user_id']
            t_name = target_user['username'] or target_user['first_name'] or str(t_id)
            
            try:
                parts = update.message.text.strip().split()
                if len(parts) < 2:
                    raise ValueError
                num = parts[0]
                v_id = parts[1]
                provider = parts[2].lower() if len(parts) > 2 else 'tv'
                
                if provider not in ['tv', 'pva']:
                    await update.effective_message.reply_text("❌ Provider must be 'tv' or 'pva'.")
                    return

                # Fetch details to verify and get expiry
                expiry = None
                status = 'active'
                try:
                    if provider == 'tv':
                        details = await asyncio.to_thread(textverified.reservations.details, v_id)
                        status = details.state.value
                        if hasattr(details, 'billing_cycle_id') and details.billing_cycle_id:
                            cycle = await asyncio.to_thread(textverified.billing_cycles.get, details.billing_cycle_id)
                            expiry = cycle.billing_cycle_ends_at.isoformat()
                    else:
                        res = await asyncio.to_thread(pva_client.get_ltr_details, v_id)
                        if res and res.get('success'):
                            data = res.get('data', {})
                            status = data.get('status', 'active')
                            expiry = data.get('expiryDate') or data.get('expiresAt') or data.get('endTime')
                except Exception as e:
                    logging.warning(f"Manual sync failed: {e}")
                
                if not expiry:
                    expiry = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)).isoformat()
                
                await asyncio.to_thread(add_number_record, t_id, num, v_id, expires_at=expiry, status=status, provider=provider)
                await update.effective_message.reply_text(
                    f"✅ Successfully linked number `+{num}` ({provider.upper()}) to `{t_name}`.\n"
                    f"Status: `{status}`\nExpiry: `{expiry[:10]}`",
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.effective_message.reply_text("❌ Format error. Use: `NUMBER VERIF_ID [tv/pva]`")
            return

        # Flow A: Admin typed a target (username/ID) to start an action
        context.user_data.pop('admin_action')
        target_input = update.message.text.strip()
        target_user = await asyncio.to_thread(resolve_user, target_input)
        
        if not target_user:
            await update.effective_message.reply_text("❌ User not found. Use /admin to try again.")
            return

        t_id = target_user['user_id']
        t_name = target_user['username'] or target_user['first_name'] or str(t_id)

        if action == 'view':
            await update.effective_message.reply_text(
                f"👤 *User Profile*\n\n{format_user_profile(target_user)}",
                parse_mode='Markdown'
            )
        
        elif action == 'numbers':
            numbers = await asyncio.to_thread(get_user_numbers, t_id)
            if not numbers:
                await update.effective_message.reply_text(f"User @{t_name} has no active rented numbers.")
                return
            lines = [f"📱 *Numbers for @{t_name}:*\n"]
            for number in numbers:
                lines.append(f"• `+{number['number']}` — status: {number['status']}")
            await update.effective_message.reply_text("\n".join(lines), parse_mode='Markdown')

        elif action == 'addnumber':
            context.user_data['admin_target_id'] = t_id
            
            keyboard = [
                [InlineKeyboardButton("Premium (TextVerified)", callback_data=f"admin_select_prov_tv_{t_id}"),
                 InlineKeyboardButton("Basic (PVADeals)", callback_data=f"admin_select_prov_pva_{t_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.effective_message.reply_text(
                f"➕ *Step 1: Select Provider for @{t_name}*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        elif action == 'removenum':
            numbers = await asyncio.to_thread(get_user_numbers, t_id)
            if not numbers:
                await update.effective_message.reply_text(f"User @{t_name} has no active rented numbers.")
                return
            
            keyboard = []
            for number in numbers:
                keyboard.append([InlineKeyboardButton(f"❌ Remove +{number['number']}", callback_data=f"admin_do_remove_{number['id']}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(f"📱 *Select Number to Remove for @{t_name}:*", reply_markup=reply_markup, parse_mode='Markdown')

        elif action in ['credit', 'debit']:
            amounts = [5, 10, 25, 50, 100]
            keyboard = []
            row = []
            for amt in amounts:
                row.append(InlineKeyboardButton(f"${amt}", callback_data=f"admin_{action}_{t_id}_{amt}"))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row: keyboard.append(row)
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(
                f"💰 *{action.capitalize()} User: @{t_name}*\n\nSelect the amount to {action}:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        return

    # Normal user message handling
    await update.effective_message.reply_text("I didn't understand that. Use the menu or /help to see available commands.")

