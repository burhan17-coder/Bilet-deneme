import os
import telebot
from telebot import types
import random
import sqlite3
import time
from flask import Flask, request, abort

TOKEN = os.environ['BOT_TOKEN']
bot = telebot.TeleBot(TOKEN)

# ADMIN ID'LERI - KENDİ USER ID'Nİ EKLE!
ADMIN_IDS = [123456789]  # <--- BURAYI DEĞİŞTİR!

app = Flask(__name__)

# Veritabanı (full_name eklendi)
def init_db():
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tickets
                 (user_id INTEGER, username TEXT, first_name TEXT, full_name TEXT, choice TEXT, 
                  ticket_number TEXT, amount INTEGER, timestamp REAL, approved INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# Kullanıcı durumları: adım adım ilerleme için
user_states = {}  # {user_id: {'step': 'name'/'amount', 'choice': 'A', 'full_name': 'Ahmet Yılmaz'}}

# START / MENU
@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("A", callback_data="choice_A"),
        types.InlineKeyboardButton("B", callback_data="choice_B"),
        types.InlineKeyboardButton("C", callback_data="choice_C"),
        types.InlineKeyboardButton("D", callback_data="choice_D")
    )

    bot.send_message(
        message.chat.id,
        "🎉 <b>BİLET SATIŞ BOTU</b>\n\n"
        "Lütfen almak istediğin seçeneği seç:\n\n"
        "<i>Her 250₺ = 1 bilet</i>",
        reply_markup=markup,
        parse_mode='HTML'
    )

# SEÇENEK SEÇİLDİ → İSİM SOR
@bot.callback_query_handler(func=lambda call: call.data.startswith('choice_'))
def handle_choice(call):
    choice = call.data.split('_')[1]
    user_id = call.from_user.id

    user_states[user_id] = {'step': 'name', 'choice': choice}

    bot.answer_callback_query(call.id, f"{choice} seçtin!")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✅ <b>{choice} seçeneği</b> seçildi!\n\n"
             "Lütfen <b>adınızı ve soyadınızı</b> yazın (örneğin: Ahmet Yılmaz)",
        parse_mode='HTML'
    )

# MESAJ GELDİ → ADIMLARA GÖRE İŞLE
@bot.message_handler(func=lambda m: m.from_user.id in user_states)
def handle_steps(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    step = state['step']

    if step == 'name':
        full_name = message.text.strip()
        if len(full_name) < 3 or ' ' not in full_name:
            bot.reply_to(message, "❌ Lütfen gerçek ad ve soyad yazın (örneğin: Mehmet Kaya)")
            return

        user_states[user_id]['full_name'] = full_name
        user_states[user_id]['step'] = 'amount'

        bot.reply_to(message, f"✅ Adınız kaydedildi: <b>{full_name}</b>\n\nŞimdi kaç TL'lik bilet alacaksın? (örneğin: 3000)", parse_mode='HTML')

    elif step == 'amount':
        try:
            amount = int(message.text.replace('₺', '').replace('.', '').replace(',', '').strip())
            if amount < 250:
                bot.reply_to(message, "❌ Minimum 250₺")
                return
        except:
            bot.reply_to(message, "❌ Sadece rakam yaz (örneğin: 3000)")
            return

        choice = state['choice']
        full_name = state['full_name']
        ticket_count = amount // 250

        # Benzersiz numaralar üret
        used = get_used_numbers()
        available = [f"{i:04d}" for i in range(1, 10000) if f"{i:04d}" not in used]
        
        if len(available) < ticket_count:
            bot.reply_to(message, "❌ Yeterli boş numara yok!")
            return

        tickets = random.sample(available, ticket_count)

        # Kaydet
        save_tickets(user_id, message.from_user.username or "", message.from_user.first_name, full_name, choice, tickets, amount, approved=0)

        ticket_list = "\n".join([f"🎟 <code>{t}</code>" for t in tickets])

        text = (
            f"🎉 <b>Biletlerin oluşturuldu!</b>\n\n"
            f"👤 Ad Soyad: <b>{full_name}</b>\n"
            f"📌 Seçenek: <b>{choice}</b>\n"
            f"💰 Tutar: <b>{amount}₺</b>\n"
            f"🎟 Bilet sayısı: <b>{ticket_count}</b>\n\n"
            f"<b>Numaralar:</b>\n{ticket_list}\n\n"
            f"⏳ Ödeme yaptıktan sonra admin onaylayacak!"
        )
        bot.send_message(message.chat.id, text, parse_mode='HTML')

        # Admine bildirim (isimle birlikte)
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, f"🔔 <b>Yeni bilet talebi!</b>\n"
                                          f"👤 Ad Soyad: {full_name}\n"
                                          f"👤 Telegram: {message.from_user.first_name} (@{message.from_user.username or 'yok'})\n"
                                          f"📌 Seçenek: {choice}\n"
                                          f"💰 Tutar: {amount}₺ ({ticket_count} bilet)\n"
                                          f"Komut: /onayla_{user_id}", parse_mode='HTML')
            except:
                pass

        # Durumu temizle
        del user_states[user_id]

# Diğer fonksiyonlar (onay, admin, çekiliş) aynı kalıyor, sadece get_user_by_ticket güncelleniyor

def get_user_by_ticket(ticket_number):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute("SELECT full_name, username FROM tickets WHERE ticket_number = ? LIMIT 1", (ticket_number,))
    row = c.fetchone()
    conn.close()
    if row:
        full_name = row[0] if row[0] else "Bilinmeyen"
        username = f"@{row[1]}" if row[1] else ""
        return {'first_name': full_name, 'username': row[1]}
    return {'first_name': 'Bilinmeyen', 'username': None}

# save_tickets fonksiyonuna full_name eklendi
def save_tickets(user_id, username, first_name, full_name, choice, tickets, amount, approved=0):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    ts = time.time()
    for t in tickets:
        c.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (user_id, username, first_name, full_name, choice, t, amount, ts, approved))
    conn.commit()
    conn.close()

# Diğer fonksiyonlar (approve, admin, cekilis, webhook vs.) aynı kalıyor
# (önceki mesajdaki kodun devamı)

# WEBHOOK kısmı aynı
@app.route('/bot', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return '', 200
    abort(403)

@app.route('/')
def home():
    return "Bilet Botu çalışıyor!"

bot.remove_webhook()
time.sleep(1)
webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/bot"
bot.set_webhook(url=webhook_url)
