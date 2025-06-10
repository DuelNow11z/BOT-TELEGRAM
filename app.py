from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import check_password_hash
import requests # Biblioteca para fazer requisições HTTP
import pagamentos # Nosso módulo de pagamentos
import config # Nosso módulo de configurações

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_dificil_de_adivinhar' 

DB_NAME = 'dashboard.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    return conn

# --- ROTA DE WEBHOOK (NOVA) ---
# Esta rota receberá as notificações do Mercado Pago

@app.route('/webhook/mercado-pago', methods=['POST'])
def webhook_mercado_pago():
    notification = request.json
    print("Webhook recebido:", notification)

    if notification and notification.get('type') == 'payment' and notification.get('action') == 'payment.updated':
        payment_id = notification['data']['id']
        
        # 1. Verifica o status do pagamento na API do Mercado Pago
        payment_info = pagamentos.verificar_status_pagamento(payment_id)
        
        if payment_info and payment_info['status'] == 'approved':
            venda_id = payment_info.get('external_reference')
            if not venda_id:
                print("Webhook ignorado: external_reference não encontrada.")
                return jsonify({'status': 'ignored'}), 200

            conn = get_db_connection()
            cursor = conn.cursor()

            # 2. Verifica se a venda já não foi processada
            venda = cursor.execute('SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente')).fetchone()

            if venda:
                # 3. Atualiza o status da venda para 'aprovado'
                cursor.execute('UPDATE vendas SET status = ?, payment_id = ? WHERE id = ?', ('aprovado', payment_id, venda_id))
                conn.commit()

                # 4. Busca os dados para enviar o produto
                produto_id = venda['produto_id']
                user_id = venda['user_id']
                produto = cursor.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,)).fetchone()
                conn.close()

                # 5. Envia o produto para o usuário via Telegram
                if produto:
                    enviar_produto_telegram(user_id, produto['nome'], produto['link'])
                
                print(f"Venda {venda_id} aprovada e produto enviado para o usuário {user_id}.")
                return jsonify({'status': 'success'}), 200
            else:
                conn.close()
                print(f"Webhook ignorado: venda {venda_id} não encontrada ou já processada.")
                return jsonify({'status': 'already_processed'}), 200

    return jsonify({'status': 'ignored'}), 200

def enviar_produto_telegram(user_id, nome_produto, link_produto):
    """
    Usa a API do Telegram diretamente para enviar a mensagem com o produto.
    """
    url = f"https://api.telegram.org/bot{config.API_TOKEN}/sendMessage"
    texto = (
        f"🎉 Pagamento Aprovado!\n\n"
        f"Obrigado por comprar *{nome_produto}*.\n\n"
        f"Aqui está o seu link de acesso:\n"
        f"{link_produto}"
    )
    payload = {
        'chat_id': user_id,
        'text': texto,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status() # Lança um erro para respostas ruins (4xx ou 5xx)
        print(f"Mensagem de entrega enviada com sucesso para o usuário {user_id}")
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem de entrega para o usuário {user_id}: {e}")


# --- Rotas do painel (sem alterações) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session:
        return redirect(url_for('index'))
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
    users = conn.execute('SELECT * FROM users').fetchall()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    vendas = conn.execute('SELECT v.id, u.username, p.nome, v.status, v.data_venda FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id ORDER BY v.id DESC').fetchall()
    conn.close()
    return render_template('index.html', users=users, produtos=produtos, vendas=vendas, total_vendas=len(vendas), total_usuarios=len(users), total_produtos=len(produtos))

@app.route('/add_product', methods=['POST'])
def add_product():
    if not session.get('logged_in'): return redirect(url_for('login'))
    nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
    conn = get_db_connection()
    conn.execute('INSERT INTO produtos (nome, preco, link) VALUES (?, ?, ?)', (nome, preco, link))
    conn.commit()
    conn.close()
    flash('Produto adicionado com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/remove_product/<int:id>')
def remove_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM produtos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Produto removido com sucesso!', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
