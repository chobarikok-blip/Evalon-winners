"""
Telegram Bulk Approve Bot v4.0
==============================
Render Compatible - PTB 20.3
Approve 5 users at a time - naturally like a human!
"""

import logging
import asyncio
import random
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =============================
# CONFIGURATION
# =============================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
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
# STORAGE
# =============================
pending_requests: dict = {}
is_approving = False


# =============================
# COLLECT REQUESTS
# =============================
async def collect_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_request = update.chat_join_request
    user = join_request.from_user
    chat_id = join_request.chat.id

    pending_requests[user.id] = {
        "name": user.full_name,
        "username": f"@{user.username}" if user.username else "No username",
        "chat_id": chat_id,
    }

    logger.info(f"New request: {user.full_name} | Total: {len(pending_requests)}")

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📥 *New Request!*\n"
                f"👤 {user.full_name}\n"
                f"📊 Pending: *{len(pending_requests)}*\n\n"
                f"Send /requests to view all."
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Notification failed: {e}")


# =============================
# /start
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "👋 *Welcome to Approve Bot v4.0!*\n\n"
        "📌 Commands:\n"
        "• /requests — View requests\n"
        "• /stats — Statistics\n"
        "• /stop — Stop approving",
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
        await update.message.reply_text("✅ No pending requests.")
        return

    mins = int((count / BATCH_SIZE) * ((DELAY_MIN + DELAY_MAX) / 2) / 60)
    keyboard = [[
        InlineKeyboardButton(f"🚀 Approve All ({count})", callback_data="approve_all"),
        InlineKeyboardButton("👤 Approve Some", callback_data="approve_select_page_0"),
    ]]

    await update.message.reply_text(
        f"📋 *Requests: {count}*\n"
        f"⏱ Estimated time: ~*{mins}* minutes\n\n"
        f"Choose an action:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =============================
# Approve All - Batch of 5
# =============================
async def approve_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_approving
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    if is_approving:
        await query.answer("⚠️ Approval in progress! Send /stop first.", show_alert=True)
        return

    if not pending_requests:
        await query.edit_message_text("✅ No requests to approve.")
        return

    is_approving = True
    total = len(pending_requests)
    success = 0
    failed = 0

    status_msg = await query.edit_message_text(
        f"🚀 *Starting approval for {total} users...*\n"
        f"⚡ Batch: {BATCH_SIZE} at a time\n"
        f"⏳ Please wait...",
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
                logger.error(f"Failed: {info['name']}: {e}")
                failed += 1

        # Progress update every 10 batches
        if batch_num % 10 == 0 or batch_num == total_batches:
            try:
                done = success + failed
                percent = int(done / total * 100)
                bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
                await status_msg.edit_text(
                    f"⚡ *Approving...*\n\n"
                    f"[{bar}] {percent}%\n\n"
                    f"✅ Approved: *{success}*\n"
                    f"❌ Failed: *{failed}*\n"
                    f"⏳ Remaining: *{len(pending_requests)}*",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    is_approving = False

    try:
        await status_msg.edit_text(
            f"🎉 *Done!*\n\n"
            f"✅ Approved: *{success}*\n"
            f"❌ Failed: *{failed}*\n"
            f"📊 Remaining: *{len(pending_requests)}*",
            parse_mode="Markdown"
        )
    except Exception:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🎉 Done!\n✅ {success} approved\n❌ {failed} failed"
        )


# =============================
# /stop
# =============================
async def stop_approving(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_approving
    if update.effective_user.id != ADMIN_ID:
        return
    if not is_approving:
        await update.message.reply_text("ℹ️ No approval is currently running.")
        return
    is_approving = False
    await update.message.reply_text(
        f"🛑 *Stopped!*\n📊 Remaining: *{len(pending_requests)}*",
        parse_mode="Markdown"
    )


# =============================
# Approve Some
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
        await query.edit_message_text("✅ No requests remaining.")
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
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"approve_select_page_{page-1}"))
    if end_idx < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"approve_select_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")])

    await query.edit_message_text(
        f"👤 *Select a user:* {start_idx+1}–{end_idx} of {total}",
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
        await query.answer("⚠️ User is no longer in the list.", show_alert=True)
        return

    info = pending_requests[user_id]
    try:
        await context.bot.approve_chat_join_request(
            chat_id=info["chat_id"],
            user_id=user_id
        )
        del pending_requests[user_id]
        await query.answer(f"✅ {info['name']} has been approved!")
    except Exception as e:
        await query.answer(f"❌ Failed: {e}", show_alert=True)
        return

    query.data = "approve_select_page_0"
    await show_select_page(update, context)


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    count = len(pending_requests)
    keyboard = [[
        InlineKeyboardButton(f"🚀 Approve All ({count})", callback_data="approve_all"),
        InlineKeyboardButton("👤 Approve Some", callback_data="approve_select_page_0"),
    ]]

    await query.edit_message_text(
        f"📋 *Requests: {count}*\n\nChoose an action:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =============================
# /stats
# =============================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    status = "🟢 Running" if is_approving else "🔴 Stopped"
    await update.message.reply_text(
        f"📊 *Statistics:*\n\n"
        f"⏳ Pending: *{len(pending_requests)}*\n"
        f"⚙️ Status: {status}\n"
        f"⚡ Batch: *{BATCH_SIZE}* at a time",
        parse_mode="Markdown"
    )


# =============================
# MAIN
# =============================
def main():
    print("🤖 Approve Bot v4.0 starting...")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"⚡ Batch: {BATCH_SIZE} | Delay: {DELAY_MIN}-{DELAY_MAX}s")
    print("📢 Waiting for join requests...\n")

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

    app.run_polling(
        allowed_updates=["chat_join_request", "message", "callback_query"],
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
