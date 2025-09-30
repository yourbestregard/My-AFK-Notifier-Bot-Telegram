import logging
from datetime import datetime, timezone
import html
import json
import os

# Library utama untuk bot
from telegram import Update, MessageEntity
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# GANTI DENGAN TOKEN BOT ANDA
TOKEN = "8133130086:AAEXJs4uPsHjaLInaNxlRRu8I3Ek28voA38"
# NAMA FILE UNTUK MENYIMPAN DATA AFK
DATA_FILE = "afk_data.json"

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# "Database" sementara yang akan dimuat dari file saat startup
afk_users = {}

# --- FUNGSI BARU UNTUK MENYIMPAN DAN MEMUAT DATA ---

def save_data():
    """Menyimpan data afk_users ke file JSON."""
    # Kita perlu mengonversi objek datetime ke string agar bisa disimpan di JSON
    data_to_save = {}
    for user_id, info in afk_users.items():
        data_to_save[user_id] = {
            "reason": info["reason"],
            "since": info["since"].isoformat(),  # Konversi ke string format ISO
            "name": info["name"]
        }
    
    with open(DATA_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=4)
    logger.info("Data AFK berhasil disimpan.")

def load_data():
    """Memuat data afk_users dari file JSON saat bot dimulai."""
    global afk_users
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data_from_file = json.load(f)
                # Konversi kembali string 'since' ke objek datetime
                for user_id, info in data_from_file.items():
                    afk_users[int(user_id)] = {
                        "reason": info["reason"],
                        "since": datetime.fromisoformat(info["since"]), # Konversi kembali
                        "name": info["name"]
                    }
                logger.info("Data AFK berhasil dimuat dari file.")
            except json.JSONDecodeError:
                logger.warning("File data kosong atau rusak, memulai dengan data kosong.")
                afk_users = {}
    else:
        logger.info("File data tidak ditemukan, memulai dengan data kosong.")

# --- FUNGSI UTILITAS (TIDAK BERUBAH) ---

def format_duration(seconds):
    """Fungsi untuk mengubah detik menjadi format yang mudah dibaca."""
    if seconds < 60:
        return f"{int(seconds)} detik"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} menit"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} jam"
    else:
        days = int(seconds / 86400)
        return f"{days} hari"

# --- FUNGSI COMMAND HANDLER (DENGAN PENAMBAHAN save_data()) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Halo! Saya adalah AFK Bot (versi persistensi).\n"
        "Gunakan /afk [alasan] untuk mengatur status AFK.\n"
        "Gunakan /back untuk kembali online."
    )

async def set_afk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "Tidak ada alasan"
    
    afk_users[user.id] = {
        "reason": reason,
        "since": datetime.now(timezone.utc),
        "name": user.first_name
    }
    
    save_data() # Simpan data setiap kali ada yang set AFK
    await update.message.reply_text(f"{user.first_name} sekarang AFK. Alasan: {reason}")

async def unset_afk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    
    if user.id in afk_users:
        start_time = afk_users[user.id]["since"]
        duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        duration_str = format_duration(duration_seconds)
        
        del afk_users[user.id]
        save_data() # Simpan data setiap kali ada yang kembali
        
        await update.message.reply_text(f"Selamat datang kembali, {user.first_name}! Kamu telah AFK selama {duration_str}.")
    else:
        await update.message.reply_text("Kamu memang tidak sedang AFK.")

# --- FUNGSI PENGECEKAN AFK (DENGAN LOGIKA NOTIFIKASI BERULANG) ---

async def check_afk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    sender_id = update.effective_user.id
    
    # Kumpulkan semua ID pengguna yang AFK yang disebut dalam pesan ini
    # untuk menghindari spam notifikasi untuk orang yang sama dalam satu pesan.
    notified_ids = set()

    # Fungsi helper untuk mengirim notifikasi
    async def send_afk_notification(user_id):
        if user_id in notified_ids: # Jika sudah dinotifikasi di pesan ini, lewati
            return
            
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

    # 1. Cek jika pesan adalah sebuah REPLY
    if message.reply_to_message:
        replied_user_id = message.reply_to_message.from_user.id
        if replied_user_id in afk_users and replied_user_id != sender_id:
            await send_afk_notification(replied_user_id)
            # Perhatikan: Tidak ada 'return' di sini, pengecekan lanjut ke mention

    # 2. Cek jika pesan mengandung MENTION
    if message.entities:
        for entity in message.entities:
            # Hanya cek text_mention yang secara eksplisit menunjuk ke seorang user
            if entity.type == MessageEntity.TEXT_MENTION:
                mentioned_user_id = entity.user.id
                if mentioned_user_id in afk_users and mentioned_user_id != sender_id:
                    await send_afk_notification(mentioned_user_id)

def main() -> None:
    """Fungsi utama untuk menjalankan bot."""
    # --- PENTING: MUAT DATA SAAT BOT DIMULAI ---
    load_data()
    
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("afk", set_afk))
    application.add_handler(CommandHandler("back", unset_afk))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_afk))

    print("Bot sedang berjalan...")
    application.run_polling()

if __name__ == "__main__":
    main()
