from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import check_password_hash
import requests 
import pagamentos 
import config 
from datetime import datetime, timedelta, time
import json

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_dificil_de_adivinhar' 

DB_NAME = 'dashboard.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    return conn

# --- ROTA DE WEBHOOK ---
@app.route('/webhook/mercado-pago', methods=['POST'])
def webhook_mercado_pago():
    notification = request.json
    if notification and notification.get('type') == 'payment':
        payment_id = notification['data']['id']
        payment_info = pagamentos.verificar_status_pagamento(payment_id)
        
        if payment_info and payment_info['status'] == 'approved':
            venda_id = payment_info.get('external_reference')
            if not venda_id: return jsonify({'status': 'ignored'}), 200

            conn = get_db_connection()
            venda = conn.execute('SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente')).fetchone()

            if venda:
                conn.execute('UPDATE vendas SET status = ?, payment_id = ? WHERE id = ?', ('aprovado', payment_id, venda_id))
                conn.commit()
                produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (venda['produto_id'],)).fetchone()
                conn.close()
                if produto:
                    enviar_produto_telegram(venda['user_id'], produto['nome'], produto['link'])
                return jsonify({'status': 'success'}), 200
            else:
                conn.close()
                return jsonify({'status': 'already_processed'}), 200
    return jsonify({'status': 'ignored'}), 200

def enviar_produto_telegram(user_id, nome_produto, link_produto):
    url = f"https://api.telegram.org/bot{config.API_TOKEN}/sendMessage"
    texto = (f"🎉 Pagamento Aprovado!\n\n"
             f"Obrigado por comprar *{nome_produto}*.\n\n"
             f"Aqui está o seu link de acesso:\n{link_produto}")
    payload = { 'chat_id': user_id, 'text': texto, 'parse_mode': 'Markdown' }
    try:
        requests.post(url, json=payload)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem de entrega: {e}")

# --- ROTAS DE AUTENTICAÇÃO E DASHBOARD ---
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
    total_usuarios = conn.execute('SELECT COUNT(id) FROM users').fetchone()[0]
    total_produtos = conn.execute('SELECT COUNT(id) FROM produtos').fetchone()[0]
    
    vendas_data = conn.execute("SELECT COUNT(v.id), SUM(p.preco) FROM vendas v JOIN produtos p ON v.produto_id = p.id WHERE v.status = ?", ('aprovado',)).fetchone()
    total_vendas_aprovadas = vendas_data[0] or 0
    receita_total = vendas_data[1] or 0.0

    vendas_recentes = conn.execute('''
        SELECT v.id, u.username, u.first_name, p.nome, p.preco, v.data_venda,
               CASE
                   WHEN v.status = 'aprovado' THEN 'aprovado'
                   WHEN v.status = 'pendente' AND DATETIME('now', 'localtime', '-24 hours') > DATETIME(v.data_venda) THEN 'cancelado'
                   ELSE 'pendente'
               END AS status
        FROM vendas v
        JOIN users u ON v.user_id = u.id
        JOIN produtos p ON v.produto_id = p.id
        ORDER BY v.id DESC LIMIT 5
    ''').fetchall()
    
    chart_labels, chart_data = [], []
    today = datetime.now()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        start_of_day, end_of_day = datetime.combine(day.date(), time.min), datetime.combine(day.date(), time.max)
        chart_labels.append(day.strftime('%d/%m'))
        daily_revenue = conn.execute("SELECT SUM(p.preco) FROM vendas v JOIN produtos p ON v.produto_id = p.id WHERE v.status = 'aprovado' AND v.data_venda BETWEEN ? AND ?", (start_of_day, end_of_day)).fetchone()[0]
        chart_data.append(daily_revenue or 0)
    conn.close()

    return render_template('index.html', total_vendas=total_vendas_aprovadas, total_usuarios=total_usuarios, total_produtos=total_produtos, receita_total=receita_total, vendas_recentes=vendas_recentes, chart_labels=json.dumps(chart_labels), chart_data=json.dumps(chart_data))

# --- ROTAS DE GESTÃO ---
@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    if request.method == 'POST':
        nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
        conn = get_db_connection()
        conn.execute('INSERT INTO produtos (nome, preco, link) VALUES (?, ?, ?)', (nome, preco, link))
        conn.commit()
        conn.close()
        flash('Produto adicionado com sucesso!', 'success')
        return redirect(url_for('produtos'))

    conn = get_db_connection()
    lista_produtos = conn.execute('SELECT * FROM produtos ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('produtos.html', produtos=lista_produtos)

# --- NOVA ROTA PARA EDITAR PRODUTOS ---
@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (id,)).fetchone()

    if request.method == 'POST':
        nome = request.form['nome']
        preco = request.form['preco']
        link = request.form['link']
        conn.execute('UPDATE produtos SET nome = ?, preco = ?, link = ? WHERE id = ?',
                     (nome, preco, link, id))
        conn.commit()
        conn.close()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('produtos'))

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
    produtos_disponiveis = conn.execute('SELECT id, nome FROM produtos ORDER BY nome').fetchall()
    query_base = '''
        SELECT T.*
        FROM (
            SELECT v.id, u.username, u.first_name, p.nome, p.preco, v.data_venda, p.id as produto_id,
                   CASE
                       WHEN v.status = 'aprovado' THEN 'aprovado'
                       WHEN v.status = 'pendente' AND DATETIME('now', 'localtime', '-24 hours') > DATETIME(v.data_venda) THEN 'cancelado'
                       ELSE 'pendente'
                   END AS status
            FROM vendas v
            JOIN users u ON v.user_id = u.id
            JOIN produtos p ON v.produto_id = p.id
        ) AS T
    '''
    conditions = []
    params = []

    data_inicio_str, data_fim_str, pesquisa_str, produto_id_str, status_str = (
        request.args.get('data_inicio'), request.args.get('data_fim'),
        request.args.get('pesquisa'), request.args.get('produto_id'), request.args.get('status')
    )
    
    if data_inicio_str:
        conditions.append("DATE(T.data_venda) >= ?"); params.append(data_inicio_str)
    if data_fim_str:
        conditions.append("DATE(T.data_venda) <= ?"); params.append(data_fim_str)
    if pesquisa_str:
        conditions.append("(T.username LIKE ? OR T.nome LIKE ? OR T.first_name LIKE ?)")
        params.extend([f'%{pesquisa_str}%'] * 3)
    if produto_id_str:
        conditions.append("T.produto_id = ?"); params.append(produto_id_str)
    if status_str:
        conditions.append("T.status = ?"); params.append(status_str)

    if conditions:
        query_base += " WHERE " + " AND ".join(conditions)
    query_base += " ORDER BY T.id DESC"
    lista_vendas = conn.execute(query_base, tuple(params)).fetchall()
    conn.close()
    return render_template('vendas.html', vendas=lista_vendas, produtos_disponiveis=produtos_disponiveis)

@app.route('/usuarios')
def usuarios():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    lista_usuarios = conn.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('usuarios.html', usuarios=lista_usuarios)

@app.route('/remove_user/<int:id>')
def remove_user(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Usuário removido com sucesso!', 'danger')
    return redirect(url_for('usuarios'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
