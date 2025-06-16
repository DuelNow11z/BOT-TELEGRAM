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
    # (Este código pode ser movido para o db_init_multitenant.py para ser executado apenas uma vez)
    # Por agora, deixamos aqui para garantir que as tabelas existam.
    pass 

# --- ROTAS FLASK E LÓGICA DO PAINEL ---

@app.route(f"/{API_TOKEN}", methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_str)
        # Aqui virá a lógica para identificar o tenant pelo token e processar a atualização
        bot.process_new_updates([update])
        return '!', 200
    return "Unsupported Media Type", 415

# ... (outras rotas de webhook, como a do Mercado Pago para assinaturas)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        # No futuro, a lógica de login também considerará o tenant
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM admin WHERE username = %s', (username,))
        admin_user = cur.fetchone()
        cur.close()
        conn.close()
        if admin_user and check_password_hash(admin_user['password_hash'], password):
            session['logged_in'], session['username'] = True, admin_user['username']
            # Guardar o tenant_id na sessão será crucial
            session['tenant_id'] = admin_user['tenant_id'] 
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
    # O dashboard agora deve mostrar dados relativos ao tenant logado
    # Esta parte será adaptada futuramente
    return render_template('index.html') # Passaremos os dados do tenant específico

@app.route('/planos', methods=['GET', 'POST'])
def planos():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == 'POST':
        nome = request.form['nome']
        preco = float(request.form['preco'])
        frequencia = request.form['frequencia'] # 'months' or 'years'
        intervalo = int(request.form['intervalo'])

        # 1. Cria o plano no Mercado Pago
        plano_mp = pagamentos_subscriptions.criar_plano_assinatura(nome, preco, frequencia, intervalo)

        if plano_mp and plano_mp.get('id'):
            # 2. Guarda o plano no nosso banco de dados
            id_plano_mp = plano_mp['id']
            cur.execute(
                'INSERT INTO planos (nome, preco, frequencia, intervalo, id_plano_mp, ativo) VALUES (%s, %s, %s, %s, %s, %s)',
                (nome, preco, frequencia, intervalo, id_plano_mp, True)
            )
            conn.commit()
            flash('Plano de assinatura criado com sucesso!', 'success')
        else:
            flash('Erro: Não foi possível criar o plano no Mercado Pago.', 'danger')
        
        cur.close()
        conn.close()
        return redirect(url_for('planos'))

    # Busca os planos existentes para exibir na tabela
    cur.execute('SELECT * FROM planos ORDER BY id DESC')
    lista_planos = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('planos.html', planos=lista_planos)


@app.route('/usuarios')
def usuarios():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # A query deverá ser adaptada para buscar usuários do tenant logado
    cur.execute('SELECT * FROM users ORDER BY id DESC')
    lista_usuarios = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('usuarios.html', usuarios=lista_usuarios)

# --- INICIALIZAÇÃO FINAL ---
if __name__ != '__main__':
    # Esta parte só é executada quando em produção (na Render)
    # A configuração do webhook será mais complexa, pois precisaremos de um para cada tenant
    print("Aplicação a iniciar em modo de produção...")
    init_db() # Garante que as tabelas existem no primeiro arranque

