import os
import json
import requests
import telebot
from telebot import types
import base64
import pagamentos
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, time
import psycopg2 # Nova importação para PostgreSQL
import psycopg2.extras
import urllib.parse as up

# --- CONFIGURAÇÃO INICIAL ---
API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL')
DATABASE_URL = os.getenv('DATABASE_URL') # URL do banco de dados da Render

bot = telebot.TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_padrao_muito_segura')

# --- CONEXÃO E INICIALIZAÇÃO DO BANCO DE DADOS POSTGRESQL ---

def get_db_connection():
    """Conecta ao banco de dados PostgreSQL usando a DATABASE_URL."""
    up.uses_netloc.append("postgres")
    url = up.urlparse(DATABASE_URL)
    try:
        conn = psycopg2.connect(database=url.path[1:],
                                user=url.username,
                                password=url.password,
                                host=url.hostname,
                                port=url.port)
        return conn
    except psycopg2.OperationalError as e:
        print(f"Erro ao conectar ao PostgreSQL: {e}")
        return None

def init_db():
    """Cria as tabelas do banco de dados se elas não existirem."""
    conn = get_db_connection()
    if conn is None:
        print("Não foi possível inicializar o banco de dados: conexão falhou.")
        return
        
    cur = conn.cursor()
    # Usamos TEXT para datas para manter a compatibilidade com o código existente
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            data_registro TEXT
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            preco NUMERIC(10, 2) NOT NULL,
            link TEXT NOT NULL
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            produto_id INTEGER,
            preco NUMERIC(10, 2), 
            payment_id TEXT,
            status TEXT,
            data_venda TEXT,
            payer_name TEXT,
            payer_email TEXT
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()
    print("Tabelas do banco de dados verificadas/criadas.")

# --- FUNÇÕES AUXILIARES ADAPTADAS ---

def get_or_register_user(user: types.User):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (user.id,))
    db_user = cur.fetchone()
    if db_user is None:
        data_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur.execute("INSERT INTO users (id, username, first_name, last_name, data_registro) VALUES (%s, %s, %s, %s, %s)",
                       (user.id, user.username, user.first_name, user.last_name, data_registro))
        conn.commit()
    cur.close()
    conn.close()

def enviar_produto_telegram(user_id, nome_produto, link_produto):
    url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
    texto = (f"🎉 Pagamento Aprovado!\n\nObrigado por comprar *{nome_produto}*.\n\nAqui está o seu link de acesso:\n{link_produto}")
    payload = { 'chat_id': user_id, 'text': texto, 'parse_mode': 'Markdown' }
    try:
        requests.post(url, json=payload)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem de entrega: {e}")

# --- ROTAS FLASK E WEBHOOKS ADAPTADAS ---

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

    venda_id = payment_info.get('external_reference')
    if not venda_id: return jsonify({'status': 'ignored'}), 200

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM vendas WHERE id = %s AND status = %s', (venda_id, 'pendente'))
    venda = cur.fetchone()

    if venda:
        payer_info = payment_info.get('payer', {})
        payer_name = f"{payer_info.get('first_name', '')} {payer_info.get('last_name', '')}".strip()
        payer_email = payer_info.get('email')
        cur.execute('UPDATE vendas SET status = %s, payment_id = %s, payer_name = %s, payer_email = %s WHERE id = %s',
                     ('aprovado', payment_id, payer_name, payer_email, venda_id))
        conn.commit()
        cur.execute('SELECT * FROM produtos WHERE id = %s', (venda['produto_id'],))
        produto = cur.fetchone()
        if produto:
            enviar_produto_telegram(venda['user_id'], produto['nome'], produto['link'])
    cur.close()
    conn.close()
    return jsonify({'status': 'success'}), 200

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
            flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cur.execute('SELECT COUNT(id) FROM users')
    total_usuarios = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(id) FROM produtos')
    total_produtos = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(id), SUM(preco) FROM vendas WHERE status = %s", ('aprovado',))
    vendas_data = cur.fetchone()
    total_vendas_aprovadas = vendas_data[0] or 0
    receita_total = vendas_data[1] or 0.0

    cur.execute("""
        SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, 
               CASE 
                   WHEN v.status = 'aprovado' THEN 'aprovado'
                   WHEN v.status = 'pendente' AND (NOW() - INTERVAL '1 hour') > TO_TIMESTAMP(v.data_venda, 'YYYY-MM-DD HH24:MI:SS') THEN 'expirado'
                   ELSE v.status 
               END AS status
        FROM vendas v
        JOIN users u ON v.user_id = u.id
        JOIN produtos p ON v.produto_id = p.id
        ORDER BY v.id DESC LIMIT 5
    """)
    vendas_recentes = cur.fetchall()
    
    chart_labels, chart_data = [], []
    today = datetime.now()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        start_of_day_str = datetime.combine(day, time.min).strftime('%Y-%m-%d %H:%M:%S')
        end_of_day_str = datetime.combine(day, time.max).strftime('%Y-%m-%d %H:%M:%S')
        chart_labels.append(day.strftime('%d/%m'))
        cur.execute("SELECT SUM(preco) FROM vendas WHERE status = 'aprovado' AND data_venda BETWEEN %s AND %s", (start_of_day_str, end_of_day_str))
        daily_revenue = cur.fetchone()[0]
        chart_data.append(float(daily_revenue or 0.0))
        
    cur.close()
    conn.close()
    
    return render_template('index.html', total_vendas=total_vendas_aprovadas, total_usuarios=total_usuarios, total_produtos=total_produtos, receita_total=float(receita_total), vendas_recentes=vendas_recentes, chart_labels=json.dumps(chart_labels), chart_data=json.dumps(chart_data))

