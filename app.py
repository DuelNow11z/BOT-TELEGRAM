from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from datetime import datetime
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = 'supersecret'

def get_db_connection():
    conn = sqlite3.connect('dashboard_v2.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    pedidos = conn.execute('SELECT * FROM pedidos ORDER BY id DESC').fetchall()
    total_vendas = conn.execute('SELECT COUNT(*) FROM pedidos').fetchone()[0]
    total_clientes = conn.execute('SELECT COUNT(DISTINCT comprador) FROM pedidos').fetchone()[0]
    conn.close()
    return render_template('dashboard.html', produtos=produtos, pedidos=pedidos,
                           total_vendas=total_vendas, total_clientes=total_clientes)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        senha = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM usuarios WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['senha'], senha):
            session['user'] = username
            return redirect(url_for('index'))
        return render_template('login.html', error='Usuário ou senha incorretos.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/produtos/new', methods=['POST'])
def novo_produto():
    if 'user' not in session:
        return redirect(url_for('login'))
    nome = request.form['nome']
    preco = request.form['preco']
    link = request.form['link']
    conn = get_db_connection()
    conn.execute('INSERT INTO produtos (nome, preco, link_entrega) VALUES (?, ?, ?)', (nome, preco, link))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/produtos/delete/<int:id>')
def deletar_produto(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM produtos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    conn = get_db_connection()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        preco REAL,
        link_entrega TEXT)""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto TEXT,
        status TEXT,
        comprador TEXT,
        data TEXT)""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL)""")
    conn.close()
    app.run(debug=True)
