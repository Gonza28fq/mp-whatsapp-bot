import httpx
import os
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MP_API_BASE = "https://api.mercadopago.com"

# Tolerancia ampliada al 2%
TOLERANCIA_PORCENTAJE = 0.02


async def obtener_nombre_pagador(client: httpx.AsyncClient, payer_id: str) -> str:
    """
    Intenta obtener el nombre del titular de la cuenta a partir del payer_id.
    Si no puede, devuelve None para que el llamador use el email como fallback.
    """
    if not payer_id:
        return None
    try:
        headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
        response = await client.get(
            f"{MP_API_BASE}/v4/users/{payer_id}",
            headers=headers,
            timeout=5.0,
        )
        if response.status_code == 200:
            data = response.json()
            # Intentar nombre completo, luego first_name + last_name, luego nickname
            nombre = data.get("full_name") or data.get("name")
            if not nombre:
                first = data.get("first_name", "")
                last = data.get("last_name", "")
                nombre = f"{first} {last}".strip()
            if not nombre:
                nombre = data.get("nickname")
            return nombre if nombre else None
        else:
            logger.warning(f"No se pudo obtener nombre del pagador {payer_id}: {response.status_code}")
            return None
    except Exception as e:
        logger.warning(f"Error al obtener nombre del pagador: {e}")
        return None


async def buscar_pago_reciente(
    monto: float | None = None,
    ventana_minutos: int = 20,
    modo_lista: bool = False,
    max_resultados: int = 5,
) -> dict:
    """
    Consulta la API de Mercado Pago buscando pagos aprobados recientes.
    Intenta obtener el nombre del titular como identificador del pagador.
    """
    if not MP_ACCESS_TOKEN:
        raise EnvironmentError("MP_ACCESS_TOKEN no está configurado en las variables de entorno.")

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

    logger.info(f"Consultando MP API | monto={monto} | ventana={ventana_minutos}min | lista={modo_lista}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{MP_API_BASE}/v1/payments/search",
            params=params,
            headers=headers,
        )

        if response.status_code != 200:
            logger.error(f"Error MP API: {response.status_code} - {response.text}")
            raise Exception(f"Error al consultar Mercado Pago: {response.status_code}")

        data = response.json()
        pagos = data.get("results", [])

        logger.info(f"Pagos encontrados en ventana: {len(pagos)}")

        # --- Enriquecer pagos con nombre del titular ---
        for pago in pagos[:max_resultados]:
            payer_id = str(pago.get("payer", {}).get("id", ""))
            nombre = await obtener_nombre_pagador(client, payer_id)
            # Guardamos el nombre en el pago para usarlo al formatear
            pago["_nombre_pagador"] = nombre

        # --- Modo lista ---
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

        # --- Sin monto: devolver el más reciente ---
        if monto is None:
            return {"encontrado": True, "pago": pagos[0], "pagos": [], "ventana_minutos": ventana_minutos, "modo_lista": False}

        # --- Con monto: buscar con tolerancia del 2% ---
        for pago in pagos:
            monto_pago = float(pago.get("transaction_amount", 0))
            diferencia = abs(monto_pago - monto) / monto if monto > 0 else 1
            if diferencia <= TOLERANCIA_PORCENTAJE:
                logger.info(f"Match encontrado: ${monto_pago} para consulta ${monto}")
                return {"encontrado": True, "pago": pago, "pagos": [], "ventana_minutos": ventana_minutos, "modo_lista": False}

        return {"encontrado": False, "pago": None, "pagos": [], "ventana_minutos": ventana_minutos, "modo_lista": False}