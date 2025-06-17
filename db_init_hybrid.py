import sqlite3

# Usaremos um novo nome de ficheiro para não interferir com o seu projeto atual.
DB_NAME = 'bot_hybrid.db'
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

print("Iniciando a criação do banco de dados para o modelo Híbrido...")

# Tabela de Utilizadores (comum a ambos os modelos)
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    data_registro TEXT
);
''')
print("Tabela 'users' verificada/criada.")

# --- TABELAS PARA VENDA DE PRODUTOS ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    link TEXT NOT NULL
);
''')
print("Tabela 'produtos' criada.")

cursor.execute('''
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    preco REAL, 
    payment_id TEXT,
    status TEXT, -- pendente, aprovado, expirado
    data_venda TEXT,
    payer_name TEXT,
    payer_email TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(produto_id) REFERENCES produtos(id)
);
''')
print("Tabela 'vendas' criada.")

# --- TABELAS PARA PASSES DE ACESSO ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    duracao_dias INTEGER NOT NULL
);
''')
print("Tabela 'passes' criada.")

cursor.execute('''
CREATE TABLE IF NOT EXISTS assinaturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pass_id INTEGER NOT NULL,
    payment_id TEXT,
    data_inicio TEXT,
    data_expiracao TEXT,
    status TEXT NOT NULL, -- pendente, ativo, expirado
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(pass_id) REFERENCES passes(id)
);
''')
print("Tabela 'assinaturas' criada.")

# Tabela de Admin (comum a ambos os modelos)
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

print(f"\nBanco de dados '{DB_NAME}' criado com sucesso para o modelo híbrido!")

