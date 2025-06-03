import sqlite3

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

conn.commit()
conn.close()
print("Banco de dados inicializado com sucesso.")