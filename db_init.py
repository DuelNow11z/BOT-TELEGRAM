import sqlite3

# Nome do arquivo do banco de dados
DB_NAME = 'dashboard.db'

# Conecta ao banco de dados (cria o arquivo se não existir)
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# --- Criação das Tabelas ---

# Tabela para armazenar informações dos usuários do bot
# Esta tabela é populada pelo seu bot.py
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    data_registro TEXT
)
''')

# Tabela para armazenar os produtos à venda
cursor.execute('''
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    link TEXT NOT NULL
)
''')

# Tabela para registrar as vendas
cursor.execute('''
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    produto_id INTEGER,
    payment_id TEXT,
    status TEXT,
    data_venda TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (produto_id) REFERENCES produtos (id)
)
''')

# --- NOVA TABELA ADMIN ---
# Tabela para armazenar os administradores do painel de controle
# A senha é armazenada como um "hash", um formato seguro que não pode ser revertido.
print("Criando tabela 'admin'...")
cursor.execute('''
CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
)
''')


# Salva as alterações e fecha a conexão
conn.commit()
conn.close()

print(f"Banco de dados '{DB_NAME}' inicializado com sucesso!")
print("Tabelas: users, produtos, vendas, admin foram criadas.")

