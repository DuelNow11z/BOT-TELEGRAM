import telebot
from telebot import types
import sqlite3
from datetime import datetime
import pagamentos 
import config 
import base64

# Inicialização do bot com o token do arquivo de configuração
bot = telebot.TeleBot(config.API_TOKEN)

DB_NAME = 'dashboard.db'

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_or_register_user(user: types.User):
    """Verifica se um usuário existe no banco de dados e o registra se não existir."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user.id,))
    db_user = cursor.fetchone()

    if db_user is None:
        data_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO users (id, username, first_name, last_name, data_registro) VALUES (?, ?, ?, ?, ?)",
                       (user.id, user.username, user.first_name, user.last_name, data_registro))
        conn.commit()
    
    conn.close()


# --- COMANDOS INICIAIS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_or_register_user(message.from_user) # Garante que o usuário está registrado
    
    markup = types.InlineKeyboardMarkup()
    btn_produtos = types.InlineKeyboardButton("🛍️ Ver Produtos", callback_data='ver_produtos')
    markup.add(btn_produtos)
    bot.reply_to(message, f"Olá, {message.from_user.first_name}! Bem-vindo(a) ao nosso bot de vendas. ✨", reply_markup=markup)

# --- CALLBACK HANDLERS (LÓGICA CORRIGIDA) ---

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    # Garante que o usuário que clicou no botão seja registrado
    get_or_register_user(call.from_user)
    
    if call.data == 'ver_produtos':
        mostrar_produtos(call.message.chat.id)
    elif call.data.startswith('comprar_'):
        produto_id = int(call.data.split('_')[1])
        # Passa o objeto 'call' inteiro para ter acesso ao usuário correto
        gerar_cobranca(call, produto_id)

def mostrar_produtos(chat_id):
    conn = get_db_connection()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    conn.close()

    if not produtos:
        bot.send_message(chat_id, "Nenhum produto disponível no momento. �")
        return

    for produto in produtos:
        markup = types.InlineKeyboardMarkup()
        btn_comprar = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_{produto['id']}")
        markup.add(btn_comprar)
        bot.send_message(chat_id, f"💎 *{produto['nome']}*\n\nPreço: R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca(call: types.CallbackQuery, produto_id: int):
    # Pega o ID do usuário que CLICOU no botão, não do autor da mensagem original
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    conn = get_db_connection()
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,)).fetchone()

    if not produto:
        bot.send_message(chat_id, "Produto não encontrado.")
        conn.close()
        return
        
    data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor = conn.cursor()
    # Insere a venda com o ID do usuário correto
    cursor.execute(
        "INSERT INTO vendas (user_id, produto_id, status, data_venda) VALUES (?, ?, ?, ?)",
        (user_id, produto_id, 'pendente', data_venda)
    )
    conn.commit()
    venda_id = cursor.lastrowid 
    
    pagamento = pagamentos.criar_pagamento_pix(
        valor=produto['preco'],
        descricao=produto['nome'],
        email=f"user_{user_id}@email.com", 
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
        bot.send_message(chat_id, "Desculpe, ocorreu um erro ao gerar o PIX. Tente novamente mais tarde ou contate o suporte.")
        print(f"[ERRO] Falha ao gerar PIX. Resposta do MP: {pagamento}")


print("Bot em execução...")
bot.polling()
