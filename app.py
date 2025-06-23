import os
import json
import requests
import telebot
from telebot import types
import base64
import pagamentos
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras
import urllib.parse as up

# --- CONFIGURAÇÃO ---
API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL')
DATABASE_URL = os.getenv('DATABASE_URL')
GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')

bot = telebot.TeleBot(API_TOKEN) if API_TOKEN else None
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_super_secreta_e_longa')

# --- LÓGICA DO BANCO DE DADOS (POSTGRESQL) ---
def get_db_connection():
    up.uses_netloc.append("postgres")
    url = up.urlparse(DATABASE_URL)
    return psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS vendas, assinaturas, produtos, passes, users, admin, configuracoes CASCADE;")
    cur.execute('''CREATE TABLE IF NOT EXISTS users (id BIGINT PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, data_registro TEXT);''')
    cur.execute('''CREATE TABLE IF NOT EXISTS produtos (id SERIAL PRIMARY KEY, nome TEXT NOT NULL, preco NUMERIC(10, 2) NOT NULL, link TEXT NOT NULL);''')
    cur.execute('''CREATE TABLE IF NOT EXISTS vendas (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, produto_id INTEGER NOT NULL, preco NUMERIC(10, 2), payment_id TEXT, status TEXT, data_venda TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY(produto_id) REFERENCES produtos(id) ON DELETE CASCADE);''')
    cur.execute('''CREATE TABLE IF NOT EXISTS passes (id SERIAL PRIMARY KEY, nome TEXT NOT NULL, preco NUMERIC(10, 2) NOT NULL, duracao_dias INTEGER NOT NULL);''')
    cur.execute('''CREATE TABLE IF NOT EXISTS assinaturas (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, pass_id INTEGER NOT NULL, payment_id TEXT, data_inicio TIMESTAMP, data_expiracao TIMESTAMP, status TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY(pass_id) REFERENCES passes(id) ON DELETE CASCADE);''')
    cur.execute('''CREATE TABLE IF NOT EXISTS admin (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);''')
    cur.execute('''CREATE TABLE IF NOT EXISTS configuracoes (id INTEGER PRIMARY KEY CHECK (id = 1), gateway_provider TEXT DEFAULT 'mercadopago', mercadopago_token TEXT);''')
    cur.execute("INSERT INTO configuracoes (id) VALUES (1) ON CONFLICT (id) DO NOTHING;")
    conn.commit()
    cur.close()
    conn.close()
    print("Tabelas do banco de dados (re)criadas com sucesso.")

