import mercadopago
import os

# Lê o token diretamente das variáveis de ambiente
MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
BOT_USERNAME = "seu_bot_aqui" # Ex: meusuperbot
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

def criar_plano_assinatura(nome_plano, valor, frequencia, intervalo):
    """
    Cria um plano de assinatura no Mercado Pago usando o método correto da SDK.
    """
    # --- CORREÇÃO: Acessa o cliente de planos diretamente pelo objeto SDK ---
    plan_client = mercadopago.preapproval_plan.PreapprovalPlanClient(sdk)
    
    plan_data = {
        "reason": nome_plano,
        "auto_recurring": {
            "frequency": intervalo,
            "frequency_type": frequencia,
            "transaction_amount": valor,
            "currency_id": "BRL"
        },
        "back_url": f"https://t.me/{BOT_USERNAME}"
    }

    try:
        plan_response = plan_client.create(plan_data)
        
        # A resposta de sucesso para esta API tem o status no corpo
        if plan_response and plan_response.get("status") == "active":
            print(f"Plano '{nome_plano}' criado com sucesso no Mercado Pago.")
            return plan_response
        else:
            print(f"Erro ao criar plano. Resposta: {plan_response}")
            return None
    except Exception as e:
        print(f"Ocorreu uma exceção ao criar o plano: {e}")
        return None

def criar_link_assinatura(id_plano_mp, email_comprador):
    """
    Cria o link de checkout para um utilizador assinar um plano.
    """
    # --- CORREÇÃO: Acessa o cliente de assinaturas diretamente pelo objeto SDK ---
    preapproval_client = mercadopago.preapproval.PreapprovalClient(sdk)

    preapproval_data = {
        "preapproval_plan_id": id_plano_mp,
        "payer_email": email_comprador,
        "back_url": f"https://t.me/{BOT_USERNAME}"
    }

    try:
        preapproval_response = preapproval_client.create(preapproval_data)

        if preapproval_response and preapproval_response.get("id"):
            # Retorna o link de checkout para o utilizador
            return preapproval_response.get("init_point")
        else:
            print(f"Erro ao criar link de assinatura. Resposta: {preapproval_response}")
            return None
    except Exception as e:
        print(f"Ocorreu uma exceção ao criar o link da assinatura: {e}")
        return None
