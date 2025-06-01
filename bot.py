from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_TOKEN
from pagamentos import gerar_link_pagamento
import sqlite3
from datetime import datetime

def get_db_connection():
    conn = sqlite3.connect("dashboard_v2.db")
    conn.row_factory = sqlite3.Row
    return conn

def salvar_pedido(produto, status, comprador):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO pedidos (produto, status, comprador, data) VALUES (?, ?, ?, ?)",
                   (produto, status, comprador, datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    produtos = conn.execute("SELECT * FROM produtos").fetchall()
    conn.close()

    keyboard = [
        [InlineKeyboardButton(f"🛒 {p['nome']} - R${p['preco']}", callback_data=f"comprar_{p['id']}")]
        for p in produtos
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Olá! Bem-vindo ao bot de vendas.\n"
        "Escolha um produto para comprar:",
        reply_markup=reply_markup
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dados = query.data

    if dados.startswith("comprar_"):
        produto_id = int(dados.split("_")[1])
        conn = get_db_connection()
        produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
        conn.close()

        if produto:
            link = gerar_link_pagamento(produto["nome"], produto["preco"])
            context.user_data["produto_atual"] = produto
            await query.edit_message_text(
                f"💳 Produto: {produto['nome']} - R$ {produto['preco']}\n\n"
                f"Clique no link abaixo para pagar:\n{link}\n\n"
                f"Após o pagamento, envie /confirmar"
            )
        else:
            await query.edit_message_text("Produto não encontrado.")

async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    comprador = user.username or user.first_name
    produto = context.user_data.get("produto_atual")

    if produto:
        salvar_pedido(produto["nome"], "Pago", comprador)
        await update.message.reply_text(
            f"✅ Pagamento confirmado!\n"
            f"Aqui está seu link de entrega: {produto['link_entrega']}"
        )
    else:
        await update.message.reply_text("❗Nenhuma compra recente foi encontrada. Use /start para iniciar.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(CommandHandler("confirmar", confirmar))
    print("Bot rodando...")
    app.run_polling()

if __name__ == '__main__':
    main()
