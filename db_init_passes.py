import sqlite3

# Usaremos um novo nome de ficheiro para não interferir com o seu projeto atual.
DB_NAME = 'bot_passes.db'
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

print("Iniciando a criação do banco de dados para o modelo de Passes de Acesso...")

# Tabela de Utilizadores (sem alterações)
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

# --- TABELA DE PASSES (substitui 'produtos') ---
# Adicionamos a coluna 'duracao_dias' para definir a validade de cada passe.
cursor.execute('''
CREATE TABLE IF NOT EXISTS passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    duracao_dias INTEGER NOT NULL
);
''')
print("Tabela 'passes' criada.")

# --- NOVA TABELA: ASSINATURAS ---
# Regista o acesso de cada utilizador e a sua data de expiração.
cursor.execute('''
CREATE TABLE IF NOT EXISTS assinaturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pass_id INTEGER NOT NULL,
    payment_id TEXT,
    data_inicio TEXT NOT NULL,
    data_expiracao TEXT NOT NULL,
    status TEXT NOT NULL, -- 'ativo' ou 'expirado'
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(pass_id) REFERENCES passes(id)
);
''')
print("Tabela 'assinaturas' criada.")

# Tabela de Admin (sem alterações)
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

print(f"\nBanco de dados '{DB_NAME}' criado com sucesso!")

