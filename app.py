import os
import json
import requests
import telebot
from telebot import types
import base64
import pagamentos # Usamos o pagamentos.py simples para PIX
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import sqlite3 # Usado para o ambiente local


# --- CONFIGURAÇÃO ---
# Tenta importar as chaves do config.py para testes locais.
# Se falhar (como na Render), usa as variáveis de ambiente.
IS_LOCAL = True
try:
    import config
    API_TOKEN = config.API_TOKEN
    MERCADOPAGO_ACCESS_TOKEN = config.MERCADOPAGO_ACCESS_TOKEN
    BASE_URL = config.BASE_URL
    GROUP_CHAT_ID = config.GROUP_CHAT_ID
    DB_NAME = 'bot_hybrid.db'
except ImportError:
    IS_LOCAL = False
    API_TOKEN = os.getenv('API_TOKEN')
    MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    BASE_URL = os.getenv('BASE_URL')
    GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')
    # Na Render, o banco de dados pode estar num caminho persistente
    DB_NAME = os.path.join('/var/data/sqlite', 'bot_hybrid.db') if os.path.exists('/var/data/sqlite') else 'bot_hybrid.db'


bot = telebot.TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_padrao_muito_segura')

# --- LÓGICA DO BANCO DE DADOS ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, data_registro TEXT);''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS produtos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, preco REAL NOT NULL, link TEXT NOT NULL);''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, produto_id INTEGER NOT NULL, preco REAL, payment_id TEXT, status TEXT, data_venda TEXT, payer_name TEXT, payer_email TEXT, FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(produto_id) REFERENCES produtos(id));''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS passes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, preco REAL NOT NULL, duracao_dias INTEGER NOT NULL);''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS assinaturas (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, pass_id INTEGER NOT NULL, payment_id TEXT, data_inicio TEXT, data_expiracao TEXT, status TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(pass_id) REFERENCES passes(id));''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);''')
    conn.commit()
    conn.close()
    print("Tabelas do banco de dados verificadas/criadas.")