def get_or_register_user(user: types.User):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id = %s", (user.id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users (id, username, first_name, last_name, data_registro) VALUES (%s, %s, %s, %s, %s)",
                       (user.id, user.username, user.first_name, user.last_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    cur.close()
    conn.close()

def get_payment_config():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM configuracoes WHERE id = 1")
    config = cur.fetchone()
    cur.close()
    conn.close()
    return config

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
    if not (notification and notification.get('type') == 'payment'): return jsonify({'status': 'ignored'}), 200
    
    config = get_payment_config()
    if not config or not config['mercadopago_token']:
        print("[WEBHOOK-ERRO] Credenciais do Mercado Pago não configuradas.")
        return jsonify({'status': 'config_error'}), 500

    payment_id = notification['data']['id']
    payment_info = pagamentos.verificar_status_pagamento(payment_id, config['mercadopago_token'])
    if not (payment_info and payment_info['status'] == 'approved'): return jsonify({'status': 'not_approved'}), 200
    
    external_reference = payment_info.get('external_reference')
    if not external_reference: return jsonify({'status': 'ignored'}), 200

    if external_reference.startswith('venda_'):
        venda_id = int(external_reference.split('_')[1])
        processar_venda_produto(payment_id, venda_id)
    elif external_reference.startswith('assinatura_'):
        assinatura_id = int(external_reference.split('_')[1])
        processar_assinatura_passe(payment_id, assinatura_id)
    
    return jsonify({'status': 'success'}), 200

def processar_venda_produto(payment_id, venda_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM vendas WHERE id = %s AND status = %s', (venda_id, 'pendente'))
    venda = cur.fetchone()
    if venda:
        # A API do MP pode enviar notificações com atraso, então a verificação de expiração não é ideal aqui.
        # Confiaremos que o webhook só é chamado para pagamentos válidos.
        cur.execute('UPDATE vendas SET status = %s, payment_id = %s WHERE id = %s', ('aprovado', payment_id, venda_id))
        conn.commit()
        cur.execute('SELECT * FROM produtos WHERE id = %s', (venda['produto_id'],))
        produto = cur.fetchone()
        if produto:
            bot.send_message(venda['user_id'], f"✅ Pagamento aprovado!\n\nAqui está o seu link para *{produto['nome']}*:\n{produto['link']}", parse_mode='Markdown')
    cur.close()
    conn.close()

def processar_assinatura_passe(payment_id, assinatura_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM assinaturas WHERE id = %s AND status = %s', (assinatura_id, 'pendente'))
    assinatura = cur.fetchone()
    if assinatura:
        cur.execute('SELECT * FROM passes WHERE id = %s', (assinatura['pass_id'],))
        passe = cur.fetchone()
        
        data_inicio = datetime.now()
        data_expiracao = data_inicio + timedelta(days=passe['duracao_dias'])
        
        cur.execute('UPDATE assinaturas SET status = %s, payment_id = %s, data_inicio = %s, data_expiracao = %s WHERE id = %s',
                     ('ativo', payment_id, data_inicio, data_expiracao, assinatura_id))
        conn.commit()
        try:
            expire_date_ts = int(data_expiracao.timestamp())
            link = bot.create_chat_invite_link(chat_id=int(GROUP_CHAT_ID), expire_date=expire_date_ts, member_limit=1).invite_link
            bot.send_message(assinatura['user_id'], f"✅ Pagamento aprovado! O seu acesso ao grupo VIP é válido até {data_expiracao.strftime('%d/%m/%Y')}.\n\nUse este link de convite único para entrar:\n{link}")
        except Exception as e:
            print(f"Erro ao criar link de convite: {e}")
            bot.send_message(assinatura['user_id'], "Pagamento aprovado! Ocorreu um erro ao gerar o seu link de convite. Por favor, contacte o suporte.")
    cur.close()
    conn.close()

# --- ROTAS DO PAINEL ---
@app.route('/setup-admin-e-db')
def setup_admin_and_db():
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    username, password = "admin", "123"
    hashed_password = generate_password_hash(password)
    cur.execute("INSERT INTO admin (username, password_hash) VALUES (%s, %s)", (username, hashed_password))
    conn.commit()
    cur.close()
    conn.close()
    return f"Base de dados reiniciada e utilizador '{username}' criado com a senha '{password}'. Remova esta rota do seu código agora.", 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM admin WHERE username = %s', (username,))
        admin_user = cur.fetchone()
        cur.close()
        conn.close()
        if admin_user and check_password_hash(admin_user['password_hash'], password):
            session['logged_in'], session['username'] = True, admin_user['username']
            return redirect(url_for('index'))
        else:
            flash('Utilizador ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sessão terminada com sucesso.', 'info')
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(id) FROM vendas WHERE status = 'aprovado'")
    total_vendas = cur.fetchone()[0]
    cur.execute("SELECT COUNT(id) FROM assinaturas WHERE status = 'ativo'")
    total_assinantes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(id) FROM produtos")
    total_produtos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(id) FROM passes")
    total_passes = cur.fetchone()[0]
    cur.close()
    conn.close()
    return render_template('index_hybrid.html', total_vendas=total_vendas, total_assinantes=total_assinantes, total_produtos=total_produtos, total_passes=total_passes)

@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
        cur.execute('INSERT INTO produtos (nome, preco, link) VALUES (%s, %s, %s)', (nome, preco, link))
        conn.commit()
        flash('Produto criado com sucesso!', 'success')
        return redirect(url_for('produtos'))
    cur.execute('SELECT * FROM produtos ORDER BY id DESC')
    lista_produtos = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('produtos.html', produtos=lista_produtos)

@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
        cur.execute('UPDATE produtos SET nome = %s, preco = %s, link = %s WHERE id = %s', (nome, preco, link, id))
        conn.commit()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('produtos'))
    cur.execute('SELECT * FROM produtos WHERE id = %s', (id,))
    produto = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('edit_product.html', produto=produto)

@app.route('/remove_product/<int:id>')
def remove_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM vendas WHERE produto_id = %s', (id,))
    cur.execute('DELETE FROM produtos WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Produto removido com sucesso!', 'danger')
    return redirect(url_for('produtos'))

@app.route('/vendas')
def vendas():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT v.*, u.first_name, u.username, p.nome as produto_nome FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id ORDER BY v.id DESC")
    lista_vendas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('vendas.html', vendas=lista_vendas)

@app.route('/passes', methods=['GET', 'POST'])
def passes():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        nome, preco, duracao = request.form['nome'], request.form['preco'], request.form['duracao_dias']
        cur.execute('INSERT INTO passes (nome, preco, duracao_dias) VALUES (%s, %s, %s)', (nome, preco, duracao))
        conn.commit()
        flash('Passe de acesso criado com sucesso!', 'success')
        return redirect(url_for('passes'))
    cur.execute('SELECT * FROM passes ORDER BY duracao_dias')
    lista_passes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('passes.html', passes=lista_passes)

@app.route('/remove_pass/<int:id>')
def remove_pass(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM assinaturas WHERE pass_id = %s', (id,))
    cur.execute('DELETE FROM passes WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Passe removido com sucesso!', 'danger')
    return redirect(url_for('passes'))

@app.route('/assinantes')
def assinantes():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT a.id, u.first_name, u.username, p.nome as passe_nome, a.data_expiracao,
               CASE
                   WHEN a.status = 'ativo' AND NOW() > a.data_expiracao THEN 'expirado'
                   ELSE a.status
               END as status
        FROM assinaturas a JOIN users u ON a.user_id = u.id JOIN passes p ON a.pass_id = p.id
        ORDER BY a.data_expiracao ASC
    """)
    lista_assinantes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('assinantes.html', assinantes=lista_assinantes)

@app.route('/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        token = request.form.get('mercadopago_token')
        if token:
            cur.execute("UPDATE configuracoes SET mercadopago_token = %s WHERE id = 1", (token,))
            conn.commit()
            flash('Configurações de pagamento guardadas com sucesso!', 'success')
        return redirect(url_for('configuracoes'))
    cur.execute("SELECT * FROM configuracoes WHERE id = 1")
    config_data = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('configuracoes.html', config=config_data)

# --- COMANDOS DO BOT ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_or_register_user(message.from_user)
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_produtos = types.InlineKeyboardButton("🛍️ Comprar Produtos", callback_data='ver_produtos')
    btn_passes = types.InlineKeyboardButton("🎟️ Obter Acesso VIP", callback_data='ver_passes')
    markup.add(btn_produtos, btn_passes)
    bot.reply_to(message, "Olá! Escolha uma opção para continuar:", reply_markup=markup)

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
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM produtos ORDER BY id DESC')
    produtos = cur.fetchall()
    cur.close()
    conn.close()
    if not produtos: bot.send_message(chat_id, "Nenhum produto digital disponível.")
    else:
        for produto in produtos:
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_produto_{produto['id']}")
            markup.add(btn)
            bot.send_message(chat_id, f"🛍️ *{produto['nome']}*\n*Preço:* R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca_produto(call: types.CallbackQuery, produto_id: int):
    config = get_payment_config()
    if not config or not config['mercadopago_token']:
        bot.send_message(call.message.chat.id, "⚠️ Erro: O administrador não configurou um método de pagamento.")
        return
    user, chat_id = call.from_user, call.message.chat.id
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM produtos WHERE id = %s', (produto_id,))
    produto = cur.fetchone()
    if produto:
        cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                       (user.id, produto_id, produto['preco'], 'pendente', datetime.now()))
        venda_id = cur.fetchone()[0]
        conn.commit()
        pagamento = pagamentos.criar_pagamento_pix(produto, user, f"venda_{venda_id}", config['mercadopago_token'])
        if pagamento and 'point_of_interaction' in pagamento:
            qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
            qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
            qr_code_image = base64.b64decode(qr_code_base64)
            bot.send_photo(chat_id, qr_code_image, caption=f"✅ PIX gerado para *{produto['nome']}*!")
            bot.send_message(chat_id, qr_code_data)
    cur.close()
    conn.close()

def mostrar_passes(chat_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM passes ORDER BY duracao_dias')
    passes = cur.fetchall()
    cur.close()
    conn.close()
    if not passes: bot.send_message(chat_id, "Nenhum passe de acesso disponível.")
    else:
        for passe in passes:
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton(f"Obter por R${passe['preco']:.2f}", callback_data=f"comprar_passe_{passe['id']}")
            markup.add(btn)
            bot.send_message(chat_id, f"🎟️ *{passe['nome']}*\n*Duração:* {passe['duracao_dias']} dias\n*Preço:* R${passe['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca_passe(call: types.CallbackQuery, pass_id: int):
    config = get_payment_config()
    if not config or not config['mercadopago_token']:
        bot.send_message(call.message.chat.id, "⚠️ Erro: O administrador não configurou um método de pagamento.")
        return
    user, chat_id = call.from_user, call.message.chat.id
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM passes WHERE id = %s', (pass_id,))
    passe = cur.fetchone()
    if passe:
        cur.execute("INSERT INTO assinaturas (user_id, pass_id, status, data_inicio, data_expiracao) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                       (user.id, pass_id, 'pendente', datetime.now(), datetime.now()))
        assinatura_id = cur.fetchone()[0]
        conn.commit()
        pagamento = pagamentos.criar_pagamento_pix(passe, user, f"assinatura_{assinatura_id}", config['mercadopago_token'])
        if pagamento and 'point_of_interaction' in pagamento:
            qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
            qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
            qr_code_image = base64.b64decode(qr_code_base64)
            bot.send_photo(chat_id, qr_code_image, caption=f"✅ PIX gerado para *{passe['nome']}*!")
            bot.send_message(chat_id, qr_code_data)
    cur.close()
    conn.close()

# --- INICIALIZAÇÃO FINAL ---
if os.getenv('IS_RENDER'):
    # Na Render, não chamamos init_db() automaticamente para não apagar os dados.
    # A inicialização é feita pela rota secreta.
    if bot and BASE_URL:
        bot.set_webhook(url=f"{BASE_URL}/{API_TOKEN}")
