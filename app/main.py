from fastapi import FastAPI, Request, Form
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
    logger.info(f"Mensaje recibido de {From}: {Body}")

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


def identificar_pagador(pago: dict) -> str:
    """
    Devuelve el nombre del titular si está disponible,
    sino el email, sino 'desconocido'.
    """
    nombre = pago.get("_nombre_pagador")
    if nombre:
        return nombre
    email = pago.get("payer", {}).get("email", "")
    return email if email else "desconocido"


def formatear_respuesta(resultado: dict, monto_consultado: float | None) -> str:

    # --- Modo lista de pagos ---
    if resultado.get("modo_lista"):
        pagos = resultado.get("pagos", [])
        if not pagos:
            return "❌ No hubo pagos en la ultima hora."

        lineas = ["📋 *Ultimos pagos recibidos:*\n"]
        for i, pago in enumerate(pagos, 1):
            monto = pago.get("transaction_amount", 0)
            hora = pago.get("date_approved", "")[:16].replace("T", " ")
            pagador = identificar_pagador(pago)
            lineas.append(f"{i}. 💰 ${monto:,.0f} | 🕐 {hora} | 👤 {pagador}")

        return "\n".join(lineas)

    # --- Pago encontrado ---
    if resultado["encontrado"]:
        pago = resultado["pago"]
        monto = pago.get("transaction_amount", 0)
        fecha = pago.get("date_approved", "")[:16].replace("T", " ")
        pagador = identificar_pagador(pago)
        return (
            f"✅ *Pago confirmado*\n"
            f"💰 Monto: ${monto:,.0f}\n"
            f"🕐 Hora: {fecha}\n"
            f"👤 Titular: {pagador}"
        )

    # --- No encontrado ---
    ventana = resultado["ventana_minutos"]
    if monto_consultado:
        return (
            f"❌ No se encontro ningun pago de ${monto_consultado:,.0f} "
            f"en los ultimos {ventana} minutos.\n"
            f"Podes consultar con mas tiempo: escribi *{int(monto_consultado):,} hace 30*"
        )
    return (
        f"❌ No se encontro ningun pago reciente "
        f"en los ultimos {ventana} minutos.\n"
        f"Para ver todos los pagos escribi: *ultimos pagos*"
    )