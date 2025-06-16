import os
import json
import requests
import telebot
from telebot import types
import base64
import pagamentos_subscriptions # O novo módulo para pagamentos
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, time
import psycopg2 # Biblioteca para PostgreSQL
import psycopg2.extras
import urllib.parse as up

# --- CONFIGURAÇÃO INICIAL ---
API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL')
DATABASE_URL = os.getenv('DATABASE_URL') 

bot = telebot.TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_padrao_muito_segura')

# --- CONEXÃO E INICIALIZAÇÃO DO BANCO DE DADOS POSTGRESQL ---

def get_db_connection():
    """Conecta-se ao banco de dados PostgreSQL."""
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
    """Cria as tabelas do banco de dados se não existirem."""
    conn = get_db_connection()
    if conn is None:
        print("Não foi possível inicializar o banco de dados: conexão falhou.")
        return
        
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            api_token_telegram TEXT NOT NULL UNIQUE,
            mercadopago_token TEXT NOT NULL,
            licenca_expira_em TEXT NOT NULL,
            ativo BOOLEAN NOT NULL CHECK (ativo IN (false, true))
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            UNIQUE(username)
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT NOT NULL,
            tenant_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            data_registro TEXT,
            PRIMARY KEY (id, tenant_id)
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS planos (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            preco NUMERIC(10, 2) NOT NULL,
            frequencia TEXT NOT NULL,
            intervalo INTEGER NOT NULL,
            id_plano_mp TEXT,
            ativo BOOLEAN NOT NULL DEFAULT true
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS assinaturas (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            tenant_id INTEGER NOT NULL,
            plano_id INTEGER NOT NULL,
            id_assinatura_mp TEXT,
            status TEXT NOT NULL,
            data_inicio TEXT NOT NULL,
            data_proximo_pagamento TEXT
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()
    print("Tabelas do banco de dados verificadas/criadas.")

# --- ROTAS FLASK E LÓGICA DO PAINEL ---

@app.route(f"/{API_TOKEN}", methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_str)
        # Futuramente, aqui identificaremos o tenant pelo token
        bot.process_new_updates([update])
        return '!', 200
    return "Unsupported Media Type", 415

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # A lógica de login precisará ser adaptada para multi-tenant
        cur.execute('SELECT * FROM admin WHERE username = %s', (username,))
        admin_user = cur.fetchone()
        cur.close()
        conn.close()
        if admin_user and check_password_hash(admin_user['password_hash'], password):
            session['logged_in'], session['username'] = True, admin_user['username']
            session['tenant_id'] = admin_user.get('tenant_id', 1) # Provisório
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
    # LÓGICA DO DASHBOARD REIMPLEMENTADA
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Por agora, os dados são globais. Futuramente, filtraremos por tenant_id.
    tenant_id = session.get('tenant_id', 1) 

    cur.execute('SELECT COUNT(id) FROM users') # WHERE tenant_id = %s', (tenant_id,))
    total_usuarios = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(id) FROM planos') # WHERE tenant_id = %s', (tenant_id,))
    total_planos = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(id), SUM(preco) FROM assinaturas WHERE status = %s", ('ativo',)) # WHERE tenant_id = %s
    vendas_data = cur.fetchone()
    total_assinaturas_ativas = vendas_data[0] or 0
    # A receita total será mais complexa de calcular com assinaturas (precisará de uma tabela de pagamentos)
    receita_total = 0.0 

    cur.execute("""
        SELECT a.id, u.username, u.first_name, p.nome, p.preco, a.data_inicio, a.status
        FROM assinaturas a
        JOIN users u ON a.user_id = u.id AND a.tenant_id = u.tenant_id
        JOIN planos p ON a.plano_id = p.id
        ORDER BY a.id DESC LIMIT 5
    """) # WHERE a.tenant_id = %s
    assinaturas_recentes = cur.fetchall()
    
    chart_labels, chart_data = [], []
    today = datetime.now()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        chart_labels.append(day.strftime('%d/%m'))
        # A lógica do gráfico precisará ser adaptada para uma tabela de pagamentos
        chart_data.append(0) 

    cur.close()
    conn.close()
    
    return render_template('index.html', 
                           total_assinaturas=total_assinaturas_ativas, 
                           total_usuarios=total_usuarios, 
                           total_planos=total_planos,
                           receita_total=receita_total,
                           assinaturas_recentes=assinaturas_recentes,
                           chart_labels=json.dumps(chart_labels), 
                           chart_data=json.dumps(chart_data))

@app.route('/planos', methods=['GET', 'POST'])
def planos():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    tenant_id = session.get('tenant_id', 1) # Provisório

    if request.method == 'POST':
        nome, preco, frequencia, intervalo = request.form['nome'], float(request.form['preco']), request.form['frequencia'], int(request.form['intervalo'])
        
        plano_mp = pagamentos_subscriptions.criar_plano_assinatura(nome, preco, frequencia, intervalo)

        if plano_mp and plano_mp.get('id'):
            id_plano_mp = plano_mp['id']
            cur.execute(
                'INSERT INTO planos (tenant_id, nome, preco, frequencia, intervalo, id_plano_mp, ativo) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (tenant_id, nome, preco, frequencia, intervalo, id_plano_mp, True)
            )
            conn.commit()
            flash('Plano de assinatura criado com sucesso!', 'success')
        else:
            flash('Erro: Não foi possível criar o plano no Mercado Pago.', 'danger')
        
        cur.close()
        conn.close()
        return redirect(url_for('planos'))

    cur.execute('SELECT * FROM planos ORDER BY id DESC') # WHERE tenant_id = %s', (tenant_id,))
    lista_planos = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('planos.html', planos=lista_planos)

@app.route('/usuarios')
def usuarios():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    tenant_id = session.get('tenant_id', 1) # Provisório
    cur.execute('SELECT * FROM users ORDER BY id DESC') # WHERE tenant_id = %s', (tenant_id,))
    lista_usuarios = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('usuarios.html', usuarios=lista_usuarios)

# --- INICIALIZAÇÃO FINAL ---
if __name__ != '__main__':
    print("Aplicação a iniciar em modo de produção...")
    init_db()
