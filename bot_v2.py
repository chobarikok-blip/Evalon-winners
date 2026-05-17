"""
Telegram Bulk Approve Bot v2.0
==============================
UPGRADE: Approve watu 5 kwa wakati mmoja kwa delay random
         Inaonekana natural kama binadamu!

MAHITAJI:
    pip install python-telegram-bot==20.7

SETUP:
    1. Pata token kutoka @BotFather
    2. Weka BOT_TOKEN na ADMIN_ID hapa chini
    3. Fanya bot kuwa Admin wa channel yako (permission: Invite Users)
    4. Washa "Approve New Members" kwenye channel settings
    5. Endesha: python bot_v2.py
"""

import logging
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =============================
# MIPANGILIO — BADILISHA HAPA
# =============================

BOT_TOKEN = "8714717705:AAFaVeyp1OQIbkM3C3wb7qT7OzuCsMR5KmA"
ADMIN_ID = 8054370971

# Watu wangapi kwa wakati mmoja (batch)
BATCH_SIZE = 5

# Sekunde za kusubiri kati ya kila batch (random kati ya hizi)
DELAY_MIN = 0.5  # sekunde
DELAY_MAX = 2.0  # sekunde

# =============================
# LOGGING
# =============================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================
# HIFADHI YA REQUESTS
# =============================
pending_requests: dict = {}

# Kuzuia approve mbili zisifanye kazi pamoja
is_approving = False


# =============================
# KUSANYA REQUESTS
# =============================
async def collect_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_request = update.chat_join_request
    user = join_request.from_user
    chat_id = join_request.chat.id

    pending_requests[user.id] = {
        "name": user.full_name,
        "username": f"@{user.username}" if user.username else "Hana username",
        "chat_id": chat_id,
    }

    logger.info(f"📥 Request mpya: {user.full_name} | Jumla: {len(pending_requests)}")

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📥 *Request mpya!*\n"
                f"👤 {user.full_name}\n"
                f"📊 Zinasubiri sasa: *{len(pending_requests)}*\n\n"
                f"Tuma /requests kuona zote."
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Imeshindwa notify admin: {e}")


# =============================
# AMRI: /start
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "👋 *Karibu kwenye Approve Bot v2.0!*\n\n"
        "📌 Amri zinazopatikana:\n"
        "• /requests — Ona requests zinazosubiri\n"
        "• /stats — Takwimu za sasa\n"
        "• /stop — Simamisha approve inayoendelea",
        parse_mode="Markdown"
    )


