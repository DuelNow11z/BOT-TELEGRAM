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
import sqlite3

# --- CONFIGURAÇÃO ---
IS_LOCAL = True
try:
    import config
    API_TOKEN = config.API_TOKEN
    BASE_URL = config.BASE_URL
    GROUP_CHAT_ID = config.GROUP_CHAT_ID
    DB_NAME = 'bot_hybrid.db'
except ImportError:
    IS_LOCAL = False
    API_TOKEN = os.getenv('API_TOKEN')
    BASE_URL = os.getenv('BASE_URL')
    GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')
    DB_NAME = os.path.join('/var/data/sqlite', 'bot_hybrid.db') if os.path.exists('/var/data/sqlite') else 'bot_hybrid.db'

bot = telebot.TeleBot(API_TOKEN) if API_TOKEN else None
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
    cursor.execute('''CREATE TABLE IF NOT EXISTS vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, produto_id INTEGER NOT NULL, preco REAL, payment_id TEXT, status TEXT, data_venda TEXT);''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS passes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, preco REAL NOT NULL, duracao_dias INTEGER NOT NULL);''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS assinaturas (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, pass_id INTEGER NOT NULL, payment_id TEXT, data_inicio TEXT, data_expiracao TEXT, status TEXT NOT NULL);''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);''')
    conn.commit()
    conn.close()
    print("Tabelas do banco de dados verificadas/criadas.")

def get_or_register_user(user: types.User):
    conn = get_db_connection()
    if conn.execute("SELECT id FROM users WHERE id = ?", (user.id,)).fetchone() is None:
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
    # ... (código do webhook aqui, como na versão anterior)
    return jsonify({'status': 'success'})

# ... (outras funções de webhook aqui)

# --- ROTAS DO PAINEL ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        admin_user = conn.execute('SELECT * FROM admin WHERE username = ?', (username,)).fetchone()
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
    total_vendas = conn.execute("SELECT COUNT(id) FROM vendas WHERE status = 'aprovado'").fetchone()[0]
    total_assinantes = conn.execute("SELECT COUNT(id) FROM assinaturas WHERE status = 'ativo'").fetchone()[0]
    total_produtos = conn.execute("SELECT COUNT(id) FROM produtos").fetchone()[0]
    total_passes = conn.execute("SELECT COUNT(id) FROM passes").fetchone()[0]
    conn.close()
    return render_template('index_hybrid.html', total_vendas=total_vendas, total_assinantes=total_assinantes, total_produtos=total_produtos, total_passes=total_passes)

@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
        conn.execute('INSERT INTO produtos (nome, preco, link) VALUES (?, ?, ?)', (nome, preco, link))
        conn.commit()
        flash('Produto criado com sucesso!', 'success')
        conn.close()
        return redirect(url_for('produtos'))
    lista_produtos = conn.execute('SELECT * FROM produtos ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('produtos.html', produtos=lista_produtos)

@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
        conn.execute('UPDATE produtos SET nome = ?, preco = ?, link = ? WHERE id = ?', (nome, preco, link, id))
        conn.commit()
        flash('Produto atualizado com sucesso!', 'success')
        conn.close()
        return redirect(url_for('produtos'))
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('edit_product.html', produto=produto)

@app.route('/remove_product/<int:id>')
def remove_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM produtos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Produto removido com sucesso!', 'danger')
    return redirect(url_for('produtos'))

@app.route('/vendas')
def vendas():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    lista_vendas = conn.execute("SELECT v.*, u.first_name, u.username, p.nome as produto_nome FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id ORDER BY v.id DESC").fetchall()
    conn.close()
    return render_template('vendas.html', vendas=lista_vendas)

@app.route('/passes', methods=['GET', 'POST'])
def passes():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        nome, preco, duracao = request.form['nome'], request.form['preco'], request.form['duracao_dias']
        conn.execute('INSERT INTO passes (nome, preco, duracao_dias) VALUES (?, ?, ?)', (nome, preco, duracao))
        conn.commit()
        flash('Passe de acesso criado com sucesso!', 'success')
        return redirect(url_for('passes'))
    lista_passes = conn.execute('SELECT * FROM passes ORDER BY duracao_dias').fetchall()
    conn.close()
    return render_template('passes.html', passes=lista_passes)

@app.route('/assinantes')
def assinantes():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    lista_assinantes = conn.execute("""
        SELECT a.id, u.first_name, u.username, p.nome as passe_nome, a.data_expiracao,
               CASE
                   WHEN a.status = 'ativo' AND DATETIME('now', 'localtime') > DATETIME(a.data_expiracao) THEN 'expirado'
                   ELSE a.status
               END as status
        FROM assinaturas a JOIN users u ON a.user_id = u.id JOIN passes p ON a.pass_id = p.id
        ORDER BY a.data_expiracao ASC
    """).fetchall()
    conn.close()
    return render_template('assinantes.html', assinantes=lista_assinantes)


# --- COMANDOS DO BOT ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # ... (código do bot aqui)
    pass

# ... (outras funções do bot)

# --- INICIALIZAÇÃO FINAL ---
if not IS_LOCAL:
    init_db()
    if API_TOKEN and BASE_URL:
        bot.set_webhook(url=f"{BASE_URL}/{API_TOKEN}")
else:
    init_db()
