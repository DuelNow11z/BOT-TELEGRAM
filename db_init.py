import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("dashboard_v2.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS produtos (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 nome TEXT NOT NULL,
 preco REAL NOT NULL,
 link_entrega TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS pedidos (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 produto TEXT NOT NULL,
 status TEXT NOT NULL,
 comprador TEXT NOT NULL,
 data TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT NOT NULL UNIQUE,
 senha TEXT NOT NULL
)
""")

# Criar usuário admin se não existir
cursor.execute("SELECT * FROM usuarios WHERE username = 'admin'")
if not cursor.fetchone():
    senha_hash = generate_password_hash("admin123")
    cursor.execute("INSERT INTO usuarios (username, senha) VALUES (?, ?)", ('admin', senha_hash))

conn.commit()
conn.close()
print("Banco de dados inicializado com sucesso.")
