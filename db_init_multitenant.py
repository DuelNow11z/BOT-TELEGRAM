import os
import psycopg2
import urllib.parse as up

# --- CONFIGURAÇÃO ---
# Lê a URL da base de dados a partir das variáveis de ambiente
DATABASE_URL = os.getenv('DATABASE_URL')

def init_db():
    """
    Este script conecta-se à base de dados PostgreSQL na Render e cria
    a estrutura de tabelas necessária para o modelo de licenças (multi-tenant).
    """
    if not DATABASE_URL:
        print("❌ ERRO: A variável de ambiente DATABASE_URL não foi definida.")
        return

    conn = None
    try:
        up.uses_netloc.append("postgres")
        url = up.urlparse(DATABASE_URL)
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
        cursor = conn.cursor()

        print("Iniciando a criação das tabelas para o modelo de Licenças...")

        # --- TABELA DE TENANTS (SEUS CLIENTES) ---
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY,
            nome_negocio TEXT NOT NULL,
            
            -- Configurações do Bot
            telegram_bot_token TEXT UNIQUE,
            telegram_group_id TEXT,

            -- Configurações de Pagamento
            gateway_provider TEXT, -- Ex: 'mercadopago', 'stripe'
            gateway_credentials TEXT, -- Armazenará as chaves como um JSON seguro
            
            -- Gestão da Licença
            licenca_ativa BOOLEAN DEFAULT TRUE,
            licenca_expira_em DATE
        );
        ''')
        print("Tabela 'tenants' verificada/criada.")

        # --- TABELA DE ADMINS ---
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_super_admin BOOLEAN DEFAULT FALSE,
            UNIQUE(tenant_id, username),
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        );
        ''')
        print("Tabela 'admins' verificada/criada.")

        # --- TABELAS DE DADOS ISOLADAS POR TENANT ---
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            preco NUMERIC(10, 2) NOT NULL,
            link TEXT NOT NULL,
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        );
        ''')
        print("Tabela 'produtos' verificada/criada.")

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS passes (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            preco NUMERIC(10, 2) NOT NULL,
            duracao_dias INTEGER NOT NULL,
            FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        );
        ''')
        print("Tabela 'passes' verificada/criada.")
        
        # (Outras tabelas como 'users', 'vendas', 'assinaturas' seguiriam a mesma lógica,
        #  sempre com a coluna 'tenant_id' e a FOREIGN KEY correspondente)

        conn.commit()
        cursor.close()
        print("\n✅ Banco de dados configurado com sucesso para o modelo de licenças!")

    except Exception as e:
        print(f"❌ Ocorreu um erro ao inicializar a base de dados: {e}")
    finally:
        if conn is not None:
            conn.close()

if __name__ == '__main__':
    # Para executar este script localmente, você precisaria de um ficheiro .env
    # ou de definir as variáveis de ambiente no seu terminal.
    print("A executar o script de inicialização da base de dados...")
    init_db()

