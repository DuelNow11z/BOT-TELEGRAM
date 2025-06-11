import mercadopago
import config

# Função atualizada para aceitar o objeto do produto e do usuário
def criar_pagamento_pix(produto, user, venda_id):
    """
    Cria um pagamento PIX no Mercado Pago com todos os campos de qualidade recomendados.
    """
    sdk = mercadopago.SDK(config.MERCADOPAGO_ACCESS_TOKEN)
    notification_url = f"{config.BASE_URL}/webhook/mercado-pago"
    
    # --- DADOS DO PAGAMENTO ATUALIZADOS ---
    payment_data = {
        'transaction_amount': float(produto['preco']),
        'payment_method_id': 'pix',
        
        # --- Dados do pagador (ainda mais completos) ---
        'payer': {
            'email': f"user_{user.id}@email.com",
            'first_name': user.first_name or "Comprador", # Garante que não seja nulo
            'last_name': user.last_name or "Bot",       # Garante que não seja nulo
            'identification': {
                'type': 'OTHER',
                'number': str(user.id) # Usa o ID do Telegram como identificação
            }
        },
        
        'notification_url': notification_url,
        'external_reference': str(venda_id),
        
        # Descrição geral da transação
        'description': f"Venda de produto digital: {produto['nome']}",
        'statement_descriptor': 'BOTVENDAS',
        
        # --- NOVOS CAMPOS DE QUALIDADE DENTRO DE "additional_info" ---
        'additional_info': {
            "items": [
                {
                    "id": str(produto['id']),
                    "title": produto['nome'],
                    "description": f"Conteúdo digital: {produto['nome']}",
                    "category_id": "digital_content",
                    "quantity": 1,
                    "unit_price": float(produto['preco']),
                }
            ],
            "payer": {
                "first_name": user.first_name or "Comprador",
                "last_name": user.last_name or "Bot",
                "phone": { # Adiciona um telefone genérico para aumentar a pontuação
                    "area_code": "11",
                    "number": "999999999"
                }
            },
        }
    }

    try:
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]
        return payment
    except Exception as e:
        print(f"Erro ao criar pagamento PIX: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'json'):
            print("Resposta do MP:", e.response.json())
        return None

def verificar_status_pagamento(payment_id):
    """
    Verifica o status de um pagamento específico no Mercado Pago.
    """
    sdk = mercadopago.SDK(config.MERCADOPAGO_ACCESS_TOKEN)
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info["response"]
    except Exception as e:
        print(f"Erro ao verificar status do pagamento: {e}")
        return None
