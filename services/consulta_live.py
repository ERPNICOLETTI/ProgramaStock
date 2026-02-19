import os
import shutil
import dbf
import time
from datetime import datetime

# ==========================================
# CONFIGURACIÓN
# ==========================================
# RUTA DE RED (SERVIDOR) - Apunta al corazón del sistema
RUTA_ORIGINAL = r"\\servidor\sistema\VENTAS\SETART.DBF" 

# RUTA TEMPORAL LOCAL (Donde trabajamos seguros sin molestar a nadie)
RUTA_TEMP_BASE = r"C:\Users\Usuario\Desktop\ERP-PINO\temp_live_"

def buscar_stock_live(termino_busqueda):
    """
    1. Trae una copia del DBF del servidor a local (Snapshot).
    2. Busca por SKU o Descripción.
    3. Calcula Precio Final usando INVP02 + IVA.
    """
    if not termino_busqueda: return {"success": False, "error": "Búsqueda vacía"}
    
    termino = str(termino_busqueda).strip().upper()
    palabras = termino.split()
    timestamp = int(time.time() * 1000)
    ruta_temp = f"{RUTA_TEMP_BASE}{timestamp}.dbf"
    
    # 1. COPIA SEGURA DESDE LA RED
    copiado_ok = False
    for i in range(3):
        try:
            shutil.copy2(RUTA_ORIGINAL, ruta_temp)
            copiado_ok = True
            break
        except PermissionError:
            # Si el servidor está bloqueado, esperamos un poquito
            time.sleep(0.2)
        except Exception:
            # Error de red o no encontrado
            return {"success": False, "error": "Error de Red o Archivo no encontrado"}
            
    if not copiado_ok:
        return {"success": False, "error": "Servidor ocupado o inaccesible."}

    resultados = []
    
    # 2. LECTURA Y CÁLCULO
    try:
        table = dbf.Table(ruta_temp, codepage='cp850')
        table.open(mode=dbf.READ_ONLY)
        
        for record in table:
            sku = str(record.invcod).strip().upper()
            desc = str(record.invnom).strip().upper()
            
            match_sku = all(p in sku for p in palabras)
            match_desc = all(p in desc for p in palabras)

            if match_sku or match_desc:

                
                # --- MAPEO DE STOCK ---
                stock_salon = record.invact or 0   # Salón
                stock_depo = record.invpen or 0    # Depósito
                
                # --- PRECIO CORREGIDO (INVP02) ---
                precio_base = float(record.invp02 or 0) # <--- AHORA USA INVP02
                cod_iva = str(record.inviva).strip()
                
                # --- CÁLCULO IVA ---
                if cod_iva == '01':
                    alicuota = 1.21   # 21%
                elif cod_iva == '02': 
                    alicuota = 1.105  # 10.5%
                else:
                    alicuota = 1.21   # Default
                
                precio_calc = round(precio_base * alicuota, 2)

                centavos = int(round((precio_calc - int(precio_calc)) * 100))

                if centavos in (98, 99):
                    precio_final = int(precio_calc) + 1
                else:
                    precio_final = precio_calc


                item = {
                    "sku": sku,
                    "descripcion": desc,
                    "stock_salon": stock_salon,
                    "stock_depo": stock_depo,
                    "precio_final": precio_final
                }
                
                if sku == termino:
                    resultados.insert(0, item)
                else:
                    resultados.append(item)
                
                if len(resultados) >= 50:
                    break
        
        table.close()
        
    except Exception as e:
        return {"success": False, "error": f"Error leyendo datos: {str(e)}"}
    finally:
        # 3. LIMPIEZA (Borramos la copia local)
        if os.path.exists(ruta_temp):
            try: os.remove(ruta_temp)
            except: pass

    return {"success": True, "resultados": resultados}