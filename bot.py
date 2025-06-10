import telebot
from telebot import types
import sqlite3
from datetime import datetime
import pagamentos # Importa nosso módulo de pagamentos atualizado
import config # Importa as configurações

# Inicialização do bot com o token do arquivo de configuração
bot = telebot.TeleBot(config.API_TOKEN)

DB_NAME = 'dashboard.db'

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- COMANDOS INICIAIS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    data_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    if user is None:
        cursor.execute("INSERT INTO users (id, username, first_name, last_name, data_registro) VALUES (?, ?, ?, ?, ?)",
                       (user_id, username, first_name, last_name, data_registro))
        conn.commit()
    
    conn.close()

    markup = types.InlineKeyboardMarkup()
    btn_produtos = types.InlineKeyboardButton("🛍️ Ver Produtos", callback_data='ver_produtos')
    markup.add(btn_produtos)
    bot.reply_to(message, f"Olá, {first_name}! Bem-vindo(a) ao nosso bot de vendas. ✨", reply_markup=markup)

# --- CALLBACK HANDLERS ---

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == 'ver_produtos':
        mostrar_produtos(call.message)
    elif call.data.startswith('comprar_'):
        produto_id = int(call.data.split('_')[1])
        gerar_cobranca(call.message, produto_id)

def mostrar_produtos(message):
    conn = get_db_connection()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    conn.close()

    if not produtos:
        bot.send_message(message.chat.id, "Nenhum produto disponível no momento. 🙁")
        return

    for produto in produtos:
        markup = types.InlineKeyboardMarkup()
        btn_comprar = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_{produto['id']}")
        markup.add(btn_comprar)
        bot.send_message(message.chat.id, f"💎 *{produto['nome']}*\n\nPreço: R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca(message, produto_id):
    user_id = message.chat.id
    conn = get_db_connection()
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,)).fetchone()

    if not produto:
        bot.send_message(user_id, "Produto não encontrado.")
        conn.close()
        return
        
    # 1. Cria uma entrada na tabela de vendas com status 'pendente'
    data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO vendas (user_id, produto_id, status, data_venda) VALUES (?, ?, ?, ?)",
        (user_id, produto_id, 'pendente', data_venda)
    )
    conn.commit()
    venda_id = cursor.lastrowid # Pega o ID da venda que acabamos de criar
    
    # 2. Gera o pagamento no Mercado Pago usando o ID da venda como referência
    pagamento = pagamentos.criar_pagamento_pix(
        valor=produto['preco'],
        descricao=produto['nome'],
        email=f"user_{user_id}@email.com", # Pode ser um email genérico
        venda_id=venda_id 
    )
    conn.close()

    if pagamento:
        qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
        qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
        
        # Decodifica a imagem do QR Code
        import base64
        qr_code_image = base64.b64decode(qr_code_base64)

        # Envia a imagem do QR Code e o código PIX Copia e Cola
        bot.send_photo(user_id, qr_code_image, caption=f"✅ PIX gerado para *{produto['nome']}*!\n\nEscaneie o QR Code ou use o código abaixo:")
        bot.send_message(user_id, f"```{qr_code_data}```", parse_mode='Markdown')
        bot.send_message(user_id, "Assim que o pagamento for confirmado, você receberá o produto automaticamente aqui. 😊")
    else:
        bot.send_message(user_id, "Desculpe, ocorreu um erro ao gerar o PIX. Tente novamente mais tarde.")


print("Bot em execução...")
bot.polling()
