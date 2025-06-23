import os
import psycopg2
import urllib.parse as up
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

# Carrega a variável de ambiente da base de dados
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """Conecta-se à base de dados PostgreSQL."""
    up.uses_netloc.append("postgres")
    url = up.urlparse(DATABASE_URL)
    return psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )

def setup_super_admin():
    """
    Cria o primeiro Tenant (a sua própria empresa) e o primeiro Super Admin.
    Este script deve ser executado apenas uma vez.
    """
    print("--- A configurar o Super Admin e o Tenant Principal ---")
    
    # --- Dados do seu negócio principal ---
    NOME_DO_SEU_NEGOCIO = "Meu Bot SaaS" # Pode alterar este nome
    SEU_USERNAME_ADMIN = input("Digite o nome de utilizador para o Super Admin: ")
    SUA_SENHA_ADMIN = input("Digite a senha para o Super Admin: ")
    
    if not SEU_USERNAME_ADMIN or not SUA_SENHA_ADMIN:
        print("❌ Nome de utilizador e senha não podem ser vazios.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Cria o primeiro tenant (a sua própria empresa/serviço)
        print(f"A criar o tenant principal: '{NOME_DO_SEU_NEGOCIO}'...")
        # Licença "infinita" para si mesmo
        data_expiracao = datetime.now().date() + timedelta(days=9999)
        
        cur.execute(
            "INSERT INTO tenants (nome_negocio, licenca_expira_em, licenca_ativa) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING RETURNING id",
            (NOME_DO_SEU_NEGOCIO, data_expiracao, True)
        )
        
        # Se a tabela estiver vazia, obtemos o ID do tenant recém-criado
        tenant_id_row = cur.fetchone()
        if tenant_id_row:
            tenant_id = tenant_id_row[0]
            print(f"Tenant principal criado com ID: {tenant_id}")
        else:
            # Se já existir, assumimos que o ID é 1
            cur.execute("SELECT id FROM tenants WHERE nome_negocio = %s", (NOME_DO_SEU_NEGOCIO,))
            tenant_id = cur.fetchone()[0]
            print(f"Tenant principal já existe com ID: {tenant_id}")


        # 2. Cria o utilizador Super Admin associado a este tenant
        print(f"A criar o utilizador Super Admin: '{SEU_USERNAME_ADMIN}'...")
        hashed_password = generate_password_hash(SUA_SENHA_ADMIN)
        
        # Tenta inserir; se o username já existir para aquele tenant, não faz nada
        cur.execute(
            """
            INSERT INTO admins (tenant_id, username, password_hash, is_super_admin)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, username) DO NOTHING
            """,
            (tenant_id, SEU_USERNAME_ADMIN, hashed_password, True)
        )
        
        conn.commit()
        print("\n✅ Configuração do Super Admin concluída com sucesso!")
        print(f"Pode agora fazer login com o utilizador '{SEU_USERNAME_ADMIN}' e a senha que definiu.")

    except Exception as e:
        print(f"❌ Ocorreu um erro: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    setup_super_admin()
