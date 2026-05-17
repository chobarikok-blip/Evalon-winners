"""
Telegram Bulk Approve Bot v3.0
==============================
Compatible na Python 3.13 + python-telegram-bot 21.x
Approve watu 5 kwa wakati — natural kama binadamu!
"""

import logging
import asyncio
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ChatJoinRequestHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =============================
# MIPANGILIO
# =============================
BOT_TOKEN = "8714717705:AAFaVeyp1OQIbkM3C3wb7qT7OzuCsMR5KmA"
ADMIN_ID = 8054370971
BATCH_SIZE = 5
DELAY_MIN = 0.5
DELAY_MAX = 2.0

# =============================
# LOGGING
# =============================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================
# HIFADHI
# =============================
pending_requests: dict = {}
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

    logger.info(f"Request mpya: {user.full_name} | Jumla: {len(pending_requests)}")

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📥 *Request mpya!*\n"
                f"👤 {user.full_name}\n"
                f"📊 Zinasubiri: *{len(pending_requests)}*\n\n"
                f"Tuma /requests kuona zote."
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Notify imeshindwa: {e}")


# =============================
# /start
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "👋 *Karibu Approve Bot v3.0!*\n\n"
        "📌 Amri:\n"
        "• /requests — Ona requests\n"
        "• /stats — Takwimu\n"
        "• /stop — Simamisha approve",
        parse_mode="Markdown"
    )


# =============================
# /requests
# =============================
async def show_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    count = len(pending_requests)
    if count == 0:
        await update.message.reply_text("✅ Hakuna requests zinazosubiri.")
        return

    mins = int((count / BATCH_SIZE) * ((DELAY_MIN + DELAY_MAX) / 2) / 60)
    keyboard = [[
        InlineKeyboardButton(f"🚀 Approve All ({count})", callback_data="approve_all"),
        InlineKeyboardButton("👤 Approve Baadhi", callback_data="approve_select_page_0"),
    ]]

    await update.message.reply_text(
        f"📋 *Requests: {count}*\n"
        f"⏱ Muda wa kukamilisha: ~dakika *{mins}*\n\n"
        f"Chagua hatua:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =============================
# Approve All
# =============================
async def approve_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_approving
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    if is_approving:
        await query.answer("⚠️ Approve inaendelea! Tuma /stop kwanza.", show_alert=True)
        return

    if not pending_requests:
        await query.edit_message_text("✅ Hakuna requests za ku-approve.")
        return

    is_approving = True
    total = len(pending_requests)
    success = 0
    failed = 0

    status_msg = await query.edit_message_text(
        f"🚀 *Inaanza approve {total} watu...*\n"
        f"⚡ Batch: {BATCH_SIZE} kwa wakati\n"
        f"⏳ Subiri...",
        parse_mode="Markdown"
    )

    to_approve = list(pending_requests.items())
    total_batches = (len(to_approve) + BATCH_SIZE - 1) // BATCH_SIZE
    batch_num = 0

    for i in range(0, len(to_approve), BATCH_SIZE):
        if not is_approving:
            break

        batch = to_approve[i:i + BATCH_SIZE]
        batch_num += 1

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

        if batch_num % 10 == 0 or batch_num == total_batches:
            try:
                done = success + failed
                percent = int(done / total * 100)
                bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
                await status_msg.edit_text(
                    f"⚡ *Inakubali...*\n\n"
                    f"[{bar}] {percent}%\n\n"
                    f"✅ Approved: *{success}*\n"
                    f"❌ Imeshindwa: *{failed}*\n"
                    f"⏳ Zilizobaki: *{len(pending_requests)}*",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    is_approving = False

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
            text=f"🎉 Imekamilika!\n✅ {success} walipita\n❌ {failed} walishindwa"
        )


# =============================
# /stop
# =============================
async def stop_approving(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_approving
    if update.effective_user.id != ADMIN_ID:
        return
    if not is_approving:
        await update.message.reply_text("ℹ️ Hakuna approve inayoendelea.")
        return
    is_approving = False
    await update.message.reply_text(
        f"🛑 *Imesimamishwa!*\n📊 Zilizobaki: *{len(pending_requests)}*",
        parse_mode="Markdown"
    )


# =============================
# Approve Baadhi
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
        label = f"✅ {info['name']} ({info['username']})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"approve_one_{user_id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Nyuma", callback_data=f"approve_select_page_{page-1}"))
    if end_idx < total:
        nav.append(InlineKeyboardButton("Mbele ➡️", callback_data=f"approve_select_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Rudi", callback_data="back_to_main")])

    await query.edit_message_text(
        f"👤 *Chagua mtu:* {start_idx+1}–{end_idx} kati ya {total}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def approve_one(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    user_id = int(query.data.split("_")[-1])
    if user_id not in pending_requests:
        await query.answer("⚠️ Hayupo tena kwenye orodha.", show_alert=True)
        return

    info = pending_requests[user_id]
    try:
        await context.bot.approve_chat_join_request(
            chat_id=info["chat_id"],
            user_id=user_id
        )
        del pending_requests[user_id]
        await query.answer(f"✅ {info['name']} amekubaliwa!")
    except Exception as e:
        await query.answer(f"❌ Imeshindwa: {e}", show_alert=True)
        return

    query.data = "approve_select_page_0"
    await show_select_page(update, context)


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    count = len(pending_requests)
    keyboard = [[
        InlineKeyboardButton(f"🚀 Approve All ({count})", callback_data="approve_all"),
        InlineKeyboardButton("👤 Approve Baadhi", callback_data="approve_select_page_0"),
    ]]

    await query.edit_message_text(
        f"📋 *Requests: {count}*\n\nChagua hatua:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =============================
# /stats
# =============================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    status = "🟢 Inafanya kazi" if is_approving else "🔴 Imesimama"
    await update.message.reply_text(
        f"📊 *Takwimu:*\n\n"
        f"⏳ Zinasubiri: *{len(pending_requests)}*\n"
        f"⚙️ Hali: {status}\n"
        f"⚡ Batch: *{BATCH_SIZE}* kwa wakati",
        parse_mode="Markdown"
    )


# =============================
# MAIN
# =============================
def main():
    print("🤖 Approve Bot v3.0 inaanza...")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"⚡ Batch: {BATCH_SIZE} | Delay: {DELAY_MIN}-{DELAY_MAX}s")
    print("📢 Inangoja join requests...\n")

    app = Application.builder().token(BOT_TOKEN).build()

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
