import mercadopago
from config import MERCADO_PAGO_TOKEN

sdk = mercadopago.SDK(MERCADO_PAGO_TOKEN)

def gerar_link_pagamento(nome_produto, preco):
    preference_data = {
        "items": [
            {
                "title": nome_produto,
                "quantity": 1,
                "unit_price": float(preco),
                "currency_id": "BRL"
            }
        ],
        "back_urls": {
            "success": "https://www.google.com",
            "failure": "https://www.google.com",
            "pending": "https://www.google.com"
        },
        "auto_return": "approved"
    }

    preference_response = sdk.preference().create(preference_data)
    return preference_response["response"].get("init_point", "#ERRO")