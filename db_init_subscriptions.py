import sqlite3

# Usaremos um novo nome de arquivo para o banco de dados de produção
DB_NAME = 'bot_subscriptions.db'
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

print("Iniciando a criação do banco de dados para o modelo de assinaturas...")

# Tabela de Usuários (sem mudanças)
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    data_registro TEXT
)
''')
print("Tabela 'users' verificada/criada.")

# --- NOVA TABELA: PLANOS ---
# Armazena os diferentes planos de assinatura que você oferece.
cursor.execute('''
CREATE TABLE IF NOT EXISTS planos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    frequencia TEXT NOT NULL, -- Ex: 'months' ou 'years'
    intervalo INTEGER NOT NULL, -- Ex: 1 (para 1 mês) ou 1 (para 1 ano)
    id_plano_mp TEXT, -- ID do plano gerado pelo Mercado Pago
    ativo BOOLEAN NOT NULL DEFAULT 1
);
''')
print("Tabela 'planos' criada.")

# --- NOVA TABELA: ASSINATURAS ---
# Vincula um usuário a um plano e rastreia o status da assinatura.
cursor.execute('''
CREATE TABLE IF NOT EXISTS assinaturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plano_id INTEGER NOT NULL,
    id_assinatura_mp TEXT, -- ID da assinatura do usuário no Mercado Pago
    status TEXT NOT NULL, -- Ex: 'ativo', 'pendente', 'cancelado'
    data_inicio TEXT NOT NULL,
    data_proximo_pagamento TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(plano_id) REFERENCES planos(id)
);
''')
print("Tabela 'assinaturas' criada.")

# Tabela de Admin (sem mudanças)
cursor.execute('''
CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);
''')
print("Tabela 'admin' verificada/criada.")

conn.commit()
conn.close()

print(f"\nBanco de dados '{DB_NAME}' criado com sucesso e pronto para o modelo de assinaturas!")
