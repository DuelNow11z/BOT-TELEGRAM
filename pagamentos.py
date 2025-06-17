import mercadopago
import config

sdk = mercadopago.SDK(config.MERCADOPAGO_ACCESS_TOKEN)

def criar_pagamento_pix(passe, user, venda_id):
    """
    Cria um pagamento PIX para a compra de um Passe de Acesso.
    """
    if not config.BASE_URL:
        print("[ERRO] A variável BASE_URL não está definida em config.py.")
        return None
        
    notification_url = f"{config.BASE_URL}/webhook/mercado-pago"
    
    payment_data = {
        'transaction_amount': float(passe['preco']),
        'payment_method_id': 'pix',
        'payer': {
            'email': f"user_{user.id}@email.com",
            'first_name': user.first_name or "Comprador",
            'last_name': user.last_name or "Bot",
        },
        'notification_url': notification_url,
        'external_reference': str(venda_id), # Usaremos o ID da assinatura
        'description': f"Acesso: {passe['nome']}",
    }

    try:
        payment_response = sdk.payment().create(payment_data)
        return payment_response["response"]
    except Exception as e:
        print(f"Erro ao criar pagamento PIX: {e}")
        return None

def verificar_status_pagamento(payment_id):
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info["response"]
    except Exception as e:
        print(f"Erro ao verificar status do pagamento: {e}")
        return None
