import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
MERCADO_PAGO_TOKEN = os.environ.get('MERCADO_PAGO_TOKEN')
LINK_ENTREGA = os.environ.get('LINK_ENTREGA', 'https://pt.wikipedia.org/wiki/Wikip%C3%A9dia:P%C3%A1gina_principal')
