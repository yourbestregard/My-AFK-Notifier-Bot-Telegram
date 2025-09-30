import logging
from datetime import datetime, timezone
import html
import json
import os

from telegram import Update, MessageEntity
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = ""
DATA_FILE = "afk_data.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Kita akan menggunakan dua dictionary untuk menyimpan data
afk_users = {}
username_to_id = {}

# Fungsi penyimpanan data

def save_data():
    """Menyimpan data afk_users dan username_to_id ke file JSON."""
    data_to_save = {
        "afk_users": {},
        "username_to_id": username_to_id # Langsung simpan peta username
    }
    for user_id, info in afk_users.items():
        data_to_save["afk_users"][user_id] = {
            "reason": info["reason"],
            "since": info["since"].isoformat(),
            "name": info["name"]
        }
    with open(DATA_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=4)
    logger.info("Data AFK berhasil disimpan.")

def load_data():
    """Memuat data afk_users dan username_to_id dari file JSON."""
    global afk_users, username_to_id
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data_from_file = json.load(f)
                
                # Muat data username_to_id
                username_to_id = data_from_file.get("username_to_id", {})
                
                # Muat data afk_users
                afk_users_raw = data_from_file.get("afk_users", {})
                for user_id, info in afk_users_raw.items():
                    afk_users[int(user_id)] = {
                        "reason": info["reason"],
                        "since": datetime.fromisoformat(info["since"]),
                        "name": info["name"]
                    }
                logger.info("Data AFK berhasil dimuat dari file.")
            except json.JSONDecodeError:
                logger.warning("File data kosong atau rusak, memulai dengan data kosong.")
    else:
        logger.info("File data tidak ditemukan, memulai dengan data kosong.")

# Fungsi utilitas

def format_duration(seconds):
    if seconds < 60: return f"{int(seconds)} detik"
    if seconds < 3600: return f"{int(seconds / 60)} menit"
    if seconds < 86400: return f"{int(seconds / 3600)} jam"
    return f"{int(seconds / 86400)} hari"

# Fungsi command handler

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Halo! Saya adalah AFK Notifier Bot.\n\n"
        "• `/afk [alasan]` - Mengatur status AFK.\n"
        "• `/back` - Kembali online.\n"
        "• `/help` - Menampilkan pesan ini."
    )

async def set_afk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "Tidak ada alasan"
    
    afk_users[user.id] = {
        "reason": reason,
        "since": datetime.now(timezone.utc),
        "name": user.first_name
    }
    
    if user.username:
        username_to_id[user.username.lower()] = user.id
    
    save_data()
    await update.message.reply_text(f"{user.first_name} sekarang AFK. Alasan: {reason}")

async def unset_afk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id in afk_users:
        start_time = afk_users[user.id]["since"]
        duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        duration_str = format_duration(duration_seconds)
        
        del afk_users[user.id]
        
        if user.username and user.username.lower() in username_to_id:
            del username_to_id[user.username.lower()]
            
        save_data()
        await update.message.reply_text(f"Selamat datang kembali, {user.first_name}! Kamu telah AFK selama {duration_str}.")
    else:
        await update.message.reply_text("Kamu memang tidak sedang AFK.")

# Fungsi pengecekan afk

async def check_afk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    sender_id = update.effective_user.id
    notified_ids = set()

    async def send_afk_notification(user_id):
        if user_id in notified_ids: return
        afk_info = afk_users[user_id]
        start_time = afk_info["since"]
        duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        duration_str = format_duration(duration_seconds)
        await message.reply_text(
            f"Pengguna **{html.escape(afk_info['name'])}** sedang AFK.\n"
            f"**Alasan:** {html.escape(afk_info['reason'])}\n"
            f"**Sejak:** {duration_str} yang lalu.",
            parse_mode='Markdown'
        )
        notified_ids.add(user_id)

    # Cek reply
    if message.reply_to_message:
        replied_user_id = message.reply_to_message.from_user.id
        if replied_user_id in afk_users and replied_user_id != sender_id:
            await send_afk_notification(replied_user_id)

    # Cek semua jenis mention di dalam pesan
    if message.entities:
        for entity in message.entities:
            user_id_to_check = None
            
            # Cek mention kontak
            if entity.type == MessageEntity.TEXT_MENTION:
                user_id_to_check = entity.user.id
            
            # Cek mention
            elif entity.type == MessageEntity.MENTION:
                # Ekstrak username dari teks pesan
                username_mentioned = message.text[entity.offset:entity.offset + entity.length]
                # Hapus '@' dan ubah ke huruf kecil
                cleaned_username = username_mentioned.lstrip('@').lower()
                # Cari user_id dari peta yang sudah kita buat
                user_id_to_check = username_to_id.get(cleaned_username)
            
            if user_id_to_check and user_id_to_check in afk_users and user_id_to_check != sender_id:
                await send_afk_notification(user_id_to_check)

def main() -> None:
    load_data()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("afk", set_afk))
    application.add_handler(CommandHandler("back", unset_afk))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_afk))
    print("Bot sedang berjalan...")
    application.run_polling()

if __name__ == "__main__":
    main()