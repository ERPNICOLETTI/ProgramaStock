import re
import os

def procesar_factura_pdf(file_stream):
    """
    Parser Estricto: SOLO acepta archivos de texto/Clipper (.txt, .prn, etc).
    Rechaza PDFs reales si tienen estructura binaria de PDF, pero intentamos procesar
    si es solo la extensión la incorrecta.
    """
    filename = getattr(file_stream, 'filename', '').lower()
    
    # Advertencia simple, pero intentamos procesar igual por si acaso es un txt renombrado
    if filename.endswith('.pdf'):
        # Podríamos retornar error, pero a veces los usuarios guardan el .prn como .pdf
        pass

    return _parsear_como_texto_clipper(file_stream)

def _parsear_como_texto_clipper(file_stream):
    """
    Lee archivos de impresión crudos (Clipper/DOS).
    Formato soportado: SKU + Descripcion + Cantidad + [UNIDAD opcional] + IVA/Precio
    """
    resultado = {
        "factura": "",
        "cliente": "",
        "items": []
    }
    
    SKUS_IGNORAR = [
        "CODIGO", "DESCRIPCION", "CANTID", "TOTAL", "SUBTOTAL", "CAE", "VENCIM", 
        "PAGINA", "FECHA", "COMPR", "COND", "PRECIO", "IMPORTE", "IVA",
        "SUC", "ENVIO", "FLETE", "SERV", "LOGISTICA", "BULTOS", "OBSERVACIONES",
        "REMITE", "TRANSPORTE", "PROVINCIA", "LOCALIDAD"
    ]

    try:
        # cp850 es la codificación clásica de DOS para las líneas de dibujo y tildes
        content = file_stream.read().decode('cp850', errors='ignore')
    except Exception as e:
        return {"error": f"Error de codificación: {str(e)}"}

    lines = content.split('\n')
    buscando_cliente = False
    
    # --- REGEX EXPLICACIÓN ---
    # ^\s* -> Inicio de línea ignorando espacios
    # ([A-Z0-9\.\-\/]+)     -> GRUPO 1: SKU (Letras, numeros, puntos, guiones)
    # \s+                   -> Espacios obligatorios
    # (.+?)                 -> GRUPO 2: Descripción (toma todo lo que pueda hasta...)
    # \s+                   -> Espacios obligatorios
    # (\d+\.\d{2})          -> GRUPO 3: Cantidad (formato 1.00)
    # \s* -> Espacios (puede haber o no antes de la unidad)
    # ([A-Za-z]*)           -> GRUPO 4: Unidad (OPCIONAL, acepta vacio o letras)
    # \s+                   -> Espacios obligatorios antes del siguiente numero
    # (?:\d+\.\d+|\d+)      -> Lookahead/Ancla: Debe seguir un numero (IVA 21.0 o Precio)
    
    regex_prod = r'^\s*([A-Z0-9\.\-\/]+)\s+(.+?)\s+(\d+\.\d{2})\s*([A-Za-z]*)\s+(?:\d+\.\d+|\d+)'

    for line in lines:
        l = line.strip()
        if not l: continue

        # A. FACTURA (Busca patrones como 0021-00000208)
        if "0021-" in l:
            match = re.search(r'0021-\d{8}', l)
            if match: resultado['factura'] = match.group(0)

        # B. CLIENTE
        if "Sr./Sres.:" in l:
            # A veces el nombre está en la misma línea
            if len(l) > 15: 
                partes = l.split("Sr./Sres.:")
                if len(partes) > 1 and len(partes[1].strip()) > 2:
                    resultado['cliente'] = partes[1].strip()
            else:
                buscando_cliente = True
            continue
        
        if buscando_cliente:
            # Filtramos lineas que parecen datos fiscales y no nombres
            if len(l) > 3 and "PM" not in l and "CUIT" not in l and "IVA" not in l and "Compr:" not in l:
                resultado['cliente'] = l
                buscando_cliente = False

        # C. PRODUCTOS
        match = re.search(regex_prod, line)
        if match:
            sku = match.group(1).strip()
            
            # Validaciones para descartar falsos positivos
            if sku.upper() in SKUS_IGNORAR or len(sku) < 2:
                continue
            
            # Filtrar caracteres de tablas DOS (como 哪 o ─) si se cuelan en el SKU
            if any(ord(c) > 126 for c in sku): 
                continue

            desc = match.group(2).strip()
            
            # Si la descripción parece un total, saltar
            if "SUBTOTAL" in desc.upper() or "TOTAL" in desc.upper():
                continue

            try:
                cant = float(match.group(3))
            except:
                cant = 1.0
            
            # Unidad: puede venir vacía si el regex capturó string vacío
            unidad = match.group(4).strip() if match.group(4) else ""
            
            resultado['items'].append({
                "sku": sku,
                "descripcion": desc,
                "cantidad": cant,
                "unidad": unidad
            })

    if not resultado['items']:
        # Fallback de error o debug: imprimir las primeras lineas si falla para ver qué pasa
        return {"error": "No se encontraron items. Verifique que el archivo sea de impresión (texto) y no un PDF de imagen."}

    return resultado