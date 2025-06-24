import mercadopago
import os

def criar_pagamento_pix(item, user, reference_id, access_token):
    """
    Cria um pagamento PIX usando o Access Token fornecido.
    """
    if not access_token:
        print("[ERRO] Access Token do Mercado Pago não fornecido.")
        return None

    sdk = mercadopago.SDK(access_token)
    
    BASE_URL = os.getenv('BASE_URL')
    if not BASE_URL:
        print("[ERRO] A variável de ambiente BASE_URL não está definida.")
        return None
        
    notification_url = f"{BASE_URL}/webhook/mercado-pago"
    
    payment_data = {
        'transaction_amount': float(item['preco']),
        'payment_method_id': 'pix',
        'payer': {
            'email': f"user_{user.id}@email.com",
            'first_name': user.first_name or "Comprador",
            'last_name': user.last_name or "Bot",
        },
        'notification_url': notification_url,
        'external_reference': str(reference_id),
        'description': f"Compra: {item['nome']}",
    }

    try:
        payment_response = sdk.payment().create(payment_data)
        return payment_response["response"]
    except Exception as e:
        print(f"Erro ao criar pagamento PIX: {e}")
        return None

def verificar_status_pagamento(payment_id, access_token):
    """Verifica o status de um pagamento no Mercado Pago."""
    if not access_token:
        print("[ERRO] Access Token do Mercado Pago não fornecido para verificação.")
        return None
        
    sdk = mercadopago.SDK(access_token)
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info["response"]
    except Exception as e:
        print(f"Erro ao verificar status do pagamento: {e}")
        return None
