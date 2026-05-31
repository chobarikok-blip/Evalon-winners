"""
Telegram Bulk Approve Bot v4.0
==============================
Render Compatible - PTB 21.9 / Python 3.14
Approve 5 users at a time - naturally like a human!
PostgreSQL (Neon) powered - persistent storage.
"""

import logging
import asyncio
import random
import os
from datetime import datetime
from aiohttp import web

import psycopg2
import psycopg2.extras
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
DATABASE_URL = os.environ.get("DATABASE_URL", "")
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
# IN-MEMORY (synced with DB)
# =============================
pending_requests: dict = {}
is_approving = False


# =============================
# DATABASE
# =============================
def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pending_requests (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    username TEXT,
                    chat_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS approved_users (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    username TEXT,
                    chat_id BIGINT NOT NULL,
                    approved_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS approval_history (
                    id SERIAL PRIMARY KEY,
                    total_approved INT NOT NULL,
                    total_failed INT NOT NULL,
                    session_at TIMESTAMP DEFAULT NOW()
                );
            """)
        conn.commit()
    logger.info("Database tables ready.")


def load_pending_from_db():
    global pending_requests
    pending_requests = {}
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT user_id, name, username, chat_id FROM pending_requests;")
            for row in cur.fetchall():
                pending_requests[row["user_id"]] = {
                    "name": row["name"],
                    "username": row["username"],
                    "chat_id": row["chat_id"],
                }
    logger.info(f"Loaded {len(pending_requests)} pending requests from DB.")


def db_add_pending(user_id, name, username, chat_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pending_requests (user_id, name, username, chat_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET name=EXCLUDED.name, username=EXCLUDED.username, chat_id=EXCLUDED.chat_id;
            """, (user_id, name, username, chat_id))
        conn.commit()


def db_remove_pending(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending_requests WHERE user_id = %s;", (user_id,))
        conn.commit()


def db_add_approved(user_id, name, username, chat_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO approved_users (user_id, name, username, chat_id)
                VALUES (%s, %s, %s, %s);
            """, (user_id, name, username, chat_id))
        conn.commit()


def db_save_history(total_approved, total_failed):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO approval_history (total_approved, total_failed)
                VALUES (%s, %s);
            """, (total_approved, total_failed))
        conn.commit()


def db_get_stats():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM approved_users;")
            total_approved = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM approval_history;")
            total_sessions = cur.fetchone()[0]
            cur.execute("SELECT session_at FROM approval_history ORDER BY session_at DESC LIMIT 1;")
            last = cur.fetchone()
            last_session = last[0].strftime("%Y-%m-%d %H:%M") if last else "None"
    return total_approved, total_sessions, last_session


# =============================
# COLLECT REQUESTS
# =============================
async def collect_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_request = update.chat_join_request
    user = join_request.from_user
    chat_id = join_request.chat.id
    username = f"@{user.username}" if user.username else "No username"

    pending_requests[user.id] = {
        "name": user.full_name,
        "username": username,
        "chat_id": chat_id,
    }
    db_add_pending(user.id, user.full_name, username, chat_id)

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
        "• /history — Approval history\n"
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
# Approve All
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
                db_add_approved(user_id, info["name"], info["username"], info["chat_id"])
                db_remove_pending(user_id)
                del pending_requests[user_id]
                success += 1
            except Exception as e:
                logger.error(f"Failed: {info['name']}: {e}")
                failed += 1

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
    db_save_history(success, failed)

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
        db_add_approved(user_id, info["name"], info["username"], info["chat_id"])
        db_remove_pending(user_id)
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
    total_approved, total_sessions, last_session = db_get_stats()
    await update.message.reply_text(
        f"📊 *Statistics:*\n\n"
        f"⏳ Pending now: *{len(pending_requests)}*\n"
        f"✅ Total ever approved: *{total_approved}*\n"
        f"🔁 Total sessions: *{total_sessions}*\n"
        f"🕐 Last session: *{last_session}*\n"
        f"⚙️ Status: {status}\n"
        f"⚡ Batch: *{BATCH_SIZE}* at a time",
        parse_mode="Markdown"
    )


# =============================
# /history
# =============================
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT total_approved, total_failed, session_at
                FROM approval_history
                ORDER BY session_at DESC
                LIMIT 10;
            """)
            rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("📭 No approval history yet.")
        return

    lines = ["📜 *Last 10 Approval Sessions:*\n"]
    for row in rows:
        date = row["session_at"].strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"📅 {date}\n"
            f"  ✅ {row['total_approved']} approved | ❌ {row['total_failed']} failed"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# =============================
# WEB SERVER (keeps Render alive)
# =============================
async def health(request):
    return web.Response(text="Bot is running ✅")

async def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app = web.Application()
    web_app.router.add_get("/", health)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web server running on port {port}")

# =============================
# MAIN - asyncio.run() for Python 3.14
# =============================
async def main():
    print("🤖 Approve Bot v4.0 starting...")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"⚡ Batch: {BATCH_SIZE} | Delay: {DELAY_MIN}-{DELAY_MAX}s")

    init_db()
    load_pending_from_db()

    print(f"📦 Loaded {len(pending_requests)} pending requests from DB.")
    print("📢 Waiting for join requests...\n")


    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(ChatJoinRequestHandler(collect_request))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("requests", show_requests))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("stop", stop_approving))
    app.add_handler(CallbackQueryHandler(approve_all, pattern="^approve_all$"))
    app.add_handler(CallbackQueryHandler(show_select_page, pattern="^approve_select_page_"))
    app.add_handler(CallbackQueryHandler(approve_one, pattern="^approve_one_"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            allowed_updates=["chat_join_request", "message", "callback_query"],
            drop_pending_updates=True
        )
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
