import mercadopago
import os
# --- CORREÇÃO: Importa os módulos específicos para planos e assinaturas ---
import mercadopago.preapproval
import mercadopago.preapproval_plan

# Lê o token diretamente das variáveis de ambiente
MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
# Adicione o username do seu bot aqui para os links de retorno
BOT_USERNAME = os.getenv('BOT_USERNAME', "seu_bot_aqui") 
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

def criar_plano_assinatura(nome_plano, valor, frequencia, intervalo):
    """
    Cria um plano de assinatura no Mercado Pago usando o método correto da SDK.
    """
    # Cria um cliente específico para planos de assinatura
    plan_client = mercadopago.preapproval_plan.PreapprovalPlan(sdk)
    
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
        # Usa o cliente para criar o plano
        plan_response = plan_client.create(plan_data)
        
        # A resposta de sucesso para esta API tem o status no corpo
        if plan_response and plan_response["status"] in [200, 201]:
            print(f"Plano '{nome_plano}' criado com sucesso no Mercado Pago.")
            return plan_response.get("response")
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
    # Cria um cliente específico para assinaturas
    preapproval_client = mercadopago.preapproval.Preapproval(sdk)

    preapproval_data = {
        "preapproval_plan_id": id_plano_mp,
        "payer_email": email_comprador,
        "back_url": f"https://t.me/{BOT_USERNAME}"
    }

    try:
        # Usa o cliente para criar o link de assinatura
        preapproval_response = preapproval_client.create(preapproval_data)

        if preapproval_response and preapproval_response["status"] in [200, 201]:
            # Retorna o link de checkout para o utilizador
            return preapproval_response.get("response", {}).get("init_point")
        else:
            print(f"Erro ao criar link de assinatura. Resposta: {preapproval_response}")
            return None
    except Exception as e:
        print(f"Ocorreu uma exceção ao criar o link da assinatura: {e}")
        return None
