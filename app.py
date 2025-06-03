from flask import Flask, render_template, session, redirect, url_for, request
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'supersecret'

def get_db_connection():
    conn = sqlite3.connect('dashboard_v2.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    # 🔐 Verifica se o usuário está logado
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM pedidos", conn)
    df['data'] = pd.to_datetime(df['data'], errors='coerce')

    hoje = datetime.today()
    inicio_atual = hoje - timedelta(days=30)
    inicio_anterior = inicio_atual - timedelta(days=30)

    atual = df[(df['data'] >= inicio_atual) & (df['data'] <= hoje)]
    anterior = df[(df['data'] >= inicio_anterior) & (df['data'] < inicio_atual)]

    def resumo(pedidos):
        total = pedidos.shape[0]
        valor = 0.0
        try:
            valor = pedidos['produto'].apply(lambda x: float(x.split('R$')[-1].replace(',', '.')) if 'R$' in x else 0).sum()
        except Exception:
            pass
        return total, round(valor, 2)

    qtd_atual, val_atual = resumo(atual)
    qtd_ant, val_ant = resumo(anterior)

    def variacao(novo, antigo):
        if antigo == 0:
            return 0
        return round(((novo - antigo) / antigo) * 100, 2)

    v_qtd = variacao(qtd_atual, qtd_ant)
    v_val = variacao(val_atual, val_ant)

    historico = atual.groupby(df['data'].dt.strftime('%d/%m')).size().reset_index(name='quantidade')
    labels = historico['data'].tolist()
    valores = historico['quantidade'].tolist()

    total_usuarios = conn.execute("SELECT COUNT(DISTINCT comprador) FROM pedidos").fetchone()[0]
    try:
        total_assinantes = conn.execute("SELECT COUNT(*) FROM assinaturas").fetchone()[0]
    except:
        total_assinantes = 0

    conn.close()
    return render_template('dashboard.html',
                           qtd_atual=qtd_atual,
                           val_atual=val_atual,
                           qtd_ant=qtd_ant,
                           val_ant=val_ant,
                           v_qtd=v_qtd,
                           v_val=v_val,
                           labels=labels,
                           valores=valores,
                           total_usuarios=total_usuarios,
                           total_assinantes=total_assinantes)

# 🔒 Login com usuário fixo
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['username']
        senha = request.form['password']
        if usuario == 'admin' and senha == 'admin':
            session['user'] = usuario
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Usuário ou senha incorretos.")
    return render_template('login.html')

# 🔓 Logout limpa a sessão
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# 📦 Listagem de pedidos (pagos e pendentes)
@app.route('/pedidos')
def pedidos():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    pedidos = conn.execute("SELECT * FROM pedidos ORDER BY data DESC").fetchall()
    conn.close()
    return render_template("pedidos.html", pedidos=pedidos)

if __name__ == '__main__':
    app.run(debug=True)
