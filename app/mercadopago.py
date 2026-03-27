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
    """
    Convierte una fecha ISO de MP (UTC) a hora argentina.
    Ejemplo: "2026-03-26T20:25:35.000-00:00" → "26/03 23:25"
    """
    if not fecha_str:
        return "sin hora"
    try:
        # Normalizar el string de fecha
        fecha_str = fecha_str[:19]  # tomar solo "2026-03-26T20:25:35"
        dt_utc = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%S")
        dt_arg = dt_utc + ARG_OFFSET
        return dt_arg.strftime("%d/%m %H:%M")
    except Exception:
        return fecha_str[:16].replace("T", " ")


async def obtener_nombre_pagador(client: httpx.AsyncClient, pago: dict) -> str:
    """
    Intenta obtener el nombre del titular por múltiples vías.
    Fallback final: email del pagador.
    """
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    payer = pago.get("payer", {})

    # --- Intento 1: nombre directo en el objeto payer ---
    nombre = payer.get("first_name", "").strip()
    apellido = payer.get("last_name", "").strip()
    if nombre or apellido:
        return f"{nombre} {apellido}".strip()

    # --- Intento 2: consulta a /v4/users/{payer_id} ---
    payer_id = str(payer.get("id", ""))
    if payer_id and payer_id != "0":
        try:
            response = await client.get(
                f"{MP_API_BASE}/v4/users/{payer_id}",
                headers=headers,
                timeout=5.0,
            )
            if response.status_code == 200:
                data = response.json()
                full = data.get("full_name", "").strip()
                if full:
                    return full
                first = data.get("first_name", "").strip()
                last = data.get("last_name", "").strip()
                if first or last:
                    return f"{first} {last}".strip()
                nick = data.get("nickname", "").strip()
                if nick:
                    return nick
        except Exception as e:
            logger.warning(f"Error consultando usuario {payer_id}: {e}")

    # --- Fallback final: email ---
    email = payer.get("email", "").strip()
    return email if email else "desconocido"


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

        # Enriquecer con nombre y hora argentina
        for pago in pagos[:max_resultados]:
            pago["_nombre_pagador"] = await obtener_nombre_pagador(client, pago)
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