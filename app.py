import os
import json
import requests
import telebot
from telebot import types
import pagamentos_subscriptions # Manteremos este, pode ser útil no futuro
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras
import urllib.parse as up

# --- CONFIGURAÇÃO ---
API_TOKEN = os.getenv('API_TOKEN') # O SEU token de super admin, se necessário
BASE_URL = os.getenv('BASE_URL')
DATABASE_URL = os.getenv('DATABASE_URL')

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_super_secreta_para_o_painel')

# --- LÓGICA DO BANCO DE DADOS ---
def get_db_connection():
    up.uses_netloc.append("postgres")
    url = up.urlparse(DATABASE_URL)
    return psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port)

def init_db():
    # Este script é executado pelo ficheiro db_init_multitenant.py
    # Mantemos a função aqui para referência, mas não a chamaremos no arranque
    pass

# --- ROTAS DE SUPER ADMIN ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'super_admin_logged_in' in session:
        return redirect(url_for('super_dashboard'))
    
    if request.method == 'POST':
        # Por agora, o login de super admin será fixo.
        # No futuro, podemos criar um utilizador super admin na base de dados.
        if request.form['username'] == 'superadmin' and request.form['password'] == os.getenv('SUPER_ADMIN_PASSWORD', 'admin123'):
            session['super_admin_logged_in'] = True
            flash('Login de Super Admin realizado com sucesso!', 'success')
            return redirect(url_for('super_dashboard'))
        else:
            flash('Credenciais de Super Admin inválidas.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sessão terminada.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@app.route('/super/dashboard')
def super_dashboard():
    if not session.get('super_admin_logged_in'):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM tenants ORDER BY id DESC")
    tenants = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('super_dashboard.html', tenants=tenants)

@app.route('/super/tenant/add', methods=['GET', 'POST'])
def add_tenant():
    if not session.get('super_admin_logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        nome_negocio = request.form['nome_negocio']
        telegram_token = request.form['telegram_bot_token']
        mp_credentials = request.form['gateway_credentials'] # Provisório
        dias_licenca = int(request.form['dias_licenca'])
        
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
    if not session.get('super_admin_logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if request.method == 'POST':
        nome_negocio = request.form['nome_negocio']
        telegram_token = request.form['telegram_bot_token']
        mp_credentials = request.form['gateway_credentials']
        licenca_ativa = 'licenca_ativa' in request.form
        data_expiracao_str = request.form['licenca_expira_em']
        
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

# A lógica do bot e dos webhooks será reimplementada aqui futuramente
# para conseguir lidar com múltiplos tenants.
# Por agora, focamo-nos no painel de gestão.
