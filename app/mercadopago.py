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
        # Mercado Pago suele enviar: 2024-03-27T15:48:10.000-04:00
        # Usamos fromisoformat para manejar offsets correctamente
        dt = datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
        dt_arg = dt.astimezone(timezone(ARG_OFFSET))
        return dt_arg.strftime("%d/%m %H:%M")
    except Exception as e:
        logger.error(f"Error formateando fecha {fecha_str}: {e}")
        return fecha_str[:16].replace("T", " ")

def extraer_identificador_pagador(pago: dict) -> str:
    """
    Extrae el mejor identificador posible del pagador.
    Se añade búsqueda en point_of_interaction para transferencias.
    """
    payer = pago.get("payer") or {}
    
    # 1. Intentar obtener nombre de transaction_details (común en transferencias)
    details = pago.get("transaction_details") or {}
    external_resource = details.get("external_resource_url") # A veces ayuda a identificar el origen
    
    # 2. Nombre directo en payer
    first = (payer.get("first_name") or "").strip()
    last = (payer.get("last_name") or "").strip()
    if first or last:
        return f"{first} {last}".strip()

    # 3. Datos de identificación (DNI/CUIT) - Validando que no sea "0"
    ident = payer.get("identification") or {}
    id_num = str(ident.get("number") or "").strip()
    if id_num and id_num not in ["0", "", "None"]:
        id_type = ident.get("type") or "ID"
        return f"{id_type}: {id_num}"

    # 4. Email (Suele ser lo más confiable si no hay nombre)
    email = (payer.get("email") or "").strip()
    if email and "@" in email:
        return email

    # 5. Metadata o campos adicionales de MP
    # Si es una transferencia, el nombre a veces viene en 'description' o 'metadata'
    description = pago.get("description") or ""
    if "Transferencia de" in description:
        return description.replace("Transferencia de", "").strip()

    return "Usuario MP (ID: " + str(payer.get("id", "S/D")) + ")"

async def buscar_pago_reciente(
    monto: float | None = None,
    ventana_minutos: int = 20,
    modo_lista: bool = False,
    max_resultados: int = 5,
) -> dict:
    if not MP_ACCESS_TOKEN:
        raise EnvironmentError("MP_ACCESS_TOKEN no está configurado.")

    # Ajuste de tiempo: MP usa ISO 8601
    ahora = datetime.now(timezone.utc)
    desde = ahora - timedelta(minutes=ventana_minutos)
    # Formato aceptado por MP: 2024-03-27T10:00:00.000-00:00
    desde_str = desde.isoformat(timespec='milliseconds')

    params = {
        "sort": "date_approved", # Ordenar por aprobación es más preciso para tu caso
        "criteria": "desc",
        "begin_date": desde_str,
        "end_date": "NOW",
        "status": "approved",
    }

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                f"{MP_API_BASE}/v1/payments/search",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Error conectando a MP: {e}")
            return {"encontrado": False, "pago": None, "pagos": [], "error": str(e)}

        pagos_raw = data.get("results", [])
        pagos_procesados = []

        for p in pagos_raw[:10]: # Analizamos un poco más de los que mostramos por si hay filtros
            p["_nombre_pagador"] = extraer_identificador_pagador(p)
            p["_hora_arg"] = formatear_hora_arg(p.get("date_approved"))
            p["_email_pagador"] = p.get("payer", {}).get("email", "Sin email")
            p["_monto_limpio"] = float(p.get("transaction_amount", 0))
            
            # Filtro por monto si no es modo lista
            if monto:
                diferencia = abs(p["_monto_limpio"] - monto) / monto if monto > 0 else 1
                if diferencia <= TOLERANCIA_PORCENTAJE:
                    pagos_procesados.append(p)
                    if not modo_lista: break # Encontramos el que buscábamos
            else:
                pagos_procesados.append(p)

        return {
            "encontrado": len(pagos_procesados) > 0,
            "pago": pagos_procesados[0] if pagos_procesados else None,
            "pagos": pagos_procesados[:max_resultados],
            "ventana_minutos": ventana_minutos,
            "modo_lista": modo_lista
        }