# =============================
# AMRI: /requests
# =============================
async def show_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    count = len(pending_requests)

    if count == 0:
        await update.message.reply_text("✅ Hakuna requests zinazosubiri sasa hivi.")
        return

    keyboard = [
        [
            InlineKeyboardButton(f"🚀 Approve All ({count})", callback_data="approve_all"),
            InlineKeyboardButton("👤 Approve Baadhi", callback_data="approve_select_page_0"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📋 *Requests zinazosubiri: {count}*\n\n"
        f"⚡ Approve All itafanya *watu 5 kwa wakati mmoja*\n"
        f"⏱ Muda: ~*{estimate_time(count)}*\n\n"
        f"Chagua hatua:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


def estimate_time(count):
    """Kadiria muda wa kukamilisha approve."""
    batches = count / BATCH_SIZE
    avg_delay = (DELAY_MIN + DELAY_MAX) / 2
    total_seconds = batches * avg_delay
    if total_seconds < 60:
        return f"sekunde {int(total_seconds)}"
    elif total_seconds < 3600:
        return f"dakika {int(total_seconds / 60)}"
    else:
        return f"saa {total_seconds / 3600:.1f}"


# =============================
# CALLBACK: Approve All — Batch ya 5
# =============================
async def approve_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_approving

    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    if is_approving:
        await query.answer("⚠️ Approve tayari inaendelea! Tuma /stop kwanza.", show_alert=True)
        return

    if not pending_requests:
        await query.edit_message_text("✅ Hakuna requests za ku-approve.")
        return

    is_approving = True
    total = len(pending_requests)
    success = 0
    failed = 0
    batch_num = 0

    # Piga ujumbe wa kuanza
    status_msg = await query.edit_message_text(
        f"🚀 *Inaanza approve...*\n"
        f"👥 Jumla: *{total}*\n"
        f"⚡ Batch: watu *{BATCH_SIZE}* kwa wakati\n"
        f"⏳ Tafadhali subiri...",
        parse_mode="Markdown"
    )

    to_approve = list(pending_requests.items())
    total_batches = (len(to_approve) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(to_approve), BATCH_SIZE):
        # Angalia kama imesimamishwa
        if not is_approving:
            break

        batch = to_approve[i:i + BATCH_SIZE]
        batch_num += 1

        # Approve kila mtu kwenye batch
        for user_id, info in batch:
            if user_id not in pending_requests:
                continue
            try:
                await context.bot.approve_chat_join_request(
                    chat_id=info["chat_id"],
                    user_id=user_id
                )
                del pending_requests[user_id]
                success += 1
            except Exception as e:
                logger.error(f"Imeshindwa: {info['name']}: {e}")
                failed += 1

        # Update progress kila batch 10
        if batch_num % 10 == 0 or batch_num == total_batches:
            try:
                percent = int((success + failed) / total * 100)
                bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
                await status_msg.edit_text(
                    f"⚡ *Inakubali...*\n\n"
                    f"[{bar}] {percent}%\n\n"
                    f"✅ Approved: *{success}*\n"
                    f"❌ Imeshindwa: *{failed}*\n"
                    f"⏳ Zilizobaki: *{len(pending_requests)}*\n\n"
                    f"Tuma /stop kusimamisha.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        # Delay random kati ya batches — inaonekana natural
        delay = random.uniform(DELAY_MIN, DELAY_MAX)
        await asyncio.sleep(delay)

    is_approving = False

    # Ripoti ya mwisho
    try:
        await status_msg.edit_text(
            f"🎉 *Imekamilika!*\n\n"
            f"✅ Waliopita: *{success}*\n"
            f"❌ Walishindwa: *{failed}*\n"
            f"📊 Zilizobaki: *{len(pending_requests)}*",
            parse_mode="Markdown"
        )
    except Exception:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🎉 Imekamilika!\n✅ {success} walipita\n❌ {failed} walishindwa",
            parse_mode="Markdown"
        )


# =============================
# AMRI: /stop — Simamisha approve
# =============================
async def stop_approving(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_approving

    if update.effective_user.id != ADMIN_ID:
        return

    if not is_approving:
        await update.message.reply_text("ℹ️ Hakuna approve inayoendelea sasa hivi.")
        return

    is_approving = False
    await update.message.reply_text(
        f"🛑 *Approve imesimamishwa!*\n"
        f"📊 Zilizobaki: *{len(pending_requests)}*",
        parse_mode="Markdown"
    )


# =============================
# CALLBACK: Approve Baadhi (mmoja mmoja)
# =============================
PAGE_SIZE = 5

async def show_select_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    page = int(query.data.split("_")[-1])
    users = list(pending_requests.items())
    total = len(users)

    if total == 0:
        await query.edit_message_text("✅ Hakuna requests zilizobaki.")
        return

    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total)
    page_users = users[start_idx:end_idx]

    keyboard = []
    for user_id, info in page_users:
        name = info["name"]
        username = info["username"]
        label = f"✅ {name} ({username})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"approve_one_{user_id}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Nyuma", callback_data=f"approve_select_page_{page - 1}"))
    if end_idx < total:
        nav_buttons.append(InlineKeyboardButton("Mbele ➡️", callback_data=f"approve_select_page_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 Rudi", callback_data="back_to_main")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"👤 *Chagua mtu wa ku-approve:*\n📊 {start_idx + 1}–{end_idx} kati ya {total}",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


# =============================
# CALLBACK: Approve mtu mmoja
# =============================
async def approve_one(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    user_id = int(query.data.split("_")[-1])

    if user_id not in pending_requests:
        await query.answer("⚠️ Mtu huyu hayupo tena kwenye orodha.", show_alert=True)
        return

    info = pending_requests[user_id]

    try:
        await context.bot.approve_chat_join_request(
            chat_id=info["chat_id"],
            user_id=user_id
        )
        del pending_requests[user_id]
        await query.answer(f"✅ {info['name']} amekubaliwa!", show_alert=False)
    except Exception as e:
        await query.answer(f"❌ Imeshindwa: {e}", show_alert=True)
        return

    query.data = "approve_select_page_0"
    await show_select_page(update, context)


# =============================
# CALLBACK: Rudi main menu
# =============================
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    count = len(pending_requests)
    keyboard = [
        [
            InlineKeyboardButton(f"🚀 Approve All ({count})", callback_data="approve_all"),
            InlineKeyboardButton("👤 Approve Baadhi", callback_data="approve_select_page_0"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📋 *Requests zinazosubiri: {count}*\n\nChagua hatua:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


# =============================
# AMRI: /stats
# =============================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    count = len(pending_requests)
    status = "🟢 Inafanya kazi" if is_approving else "🔴 Imesimama"

    await update.message.reply_text(
        f"📊 *Takwimu:*\n\n"
        f"⏳ Zinasubiri: *{count}*\n"
        f"⚙️ Hali: {status}\n"
        f"⚡ Batch size: *{BATCH_SIZE}* kwa wakati\n"
        f"⏱ Delay: *{DELAY_MIN}-{DELAY_MAX}s* (random)",
        parse_mode="Markdown"
    )


# =============================
# MAIN
# =============================
def main():
    print("🤖 Approve Bot v2.0 inaanza...")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"⚡ Batch size: {BATCH_SIZE} kwa wakati")
    print(f"⏱ Delay: {DELAY_MIN}-{DELAY_MAX} sekunde (random)")
    print("📢 Inangoja join requests...\n")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(ChatJoinRequestHandler(collect_request))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("requests", show_requests))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("stop", stop_approving))
    app.add_handler(CallbackQueryHandler(approve_all, pattern="^approve_all$"))
    app.add_handler(CallbackQueryHandler(show_select_page, pattern="^approve_select_page_"))
    app.add_handler(CallbackQueryHandler(approve_one, pattern="^approve_one_"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))

    app.run_polling(allowed_updates=["chat_join_request", "message", "callback_query"])


if __name__ == "__main__":
    main()
