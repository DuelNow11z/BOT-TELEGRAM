import sqlite3

# Nome do ficheiro da base de dados local
DB_NAME = 'bot_hybrid.db'
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

print("Iniciando a criação/verificação do banco de dados...")

# Tabela de Utilizadores
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, data_registro TEXT
);
''')

# Tabela de Produtos
cursor.execute('''
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, preco REAL NOT NULL, link TEXT NOT NULL
);
''')

# Tabela de Vendas de Produtos
cursor.execute('''
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, produto_id INTEGER NOT NULL, 
    preco REAL, payment_id TEXT, status TEXT, data_venda TEXT, 
    FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(produto_id) REFERENCES produtos(id)
);
''')

# Tabela de Passes de Acesso
cursor.execute('''
CREATE TABLE IF NOT EXISTS passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, preco REAL NOT NULL, duracao_dias INTEGER NOT NULL
);
''')

# Tabela de Assinaturas de Passes
cursor.execute('''
CREATE TABLE IF NOT EXISTS assinaturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, pass_id INTEGER NOT NULL, 
    payment_id TEXT, data_inicio TEXT, data_expiracao TEXT, status TEXT NOT NULL, 
    FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(pass_id) REFERENCES passes(id)
);
''')

# Tabela de Administradores
cursor.execute('''
CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL
);
''')

# --- NOVA TABELA: CONFIGURAÇÕES ---
# Armazena as configurações do sistema, como as credenciais de pagamento.
cursor.execute('''
CREATE TABLE IF NOT EXISTS configuracoes (
    id INTEGER PRIMARY KEY CHECK (id = 1), -- Garante que haverá apenas uma linha de configuração
    gateway_provider TEXT DEFAULT 'mercadopago',
    mercadopago_token TEXT
);
''')
# Insere uma linha de configuração padrão se a tabela estiver vazia
cursor.execute("INSERT OR IGNORE INTO configuracoes (id) VALUES (1);")

print("Estrutura do banco de dados verificada/criada com sucesso.")
conn.commit()
conn.close()
