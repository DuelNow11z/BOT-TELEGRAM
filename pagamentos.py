import mercadopago
import config  # Importa as configurações

def criar_pagamento_pix(valor, descricao, email, venda_id):
    """
    Cria um pagamento PIX no Mercado Pago com uma URL de notificação (webhook).

    Args:
        valor (float): O preço do produto.
        descricao (str): Descrição do produto.
        email (str): Email do comprador (pode ser um email genérico).
        venda_id (int): O ID único da venda gerado no nosso banco de dados.

    Returns:
        dict: O dicionário com os dados do pagamento ou None em caso de erro.
    """
    sdk = mercadopago.SDK(config.MERCADOPAGO_ACCESS_TOKEN)

    # A URL para a qual o Mercado Pago enviará as notificações POST
    # Ex: https://sua-url.ngrok.io/webhook/mercado-pago
    notification_url = f"{config.BASE_URL}/webhook/mercado-pago"
    
    payment_data = {
        'transaction_amount': float(valor),
        'description': descricao,
        'payment_method_id': 'pix',
        'payer': {
            'email': email,
        },
        'notification_url': notification_url,
        # A referência externa agora é o ID da venda, para sabermos qual compra foi paga.
        # Isso é FUNDAMENTAL para o webhook funcionar corretamente.
        'external_reference': str(venda_id)
    }

    try:
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]
        return payment
    except Exception as e:
        print(f"Erro ao criar pagamento PIX: {e}")
        return None


def verificar_status_pagamento(payment_id):
    """
    Verifica o status de um pagamento específico no Mercado Pago.

    Args:
        payment_id (str): O ID do pagamento a ser verificado.

    Returns:
        dict: O dicionário com os dados do pagamento ou None em caso de erro.
    """
    sdk = mercadopago.SDK(config.MERCADOPAGO_ACCESS_TOKEN)
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info["response"]
    except Exception as e:
        print(f"Erro ao verificar status do pagamento: {e}")
        return None
