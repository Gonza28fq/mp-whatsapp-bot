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

def extraer_datos_pagador(pago: dict) -> dict:
    """
    Extrae Nombre, Email e Identificación buscando en todos los 
    recovecos de la API de Mercado Pago.
    """
    payer = pago.get("payer") or {}
    poi = pago.get("point_of_interaction") or {}
    transaction_data = poi.get("transaction_data") or {}
    
    # 1. Intentar buscar NOMBRE en el objeto de transferencia (CVU/SBU)
    nombre = (
        transaction_data.get("transefer_name") or 
        transaction_data.get("transfer_name") or 
        transaction_data.get("buyer_declaration")
    )
    
    # 2. Si no hay nombre en la transferencia, buscar en el perfil del Payer
    if not nombre:
        first = (payer.get("first_name") or "").strip()
        last = (payer.get("last_name") or "").strip()
        if first or last:
            nombre = f"{first} {last}".strip()
    
    # 3. Extraer el EMAIL (Dato clave que pediste adjuntar)
    email = (payer.get("email") or "").strip()
    
    # 4. FALLBACK: Si sigue sin haber nombre, usar ID o DNI
    if not nombre:
        ident = payer.get("identification") or {}
        id_num = str(ident.get("number") or "").strip()
        if id_num and id_num not in ["0", "", "None"]:
            nombre = f"ID: {id_num}"
        else:
            nombre = f"Usuario MP ({payer.get('id', 'S/D')})"
        
    return {
        "nombre": nombre.title() if "Usuario MP" not in nombre else nombre,
        "email": email if email else "sin email"
    }


async def buscar_pago_reciente(
    monto: float | None = None,
    ventana_minutos: int = 20,
    modo_lista: bool = False,
    max_resultados: int = 5,
) -> dict:
    if not MP_ACCESS_TOKEN:
        raise EnvironmentError("MP_ACCESS_TOKEN no está configurado.")

    # Manejo de tiempo robusto para evitar desfases con Railway/MP
    ahora = datetime.now(timezone.utc)
    desde = ahora - timedelta(minutes=ventana_minutos)
    desde_str = desde.isoformat(timespec='milliseconds')

    params = {
        "sort": "date_approved",
        "criteria": "desc",
        "begin_date": desde_str,
        "end_date": "NOW",
        "status": "approved",
    }

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    logger.info(f"Consultando MP | monto={monto} | ventana={ventana_minutos}min")

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
            logger.error(f"Error en API MP: {e}")
            return {"encontrado": False, "pago": None, "pagos": [], "error": str(e)}

        pagos_raw = data.get("results", [])
        pagos_procesados = []

        for p in pagos_raw:
            # Enriquecemos el objeto con los datos limpios
            datos_p = extraer_datos_pagador(p)
            p["_nombre_pagador"] = datos_p["nombre"]
            p["_email_pagador"] = datos_p["email"]
            p["_hora_arg"] = formatear_hora_arg(p.get("date_approved", ""))
            
            monto_actual = float(p.get("transaction_amount", 0))
            p["_monto_limpio"] = monto_actual

            # Lógica de filtrado por monto
            if monto:
                diferencia = abs(monto_actual - monto) / monto if monto > 0 else 1
                if diferencia <= TOLERANCIA_PORCENTAJE:
                    pagos_procesados.append(p)
                    if not modo_lista: break
            else:
                pagos_procesados.append(p)

        # Retorno consistente para tu main.py
        return {
            "encontrado": len(pagos_procesados) > 0,
            "pago": pagos_procesados[0] if pagos_procesados else None,
            "pagos": pagos_procesados[:max_resultados],
            "ventana_minutos": ventana_minutos,
            "modo_lista": modo_lista
        }