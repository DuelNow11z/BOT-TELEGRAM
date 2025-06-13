import os
import sqlite3
import json
import requests
import telebot
from telebot import types
import base64
import pagamentos
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash
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
    conn = psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)
    return conn

def init_db():
    """Cria as tabelas do banco de dados se elas não existirem."""
    conn = get_db_connection()
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
            payer_email TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (produto_id) REFERENCES produtos (id)
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

# --- O resto do seu código, agora adaptado para PostgreSQL ---
# As principais mudanças são o uso de conn.cursor() e placeholders %s

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

# ... (O restante das suas funções e rotas Flask, adaptadas para psycopg2)

# Exemplo de adaptação em uma rota:
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

    # A query com CASE precisa ser ajustada para a sintaxe do PostgreSQL
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
    
    # ... (lógica do gráfico adaptada)
    
    cur.close()
    conn.close()
    
    return render_template('index.html', ...) # Passar todas as variáveis

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

# (Todas as outras rotas precisam ser adaptadas da mesma forma)
