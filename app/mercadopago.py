import httpx
import os
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MP_API_BASE = "https://api.mercadopago.com"

# Tolerancia ampliada al 2% para cubrir redondeos y montos con centavos
TOLERANCIA_PORCENTAJE = 0.02


async def buscar_pago_reciente(
    monto: float | None = None,
    ventana_minutos: int = 20,
    modo_lista: bool = False,
    max_resultados: int = 5,
) -> dict:
    """
    Consulta la API de Mercado Pago buscando pagos aprobados recientes.

    Args:
        monto: Si se especifica, filtra por ese monto (con tolerancia del 2%).
        ventana_minutos: Cuántos minutos hacia atrás buscar.
        modo_lista: Si True, devuelve los últimos N pagos sin filtrar por monto.
        max_resultados: Máximo de pagos a mostrar en modo lista.

    Returns:
        {"encontrado": bool, "pago": dict | None, "pagos": list, 
         "ventana_minutos": int, "modo_lista": bool}
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

    # --- Modo lista: devolver los últimos N pagos ---
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

    logger.info(f"No se encontró pago de ${monto} en los últimos {ventana_minutos} min")
    return {"encontrado": False, "pago": None, "pagos": [], "ventana_minutos": ventana_minutos, "modo_lista": False}