import mercadopago
import os

# Lê o token diretamente das variáveis de ambiente
MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
# Adicione o username do seu bot aqui para os links de retorno
BOT_USERNAME = "seu_bot_aqui" # Ex: meusuperbot
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

def criar_plano_assinatura(nome_plano, valor, frequencia, intervalo):
    """
    Cria um plano de assinatura no Mercado Pago.

    Args:
        nome_plano (str): Nome do plano (ex: "Plano Mensal VIP").
        valor (float): Preço a ser cobrado a cada ciclo.
        frequencia (str): Unidade de tempo ('months' ou 'years').
        intervalo (int): Número de unidades de tempo (ex: 1 para cada mês).

    Returns:
        dict: A resposta da API do Mercado Pago ou None em caso de erro.
    """
    
    plan_data = {
        "reason": nome_plano,
        "auto_recurring": {
            "frequency": intervalo,
            "frequency_type": frequencia,
            "transaction_amount": valor,
            "currency_id": "BRL"
        },
        # MODIFICAÇÃO: Aponta a URL de retorno diretamente para o bot.
        "back_url": f"https://t.me/{BOT_USERNAME}"
    }

    try:
        plan_response = sdk.preapproval_plan().create(plan_data)
        if plan_response["status"] == 201:
            print(f"Plano '{nome_plano}' criado com sucesso no Mercado Pago.")
            return plan_response["response"]
        else:
            print(f"Erro ao criar plano. Status: {plan_response['status']}")
            print("Resposta:", plan_response.get("response"))
            return None
    except Exception as e:
        print(f"Ocorreu uma exceção ao criar o plano: {e}")
        return None

def criar_link_assinatura(id_plano_mp, email_comprador):
    """
    Cria o link de checkout para um usuário assinar um plano.
    """
    preapproval_data = {
        "preapproval_plan_id": id_plano_mp,
        "payer_email": email_comprador,
        # MODIFICAÇÃO: Garante que a URL de retorno aponte para o bot.
        "back_url": f"https://t.me/{BOT_USERNAME}"
    }

    try:
        preapproval_response = sdk.preapproval().create(preapproval_data)
        if preapproval_response["status"] == 201:
            # Retorna o link de checkout para o usuário
            return preapproval_response["response"]["init_point"]
        else:
            print(f"Erro ao criar link de assinatura. Status: {preapproval_response['status']}")
            return None
    except Exception as e:
        print(f"Ocorreu uma exceção ao criar o link da assinatura: {e}")
        return None
