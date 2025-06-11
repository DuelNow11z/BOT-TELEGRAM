import telebot
from telebot import types
import sqlite3
from datetime import datetime
import pagamentos 
import config 
import base64

bot = telebot.TeleBot(config.API_TOKEN)
DB_NAME = 'dashboard.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_or_register_user(user: types.User):
    conn = get_db_connection()
    db_user = conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()
    if db_user is None:
        data_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("INSERT INTO users (id, username, first_name, last_name, data_registro) VALUES (?, ?, ?, ?, ?)",
                       (user.id, user.username, user.first_name, user.last_name, data_registro))
        conn.commit()
    conn.close()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_or_register_user(message.from_user)
    markup = types.InlineKeyboardMarkup()
    btn_produtos = types.InlineKeyboardButton("🛍️ Ver Produtos", callback_data='ver_produtos')
    markup.add(btn_produtos)
    bot.reply_to(message, f"Olá, {message.from_user.first_name}! Bem-vindo(a) ao nosso bot de vendas. ✨", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    get_or_register_user(call.from_user)
    if call.data == 'ver_produtos':
        mostrar_produtos(call.message.chat.id)
    elif call.data.startswith('comprar_'):
        produto_id = int(call.data.split('_')[1])
        gerar_cobranca(call, produto_id)

def mostrar_produtos(chat_id):
    conn = get_db_connection()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    conn.close()
    if not produtos:
        bot.send_message(chat_id, "Nenhum produto disponível no momento. 🙁")
        return
    for produto in produtos:
        markup = types.InlineKeyboardMarkup()
        btn_comprar = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_{produto['id']}")
        markup.add(btn_comprar)
        bot.send_message(chat_id, f"💎 *{produto['nome']}*\n\nPreço: R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca(call: types.CallbackQuery, produto_id: int):
    user_id, chat_id = call.from_user.id, call.message.chat.id
    conn = get_db_connection()
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,)).fetchone()
    if not produto:
        bot.send_message(chat_id, "Produto não encontrado.")
        conn.close()
        return
        
    data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?)",
        (user_id, produto_id, produto['preco'], 'pendente', data_venda)
    )
    conn.commit()
    venda_id = cursor.lastrowid 
    
    pagamento = pagamentos.criar_pagamento_pix(
        produto=produto,
        user=call.from_user,
        venda_id=venda_id 
    )
    conn.close()
    
    if pagamento and 'point_of_interaction' in pagamento:
        qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
        qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
        qr_code_image = base64.b64decode(qr_code_base64)
        bot.send_photo(chat_id, qr_code_image, caption=f"✅ PIX gerado para *{produto['nome']}*!\n\nEscaneie o QR Code ou use o código abaixo:")
        bot.send_message(chat_id, f"```{qr_code_data}```", parse_mode='Markdown')
        bot.send_message(chat_id, "Assim que o pagamento for confirmado, você receberá o produto automaticamente aqui. 😊")
    else:
        # --- MODIFICAÇÃO PARA DEPURAÇÃO ---
        # Agora, vamos imprimir a resposta completa do Mercado Pago no console
        bot.send_message(chat_id, "Desculpe, ocorreu um erro ao gerar o PIX. Tente novamente mais tarde ou contate o suporte.")
        print("[ERRO] Falha ao gerar PIX. Resposta do Mercado Pago:")
        print(pagamento) # Imprime o objeto de resposta completo

print("Bot em execução...")
bot.polling()
