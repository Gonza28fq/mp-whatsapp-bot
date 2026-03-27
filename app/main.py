from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from app.mercadopago import buscar_pago_reciente
from app.parser import parsear_mensaje
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MP WhatsApp Bot")


@app.get("/")
def health():
    return {"status": "ok", "mensaje": "Bot activo ✅"}


@app.post("/webhook", response_class=PlainTextResponse)
async def webhook_twilio(
    Body: str = Form(...),
    From: str = Form(...),
):
    logger.info(f"Mensaje de {From}: {Body}")

    monto, ventana_minutos, modo_lista = parsear_mensaje(Body)
    resultado = await buscar_pago_reciente(
        monto=monto,
        ventana_minutos=ventana_minutos,
        modo_lista=modo_lista,
    )

    respuesta = formatear_respuesta(resultado, monto)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{respuesta}</Message>
</Response>"""

    return PlainTextResponse(content=twiml, media_type="application/xml")


def formatear_respuesta(resultado: dict, monto_consultado: float | None) -> str:

    # --- Modo lista ---
    if resultado.get("modo_lista"):
        pagos = resultado.get("pagos", [])
        if not pagos:
            return "❌ No hubo pagos en la ultima hora."
        lineas = ["📋 *Ultimos pagos recibidos:*\n"]
        for i, pago in enumerate(pagos, 1):
            monto = pago.get("transaction_amount", 0)
            hora = pago.get("_hora_arg", "sin hora")
            titular = pago.get("_nombre_pagador", "desconocido")
            lineas.append(f"{i}. 💰 ${monto:,.0f} | 🕐 {hora} | 👤 {titular}")
        return "\n".join(lineas)

    # --- Pago encontrado ---
    if resultado["encontrado"]:
        pago = resultado["pago"]
        monto = pago.get("transaction_amount", 0)
        hora = pago.get("_hora_arg", "sin hora")
        titular = pago.get("_nombre_pagador", "desconocido")
        return (
            f"✅ *Pago confirmado*\n"
            f"💰 Monto: ${monto:,.0f}\n"
            f"🕐 Hora: {hora}\n"
            f"👤 Titular: {titular}"
        )

    # --- No encontrado ---
    ventana = resultado["ventana_minutos"]
    if monto_consultado:
        return (
            f"❌ No se encontro pago de ${monto_consultado:,.0f} "
            f"en los ultimos {ventana} minutos.\n"
            f"Podes ampliar la busqueda: escribi *{int(monto_consultado):,} hace 30*"
        )
    return (
        f"❌ No se encontro ningun pago reciente "
        f"en los ultimos {ventana} minutos.\n"
        f"Para ver todos los pagos escribi: *ultimos pagos*"
    )