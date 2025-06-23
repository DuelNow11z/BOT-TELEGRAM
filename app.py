import os
import json
import requests
import telebot
from telebot import types
import base64
# import pagamentos_subscriptions # Comentado temporariamente para garantir o deploy
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
# Novas variáveis para o super admin
SUPER_ADMIN_USERNAME = os.getenv('SUPER_ADMIN_USERNAME')
SUPER_ADMIN_PASSWORD = os.getenv('SUPER_ADMIN_PASSWORD')

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_super_secreta_para_o_painel')

# --- LÓGICA DO BANCO DE DADOS ---
def get_db_connection():
    up.uses_netloc.append("postgres")
    url = up.urlparse(DATABASE_URL)
    return psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY, nome_negocio TEXT NOT NULL, telegram_bot_token TEXT UNIQUE,
            telegram_group_id TEXT, gateway_provider TEXT, gateway_credentials TEXT,
            licenca_ativa BOOLEAN DEFAULT TRUE, licenca_expira_em DATE
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, username TEXT NOT NULL,
            password_hash TEXT NOT NULL, is_super_admin BOOLEAN DEFAULT FALSE,
            UNIQUE(tenant_id, username), FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()
    print("Tabelas do banco de dados verificadas/criadas.")

# --- ROTAS DE SUPER ADMIN ---

# --- NOVA ROTA DE CONFIGURAÇÃO (USO ÚNICO) ---
@app.route('/setup-super-admin')
def setup_super_admin():
    if not (SUPER_ADMIN_USERNAME and SUPER_ADMIN_PASSWORD):
        return "As variáveis de ambiente SUPER_ADMIN_USERNAME e SUPER_ADMIN_PASSWORD não estão definidas.", 400

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Cria o primeiro tenant (a sua própria empresa/serviço)
        nome_negocio = "Meu Bot SaaS"
        data_expiracao = datetime.now().date() + timedelta(days=9999)
        
        cur.execute("SELECT id FROM tenants WHERE nome_negocio = %s", (nome_negocio,))
        tenant = cur.fetchone()
        
        if not tenant:
            cur.execute(
                "INSERT INTO tenants (nome_negocio, licenca_expira_em, licenca_ativa) VALUES (%s, %s, %s) RETURNING id",
                (nome_negocio, data_expiracao, True)
            )
            tenant_id = cur.fetchone()[0]
            print(f"Tenant principal criado com ID: {tenant_id}")
        else:
            tenant_id = tenant[0]
            print(f"Tenant principal já existe com ID: {tenant_id}")

        # 2. Cria o utilizador Super Admin
        hashed_password = generate_password_hash(SUPER_ADMIN_PASSWORD)
        cur.execute("SELECT id FROM admins WHERE username = %s AND is_super_admin = TRUE", (SUPER_ADMIN_USERNAME,))
        admin_exists = cur.fetchone()

        if not admin_exists:
             cur.execute(
                "INSERT INTO admins (tenant_id, username, password_hash, is_super_admin) VALUES (%s, %s, %s, %s)",
                (tenant_id, SUPER_ADMIN_USERNAME, hashed_password, True)
            )
             print(f"Super Admin '{SUPER_ADMIN_USERNAME}' criado com sucesso.")
        else:
            print("Super Admin já existe.")

        conn.commit()
        return "✅ Configuração do Super Admin concluída com sucesso! Por segurança, remova esta rota do seu app.py agora.", 200

    except Exception as e:
        return f"❌ Ocorreu um erro: {e}", 500
    finally:
        cur.close()
        conn.close()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'super_admin_logged_in' in session: return redirect(url_for('super_dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM admins WHERE username = %s AND is_super_admin = TRUE", (username,))
        admin_user = cur.fetchone()
        cur.close()
        conn.close()

        if admin_user and check_password_hash(admin_user['password_hash'], password):
            session['super_admin_logged_in'] = True
            session['username'] = admin_user['username']
            flash('Login de Super Admin realizado com sucesso!', 'success')
            return redirect(url_for('super_dashboard'))
        else:
            flash('Credenciais de Super Admin inválidas.', 'danger')
            
    return render_template('login.html')

# (O resto do seu app.py continua aqui, sem alterações)
# ...
@app.route('/logout')
def logout():
    session.clear()
    flash('Sessão terminada.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@app.route('/super/dashboard')
def super_dashboard():
    if not session.get('super_admin_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM tenants ORDER BY id DESC")
    tenants = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('super_dashboard.html', tenants=tenants)

@app.route('/super/tenant/add', methods=['GET', 'POST'])
def add_tenant():
    if not session.get('super_admin_logged_in'): return redirect(url_for('login'))
    if request.method == 'POST':
        nome_negocio, telegram_token, mp_credentials, dias_licenca = (
            request.form['nome_negocio'], request.form['telegram_bot_token'],
            request.form['gateway_credentials'], int(request.form['dias_licenca'])
        )
        data_expiracao = datetime.now().date() + timedelta(days=dias_licenca)
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO tenants (nome_negocio, telegram_bot_token, gateway_credentials, licenca_expira_em, licenca_ativa) VALUES (%s, %s, %s, %s, %s)",
                (nome_negocio, telegram_token, mp_credentials, data_expiracao, True)
            )
            conn.commit()
            flash(f"Cliente '{nome_negocio}' adicionado com sucesso!", "success")
        except psycopg2.IntegrityError:
            flash("Erro: O token do Telegram já está a ser utilizado.", "danger")
        except Exception as e:
            flash(f"Ocorreu um erro: {e}", "danger")
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('super_dashboard'))
    return render_template('tenant_form.html', form_title="Adicionar Novo Cliente (Tenant)")

@app.route('/super/tenant/edit/<int:id>', methods=['GET', 'POST'])
def edit_tenant(id):
    if not session.get('super_admin_logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        nome_negocio, telegram_token, mp_credentials, licenca_ativa, data_expiracao_str = (
            request.form['nome_negocio'], request.form['telegram_bot_token'],
            request.form['gateway_credentials'], 'licenca_ativa' in request.form,
            request.form['licenca_expira_em']
        )
        cur.execute(
            "UPDATE tenants SET nome_negocio = %s, telegram_bot_token = %s, gateway_credentials = %s, licenca_ativa = %s, licenca_expira_em = %s WHERE id = %s",
            (nome_negocio, telegram_token, mp_credentials, licenca_ativa, data_expiracao_str, id)
        )
        conn.commit()
        flash(f"Cliente '{nome_negocio}' atualizado com sucesso!", "success")
        cur.close()
        conn.close()
        return redirect(url_for('super_dashboard'))
    cur.execute("SELECT * FROM tenants WHERE id = %s", (id,))
    tenant = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('tenant_form.html', form_title=f"Editar Cliente: {tenant['nome_negocio']}", tenant=tenant)

# --- INICIALIZAÇÃO FINAL ---
if __name__ != '__main__':
    print("Aplicação a iniciar em modo de produção...")
    init_db()