@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if not session.get('logged_in'): return redirect(url_for('login'))
    if request.method == 'POST':
        nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
        cur.execute('INSERT INTO produtos (nome, preco, link) VALUES (%s, %s, %s)', (nome, preco, link))
        conn.commit()
        flash('Produto adicionado com sucesso!', 'success')
        cur.close()
        conn.close()
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
        cur.close()
        conn.close()
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
    cur.execute('DELETE FROM produtos WHERE id = %s', (id,))
    conn.commit()
    flash('Produto removido com sucesso!', 'danger')
    cur.close()
    conn.close()
    return redirect(url_for('produtos'))

@app.route('/vendas')
def vendas():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT id, nome FROM produtos ORDER BY nome')
    produtos_disponiveis = cur.fetchall()
    
    query = """
        SELECT T.* FROM (
            SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, p.id as produto_id,
                   CASE 
                       WHEN v.status = 'aprovado' THEN 'aprovado'
                       WHEN v.status = 'pendente' AND (NOW() - INTERVAL '1 hour') > TO_TIMESTAMP(v.data_venda, 'YYYY-MM-DD HH24:MI:SS') THEN 'expirado'
                       ELSE v.status 
                   END AS status
            FROM vendas v
            JOIN users u ON v.user_id = u.id
            JOIN produtos p ON v.produto_id = p.id
        ) AS T
    """
    conditions, params = [], []
    args = request.args
    if args.get('data_inicio'): conditions.append("T.data_venda >= %s"); params.append(args.get('data_inicio'))
    if args.get('data_fim'): conditions.append("T.data_venda <= %s"); params.append(args.get('data_fim') + ' 23:59:59')
    if args.get('pesquisa'): conditions.append("(T.username LIKE %s OR T.nome LIKE %s OR T.first_name LIKE %s)"); params.extend(['%' + args.get('pesquisa') + '%'] * 3)
    if args.get('produto_id'): conditions.append("T.produto_id = %s"); params.append(args.get('produto_id'))
    if args.get('status'): conditions.append("T.status = %s"); params.append(args.get('status'))

    if conditions: query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY T.id DESC"
    
    cur.execute(query, tuple(params))
    lista_vendas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('vendas.html', vendas=lista_vendas, produtos_disponiveis=produtos_disponiveis)

@app.route('/venda_detalhes/<int:id>')
def venda_detalhes(id):
    if not session.get('logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM vendas WHERE id = %s', (id,))
    venda = cur.fetchone()
    cur.close()
    conn.close()
    if venda: return jsonify(dict(venda))
    return jsonify({'error': 'Not Found'}), 404

@app.route('/usuarios')
def usuarios():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM users ORDER BY id DESC')
    lista_usuarios = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('usuarios.html', usuarios=lista_usuarios)

@app.route('/remove_user/<int:id>')
def remove_user(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM users WHERE id = %s', (id,))
    conn.commit()
    flash('Usuário removido com sucesso!', 'danger')
    cur.close()
    conn.close()
    return redirect(url_for('usuarios'))

# --- BOT HANDLERS ADAPTADOS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_or_register_user(message.from_user)
    markup = types.InlineKeyboardMarkup()
    btn_produtos = types.InlineKeyboardButton("🛍️ Ver Produtos", callback_data='ver_produtos')
    markup.add(btn_produtos)
    bot.reply_to(message, f"Olá, {message.from_user.first_name}! Bem-vindo(a).", reply_markup=markup)

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
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM produtos')
    produtos = cur.fetchall()
    cur.close()
    conn.close()
    if not produtos:
        bot.send_message(chat_id, "Nenhum produto disponível.")
        return
    for produto in produtos:
        markup = types.InlineKeyboardMarkup()
        btn_comprar = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_{produto['id']}")
        markup.add(btn_comprar)
        bot.send_message(chat_id, f"💎 *{produto['nome']}*\n\nPreço: R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca(call: types.CallbackQuery, produto_id: int):
    user_id, chat_id = call.from_user.id, call.message.chat.id
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM produtos WHERE id = %s', (produto_id,))
    produto = cur.fetchone()
    if not produto:
        bot.send_message(chat_id, "Produto não encontrado.")
    else:
        data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                       (user_id, produto_id, produto['preco'], 'pendente', data_venda))
        venda_id = cur.fetchone()[0]
        conn.commit()
        pagamento = pagamentos.criar_pagamento_pix(produto=produto, user=call.from_user, venda_id=venda_id)
        if pagamento and 'point_of_interaction' in pagamento:
            qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
            qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
            qr_code_image = base64.b64decode(qr_code_base64)
            bot.send_photo(chat_id, qr_code_image, caption=f"✅ PIX gerado para *{produto['nome']}*!")
            bot.send_message(chat_id, f"```{qr_code_data}```", parse_mode='Markdown')
            bot.send_message(chat_id, "Você receberá o produto aqui assim que o pagamento for confirmado.")
        else:
            bot.send_message(chat_id, "Ocorreu um erro ao gerar o PIX. Tente novamente.")
            print(f"[ERRO] Falha ao gerar PIX. Resposta do MP: {pagamento}")
    cur.close()
    conn.close()

# --- INICIALIZAÇÃO FINAL ---
if __name__ != '__main__':
    # Esta parte só é executada quando rodando na Render (produção)
    init_db() # Cria as tabelas na primeira vez
    try:
        if API_TOKEN and BASE_URL:
            bot.set_webhook(url=f"{BASE_URL}/{API_TOKEN}")
            print("Webhook do Telegram configurado com sucesso!")
        else:
            print("ERRO: Variáveis de ambiente não definidas.")
    except Exception as e:
        print(f"Erro ao configurar o webhook do Telegram: {e}")