def get_or_register_user(user: types.User):
    conn = get_db_connection()
    db_user = conn.execute("SELECT id FROM users WHERE id = ?", (user.id,)).fetchone()
    if db_user is None:
        conn.execute("INSERT INTO users (id, username, first_name, last_name, data_registro) VALUES (?, ?, ?, ?, ?)",
                       (user.id, user.username, user.first_name, user.last_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    conn.close()

# --- WEBHOOKS ---
@app.route(f"/{API_TOKEN}", methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '!', 200
    return "Unsupported Media Type", 415

@app.route('/webhook/mercado-pago', methods=['POST'])
def webhook_mercado_pago():
    notification = request.json
    if not (notification and notification.get('type') == 'payment'):
        return jsonify({'status': 'ignored'}), 200

    payment_id = notification['data']['id']
    payment_info = pagamentos.verificar_status_pagamento(payment_id)
    if not (payment_info and payment_info['status'] == 'approved'):
        return jsonify({'status': 'not_approved'}), 200

    external_reference = payment_info.get('external_reference')
    if not external_reference: return jsonify({'status': 'ignored'}), 200

    if external_reference.startswith('venda_'):
        venda_id = int(external_reference.split('_')[1])
        processar_venda_produto(payment_id, venda_id)
    elif external_reference.startswith('assinatura_'):
        assinatura_id = int(external_reference.split('_')[1])
        processar_assinatura_passe(payment_id, assinatura_id, payment_info)
    
    return jsonify({'status': 'success'}), 200

def processar_venda_produto(payment_id, venda_id):
    conn = get_db_connection()
    venda = conn.execute('SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente')).fetchone()
    if venda:
        data_venda_dt = datetime.strptime(venda['data_venda'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() > data_venda_dt + timedelta(hours=1):
            conn.execute('UPDATE vendas SET status = ? WHERE id = ?', ('expirado', venda_id))
            conn.commit()
        else:
            conn.execute('UPDATE vendas SET status = ?, payment_id = ? WHERE id = ?', ('aprovado', payment_id, venda_id))
            conn.commit()
            produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (venda['produto_id'],)).fetchone()
            if produto:
                bot.send_message(venda['user_id'], f"✅ Pagamento aprovado!\n\nAqui está o seu link para *{produto['nome']}*:\n{produto['link']}", parse_mode='Markdown')
    conn.close()

def processar_assinatura_passe(payment_id, assinatura_id, payment_info):
    conn = get_db_connection()
    assinatura = conn.execute('SELECT * FROM assinaturas WHERE id = ? AND status = ?', (assinatura_id, 'pendente')).fetchone()
    if assinatura:
        passe = conn.execute('SELECT * FROM passes WHERE id = ?', (assinatura['pass_id'],)).fetchone()
        
        data_inicio = datetime.now()
        data_expiracao = data_inicio + timedelta(days=passe['duracao_dias'])
        
        conn.execute('UPDATE assinaturas SET status = ?, payment_id = ?, data_inicio = ?, data_expiracao = ? WHERE id = ?',
                     ('ativo', payment_id, data_inicio.strftime('%Y-%m-%d %H:%M:%S'), data_expiracao.strftime('%Y-%m-%d %H:%M:%S'), assinatura_id))
        conn.commit()

        try:
            expire_date_ts = int(data_expiracao.timestamp())
            link = bot.create_chat_invite_link(chat_id=int(GROUP_CHAT_ID), expire_date=expire_date_ts, member_limit=1).invite_link
            bot.send_message(assinatura['user_id'], f"✅ Pagamento aprovado! O seu acesso ao grupo VIP é válido até {data_expiracao.strftime('%d/%m/%Y')}.\n\nUse este link de convite único para entrar:\n{link}")
        except Exception as e:
            print(f"Erro ao criar link de convite: {e}")
            bot.send_message(assinatura['user_id'], "Pagamento aprovado! Ocorreu um erro ao gerar o seu link de convite. Por favor, contacte o suporte.")
    
    conn.close()

# --- ROTAS DO PAINEL ---
@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    # Lógica do dashboard para o modelo híbrido
    return "Dashboard Híbrido em construção. Use as abas para gerir o seu negócio."

# ... (outras rotas do painel)

# --- COMANDOS DO BOT ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_or_register_user(message.from_user)
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_produtos = types.InlineKeyboardButton("🛍️ Comprar Produtos Digitais", callback_data='ver_produtos')
    btn_passes = types.InlineKeyboardButton("🎟️ Aceder ao Grupo VIP", callback_data='ver_passes')
    markup.add(btn_produtos, btn_passes)
    bot.reply_to(message, "Olá! O que deseja fazer?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    get_or_register_user(call.from_user)
    if call.data == 'ver_produtos':
        mostrar_produtos(call.message.chat.id)
    elif call.data.startswith('comprar_produto_'):
        produto_id = int(call.data.split('_')[2])
        gerar_cobranca_produto(call, produto_id)
    elif call.data == 'ver_passes':
        mostrar_passes(call.message.chat.id)
    elif call.data.startswith('comprar_passe_'):
        pass_id = int(call.data.split('_')[2])
        gerar_cobranca_passe(call, pass_id)

def mostrar_produtos(chat_id):
    conn = get_db_connection()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    conn.close()
    if not produtos:
        bot.send_message(chat_id, "Nenhum produto digital disponível de momento.")
        return
    for produto in produtos:
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_produto_{produto['id']}")
        markup.add(btn)
        bot.send_message(chat_id, f"🛍️ *{produto['nome']}*\n*Preço:* R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca_produto(call: types.CallbackQuery, produto_id: int):
    user_id, chat_id = call.from_user.id, call.message.chat.id
    conn = get_db_connection()
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,)).fetchone()
    if produto:
        data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?)",
                       (user_id, produto_id, produto['preco'], 'pendente', data_venda))
        venda_id = cursor.lastrowid
        conn.commit()
        # A referência externa agora indica que é uma venda
        pagamento = pagamentos.criar_pagamento_pix(produto, call.from_user, f"venda_{venda_id}")
        if pagamento and 'point_of_interaction' in pagamento:
            # Enviar QR Code e PIX
            pass # Código omitido por brevidade
    conn.close()

def mostrar_passes(chat_id):
    conn = get_db_connection()
    passes = conn.execute('SELECT * FROM passes ORDER BY duracao_dias ASC').fetchall()
    conn.close()
    if not passes:
        bot.send_message(chat_id, "Nenhum passe de acesso disponível de momento.")
        return
    for passe in passes:
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton(f"Obter por R${passe['preco']:.2f}", callback_data=f"comprar_passe_{passe['id']}")
        markup.add(btn)
        bot.send_message(chat_id, f"🎟️ *{passe['nome']}*\n*Duração:* {passe['duracao_dias']} dias\n*Preço:* R${passe['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca_passe(call: types.CallbackQuery, pass_id: int):
    user, chat_id = call.from_user, call.message.chat.id
    conn = get_db_connection()
    passe = conn.execute('SELECT * FROM passes WHERE id = ?', (pass_id,)).fetchone()
    if passe:
        data_inicio = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO assinaturas (user_id, pass_id, data_inicio, status) VALUES (?, ?, ?, ?)",
                       (user.id, pass_id, data_inicio, 'pendente'))
        assinatura_id = cursor.lastrowid
        conn.commit()
        # A referência externa agora indica que é uma assinatura
        pagamento = pagamentos.criar_pagamento_pix(passe, user, f"assinatura_{assinatura_id}")
        if pagamento and 'point_of_interaction' in pagamento:
            qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
            qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
            qr_code_image = base64.b64decode(qr_code_base64)
            bot.send_photo(chat_id, qr_code_image, caption=f"✅ PIX gerado para *{passe['nome']}*!")
            bot.send_message(chat_id, qr_code_data)
    conn.close()


# --- INICIALIZAÇÃO FINAL ---
if not IS_LOCAL:
    # Só executa na Render
    init_db()
    if API_TOKEN and BASE_URL:
        bot.set_webhook(url=f"{BASE_URL}/{API_TOKEN}")
else:
    # Só para testes locais
    init_db()
