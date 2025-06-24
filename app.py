import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras
import urllib.parse as up

# --- CONFIGURAÇÃO ---
# Lê as variáveis de ambiente necessárias para a aplicação
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin') # O seu nome de utilizador de admin
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123') # A sua senha de admin
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'uma_chave_super_secreta_e_longa')

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# --- LÓGICA DO BANCO DE DADOS ---
def get_db_connection():
    """Conecta-se à base de dados PostgreSQL na Render."""
    up.uses_netloc.append("postgres")
    url = up.urlparse(DATABASE_URL)
    return psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )

def init_db_and_admin():
    """
    (Re)cria as tabelas e o utilizador admin. Esta função é perigosa e deve ser
    chamada apenas através da rota de setup secreta.
    """
    print("A iniciar a configuração da base de dados...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Apaga tabelas antigas para garantir uma estrutura limpa
    print("A apagar tabelas antigas se existirem...")
    cur.execute("DROP TABLE IF EXISTS admins, comunidades CASCADE;")

    # --- TABELA PRINCIPAL: COMUNIDADES ---
    print("A criar a tabela 'comunidades'...")
    cur.execute('''
    CREATE TABLE comunidades (
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        descricao TEXT,
        imagem_url TEXT,
        telegram_group_id TEXT,
        status TEXT DEFAULT 'ativo'
    );
    ''')

    # --- TABELA DE ADMINS ---
    print("A criar a tabela 'admins'...")
    cur.execute('''
    CREATE TABLE admins (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_super_admin BOOLEAN DEFAULT TRUE
    );
    ''')
    
    # --- INSERIR O ADMIN PRINCIPAL ---
    print(f"A inserir o utilizador admin principal: '{ADMIN_USERNAME}'...")
    hashed_password = generate_password_hash(ADMIN_PASSWORD)
    cur.execute(
        "INSERT INTO admins (username, password_hash, is_super_admin) VALUES (%s, %s, %s)",
        (ADMIN_USERNAME, hashed_password, True)
    )
    
    conn.commit()
    cur.close()
    conn.close()
    print("\n✅ Base de dados e Admin configurados com sucesso!")

# --- ROTAS DO PAINEL DE GESTÃO ---

@app.route('/setup-inicial-seguro')
def setup_inicial_seguro():
    """
    Esta é uma rota secreta para ser acedida apenas uma vez para configurar tudo.
    """
    try:
        init_db_and_admin()
        return "Base de dados e utilizador admin configurados com sucesso! Por segurança, remova esta rota do seu ficheiro app.py e faça um novo deploy.", 200
    except Exception as e:
        return f"Ocorreu um erro durante a configuração: {e}", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session:
        return redirect(url_for('listar_comunidades'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM admins WHERE username = %s", (username,))
        admin_user = cur.fetchone()
        cur.close()
        conn.close()
        if admin_user and check_password_hash(admin_user['password_hash'], password):
            session['logged_in'] = True
            session['username'] = admin_user['username']
            return redirect(url_for('listar_comunidades'))
        else:
            flash('Credenciais inválidas.', 'danger')
    return render_template('login_comunidades.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Sessão terminada com sucesso.", "info")
    return redirect(url_for('login'))

@app.route('/')
def index():
    return redirect(url_for('listar_comunidades'))

@app.route('/comunidades')
def listar_comunidades():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM comunidades ORDER BY nome ASC")
    comunidades = cur.fetchall()
    cur.close()
    conn.close()
    
    # Exemplo de dados para a primeira comunidade (para fins visuais)
    if not comunidades:
        comunidades = [{
            'id': 1,
            'nome': 'Exemplo: Grupo VIP',
            'descricao': 'Comunidade de demonstração. Adicione a sua primeira comunidade para começar.',
            'imagem_url': 'https://placehold.co/400x400/7c3aed/ffffff?text=Exemplo',
            'status': 'ativo'
        }]

    return render_template('comunidades_lista.html', comunidades=comunidades)

@app.route('/comunidade/<int:id>')
def comunidade_opcoes(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Para o exemplo, não precisamos de ir à base de dados ainda.
    # No futuro, aqui buscaremos os dados da comunidade com o ID = id.
    comunidade_exemplo = {
        'id': id,
        'nome': 'Exemplo: Grupo VIP'
    }

    return render_template('comunidade_opcoes.html', comunidade=comunidade_exemplo)

# A lógica do bot e dos webhooks foi removida temporariamente.
# Focamo-nos primeiro em ter o painel de gestão a funcionar.
