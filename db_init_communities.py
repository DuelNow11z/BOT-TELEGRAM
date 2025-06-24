import os
import psycopg2
import urllib.parse as up
from werkzeug.security import generate_password_hash

# --- CONFIGURAÇÃO ---
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

def get_db_connection():
    """Conecta-se à base de dados PostgreSQL na Render."""
    up.uses_netloc.append("postgres")
    url = up.urlparse(DATABASE_URL)
    return psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )

def setup_database():
    """
    Apaga as tabelas antigas e cria a nova estrutura para o modelo de Comunidades.
    Também cria o utilizador administrador principal.
    """
    print("A iniciar a configuração da base de dados para o modelo de Comunidades...")
    conn = get_db_connection()
    cur = conn.cursor()

    # Apaga todas as tabelas existentes para garantir uma estrutura limpa
    print("A apagar tabelas antigas...")
    cur.execute("DROP TABLE IF EXISTS vendas, assinaturas, produtos, passes, users, admin, configuracoes, comunidades, admins CASCADE;")

    # --- TABELA PRINCIPAL: COMUNIDADES ---
    print("A criar a tabela 'comunidades'...")
    cur.execute('''
    CREATE TABLE comunidades (
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        descricao TEXT,
        imagem_url TEXT,
        telegram_group_id TEXT,
        status TEXT DEFAULT 'ativo'
    );
    ''')

    # --- TABELA DE ADMINS ---
    print("A criar a tabela 'admins'...")
    cur.execute('''
    CREATE TABLE admins (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_super_admin BOOLEAN DEFAULT TRUE
    );
    ''')
    
    # Adicionar outras tabelas com 'comunidade_id' aqui no futuro
    # Ex: produtos, passes, assinaturas, etc.

    # --- INSERIR O ADMIN PRINCIPAL ---
    print(f"A inserir o utilizador admin principal: '{ADMIN_USERNAME}'...")
    hashed_password = generate_password_hash(ADMIN_PASSWORD)
    cur.execute(
        "INSERT INTO admins (username, password_hash, is_super_admin) VALUES (%s, %s, %s)",
        (ADMIN_USERNAME, hashed_password, True)
    )
    
    conn.commit()
    cur.close()
    conn.close()
    print("\n✅ Base de dados configurada com sucesso!")

if __name__ == '__main__':
    setup_database()
