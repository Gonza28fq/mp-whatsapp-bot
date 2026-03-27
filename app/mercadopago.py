import httpx
import os
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MP_API_BASE = "https://api.mercadopago.com"
TOLERANCIA_PORCENTAJE = 0.02

# Zona horaria Argentina: UTC-3
ARG_OFFSET = timedelta(hours=-3)


def formatear_hora_arg(fecha_str: str) -> str:
    if not fecha_str:
        return "sin hora"
    try:
        fecha_str = fecha_str[:19]
        dt_utc = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%S")
        dt_arg = dt_utc + ARG_OFFSET
        return dt_arg.strftime("%d/%m %H:%M")
    except Exception:
        return fecha_str[:16].replace("T", " ")


def extraer_identificador_pagador(pago: dict) -> str:
    """
    Extrae el mejor identificador disponible del pagador
    usando SOLO los datos que vienen en el objeto pago,
    sin hacer llamadas adicionales a la API.

    Orden de prioridad:
    1. first_name + last_name del payer
    2. name del payer
    3. cardholder name (si pago con tarjeta)
    4. identification number (DNI/CUIT)
    5. email
    6. "desconocido"
    """
    payer = pago.get("payer") or {}

    # Log completo del payer para diagnostico
    logger.info(f"Datos del payer: {payer}")

    # 1. Nombre directo en payer
    first = (payer.get("first_name") or "").strip()
    last = (payer.get("last_name") or "").strip()
    if first or last:
        return f"{first} {last}".strip()

    # 2. Campo name
    name = (payer.get("name") or "").strip()
    if name:
        return name

    # 3. Cardholder name (pagos con tarjeta)
    card = pago.get("card") or {}
    cardholder = card.get("cardholder") or {}
    card_name = (cardholder.get("name") or "").strip()
    if card_name:
        return card_name

    # 4. DNI/CUIT de identification
    identification = payer.get("identification") or {}
    id_type = (identification.get("type") or "").strip()
    id_number = (identification.get("number") or "").strip()
    if id_number and id_number != "0":
        return f"{id_type} {id_number}".strip() if id_type else id_number

    # 5. Email
    email = (payer.get("email") or "").strip()
    if email and email != "":
        return email

    return "sin datos"


async def buscar_pago_reciente(
    monto: float | None = None,
    ventana_minutos: int = 20,
    modo_lista: bool = False,
    max_resultados: int = 5,
) -> dict:
    if not MP_ACCESS_TOKEN:
        raise EnvironmentError("MP_ACCESS_TOKEN no está configurado.")

    ahora = datetime.now(timezone.utc)
    desde = ahora - timedelta(minutes=ventana_minutos)
    desde_str = desde.strftime("%Y-%m-%dT%H:%M:%S.000-00:00")

    params = {
        "sort": "date_created",
        "criteria": "desc",
        "range": "date_approved",
        "begin_date": desde_str,
        "end_date": "NOW",
        "status": "approved",
    }

    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

    logger.info(f"Consultando MP | monto={monto} | ventana={ventana_minutos}min | lista={modo_lista}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{MP_API_BASE}/v1/payments/search",
            params=params,
            headers=headers,
        )

        if response.status_code != 200:
            raise Exception(f"Error MP API: {response.status_code}")

        data = response.json()
        pagos = data.get("results", [])

        logger.info(f"Pagos en ventana: {len(pagos)}")

        # Enriquecer pagos con identificador y hora
        for pago in pagos[:max_resultados]:
            pago["_nombre_pagador"] = extraer_identificador_pagador(pago)
            pago["_hora_arg"] = formatear_hora_arg(pago.get("date_approved", ""))

        if modo_lista:
            return {
                "encontrado": len(pagos) > 0,
                "pago": None,
                "pagos": pagos[:max_resultados],
                "ventana_minutos": ventana_minutos,
                "modo_lista": True,
            }

        if not pagos:
            return {"encontrado": False, "pago": None, "pagos": [], "ventana_minutos": ventana_minutos, "modo_lista": False}

        if monto is None:
            return {"encontrado": True, "pago": pagos[0], "pagos": [], "ventana_minutos": ventana_minutos, "modo_lista": False}

        for pago in pagos:
            monto_pago = float(pago.get("transaction_amount", 0))
            diferencia = abs(monto_pago - monto) / monto if monto > 0 else 1
            if diferencia <= TOLERANCIA_PORCENTAJE:
                return {"encontrado": True, "pago": pago, "pagos": [], "ventana_minutos": ventana_minutos, "modo_lista": False}

        return {"encontrado": False, "pago": None, "pagos": [], "ventana_minutos": ventana_minutos, "modo_lista": False}