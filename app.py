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
import sqlite3 # Usaremos sqlite para a versão local

# --- CONFIGURAÇÃO ---
DB_NAME = 'bot_hybrid.db' # O nome do nosso novo ficheiro de base de dados

# Para testes locais, as chaves virão do config.py. Em produção (Render), viriam do ambiente.
try:
    import config
    API_TOKEN = config.API_TOKEN
    MERCADOPAGO_ACCESS_TOKEN = config.MERCADOPAGO_ACCESS_TOKEN
    BASE_URL = config.BASE_URL
    GROUP_CHAT_ID = config.GROUP_CHAT_ID
except ImportError:
    API_TOKEN = os.getenv('API_TOKEN')
    MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    BASE_URL = os.getenv('BASE_URL')
    GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')

bot = telebot.TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_padrao_muito_segura')

# --- LÓGICA DO BANCO DE DADOS ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

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

    # --- LÓGICA HÍBRIDA ---
    # Verifica se é uma venda de produto ou uma assinatura de passe
    if external_reference.startswith('venda_'):
        venda_id = int(external_reference.split('_')[1])
        processar_venda_produto(payment_id, venda_id)
    elif external_reference.startswith('assinatura_'):
        assinatura_id = int(external_reference.split('_')[1])
        processar_assinatura_passe(payment_id, assinatura_id)
    
    return jsonify({'status': 'success'}), 200

def processar_venda_produto(payment_id, venda_id):
    conn = get_db_connection()
    venda = conn.execute('SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente')).fetchone()
    if venda:
        # Lógica para não entregar produto se o pagamento for de uma venda expirada
        data_venda_dt = datetime.strptime(venda['data_venda'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() > data_venda_dt + timedelta(hours=1):
            conn.execute('UPDATE vendas SET status = ? WHERE id = ?', ('expirado', venda_id))
            conn.commit()
            print(f"Pagamento recebido para venda de produto expirada (ID: {venda_id}).")
        else:
            conn.execute('UPDATE vendas SET status = ?, payment_id = ? WHERE id = ?', ('aprovado', payment_id, venda_id))
            conn.commit()
            produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (venda['produto_id'],)).fetchone()
            if produto:
                bot.send_message(venda['user_id'], f"✅ Pagamento aprovado!\n\nAqui está o seu link para *{produto['nome']}*:\n{produto['link']}", parse_mode='Markdown')
    conn.close()

def processar_assinatura_passe(payment_id, assinatura_id):
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
            link = bot.create_chat_invite_link(chat_id=GROUP_CHAT_ID, expire_date=expire_date_ts, member_limit=1).invite_link
            bot.send_message(assinatura['user_id'], f"✅ Pagamento aprovado! O seu acesso ao grupo VIP é válido até {data_expiracao.strftime('%d/%m/%Y')}.\n\nUse este link de convite único para entrar:\n{link}")
        except Exception as e:
            print(f"Erro ao criar link de convite: {e}")
            bot.send_message(assinatura['user_id'], "Pagamento aprovado! Ocorreu um erro ao gerar o seu link de convite. Por favor, contacte o suporte.")
    
    conn.close()

# --- ROTAS DO PAINEL ---
# ... (Rotas de login, logout, etc.)

@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    # A lógica do dashboard agora mostrará dados de ambos os modelos
    return "Dashboard Híbrido em construção."


# --- ROTAS PARA PRODUTOS E VENDAS ---
@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    # A lógica existente para gerir produtos continua aqui
    pass

@app.route('/vendas')
def vendas():
    # A lógica existente para ver vendas de produtos continua aqui
    pass


# --- NOVAS ROTAS PARA PASSES E ASSINANTES ---
@app.route('/passes', methods=['GET', 'POST'])
def passes():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form['nome']
        preco = request.form['preco']
        duracao_dias = request.form['duracao_dias']
        conn.execute('INSERT INTO passes (nome, preco, duracao_dias) VALUES (?, ?, ?)', (nome, preco, duracao_dias))
        conn.commit()
        flash('Passe de acesso criado com sucesso!', 'success')
        conn.close()
        return redirect(url_for('passes'))
    
    lista_passes = conn.execute('SELECT * FROM passes ORDER BY duracao_dias ASC').fetchall()
    conn.close()
    return render_template('passes.html', passes=lista_passes)

@app.route('/assinantes')
def assinantes():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    lista_assinantes = conn.execute("""
        SELECT a.id, u.first_name, u.username, p.nome as passe_nome, a.data_inicio, a.data_expiracao, a.status 
        FROM assinaturas a
        JOIN users u ON a.user_id = u.id
        JOIN passes p ON a.pass_id = p.id
        ORDER BY a.data_expiracao ASC
    """).fetchall()
    conn.close()
    return render_template('assinantes.html', assinantes=lista_assinantes)


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
    # Lógica para mostrar produtos
    pass

def gerar_cobranca_produto(call: types.CallbackQuery, produto_id: int):
    # Lógica para gerar cobrança de produto
    pass

def mostrar_passes(chat_id):
    # Lógica para mostrar passes
    pass

def gerar_cobranca_passe(call: types.CallbackQuery, pass_id: int):
    # Lógica para gerar cobrança de passe
    pass

# --- INICIALIZAÇÃO FINAL ---
if __name__ == '__main__':
    # Usado para testes locais
    app.run(host='0.0.0.0', port=5000, debug=True)
else:
    # Usado pela Render
    init_db() # Garante que as tabelas existem
    if API_TOKEN and BASE_URL:
        bot.set_webhook(url=f"{BASE_URL}/{API_TOKEN}")
