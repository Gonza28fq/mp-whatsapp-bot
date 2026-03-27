import re
import logging

logger = logging.getLogger(__name__)

# Ventana default ampliada a 20 minutos
VENTANA_DEFAULT = 20

# Frases que activan consulta general (sin monto)
FRASES_CONSULTA_GENERAL = [
    "entró", "entro", "llegó", "llego", "impactó", "impacto",
    "hubo pago", "hay pago", "pago reciente", "ultimo pago", "último pago",
    "verificar", "check", "confirmar", "corroborar", "fijate", "fijá",
    "entro algo", "entró algo", "llego algo", "llegó algo",
    "se acreditó", "se acredito", "acreditó", "acredito",
    "transfirieron", "hicieron una transferencia", "mandaron",
    "pago el cliente", "pagó el cliente", "cobré", "cobre",
    "hay algo", "entro plata", "entró plata", "llego plata", "llegó plata",
]

# Frases que piden ver los últimos N pagos
FRASES_ULTIMOS_PAGOS = [
    "ultimos pagos", "últimos pagos", "ultimo pagos", "último pagos",
    "pagos recientes", "que pagos hubo", "qué pagos hubo",
    "mostrar pagos", "ver pagos", "listar pagos",
    "cuantos pagos", "cuántos pagos", "pagos de hoy",
    "ultimos", "últimos",  # cubre "últimos 4 pagos", "últimos 3", etc.
]


def parsear_mensaje(texto: str) -> tuple[float | None, int, bool]:
    """
    Parsea el mensaje del empleado para extraer:
    - monto (si lo especificó)
    - ventana de tiempo en minutos (default: 20)
    - modo_lista: True si pide ver los últimos pagos
    """
    texto_lower = texto.lower().strip()

    # --- Detectar si pide lista de últimos pagos ---
    if any(frase in texto_lower for frase in FRASES_ULTIMOS_PAGOS):
        # Detectar si especifica cantidad: "últimos 4 pagos" → max_resultados=4
        match_n = re.search(r"(?:ultimos|últimos)\s+(\d+)", texto_lower)
        n = int(match_n.group(1)) if match_n else 5
        n = max(1, min(n, 10))  # clamp entre 1 y 10
        logger.info(f"Modo lista de pagos detectado | n={n}")
        return None, 60, True, n

    # --- Extraer ventana de tiempo si la especifica ---
    ventana_minutos = VENTANA_DEFAULT
    match_tiempo = re.search(r"hace\s+(\d+)", texto_lower)
    if match_tiempo:
        ventana_minutos = int(match_tiempo.group(1))
        ventana_minutos = max(1, min(ventana_minutos, 120))

    # --- Extraer monto ---
    patron_monto = re.search(
        r"\$?\s*(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{4,}(?:[.,]\d{1,2})?|\d{1,3}(?:[.,]\d{1,2})?(?=\D|$))",
        texto
    )

    if patron_monto:
        monto_str = patron_monto.group(1)
        monto = normalizar_monto(monto_str)
        if monto and monto > 0:
            logger.info(f"Monto parseado: ${monto} | ventana: {ventana_minutos}min")
            return monto, ventana_minutos, False, 5

    logger.info(f"Consulta general detectada | ventana: {ventana_minutos}min")
    return None, ventana_minutos, False, 5


def normalizar_monto(monto_str: str) -> float | None:
    try:
        s = monto_str.replace(" ", "")
        if re.match(r"^\d{1,3}(\.\d{3})+(,\d{1,2})?$", s):
            s = s.replace(".", "").replace(",", ".")
        elif re.match(r"^\d{1,3}(,\d{3})+(\.\d{1,2})?$", s):
            s = s.replace(",", "")
        elif re.match(r"^\d+(,\d{1,2})$", s):
            s = s.replace(",", ".")
        return float(s)
    except (ValueError, AttributeError):
        return None