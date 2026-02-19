import os
import time
import json
import requests
from datetime import datetime, timedelta
from flask import Blueprint, redirect, current_app, flash, request
from werkzeug.utils import secure_filename
from database import db
from models.orden import Orden, Item, ProductoMaestro, MeliToken

meli_bp = Blueprint('meli', __name__)

MELI_API_URL = "https://api.mercadolibre.com"
TOKEN_JSON_PATH = r"C:\Users\Usuario\Desktop\ERP-PINO\Stock ML\tokens.json"

# Estados válidos para descargar etiqueta
PRINTABLE_STATUSES = {"handling", "ready_to_ship", "ready_to_print"}
EXCLUDED_LOGISTICS = {"fulfillment"}

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}

def get_valid_token(force_refresh=False):
    token_db = MeliToken.query.first()
    if not token_db: return None
    
    if force_refresh or (token_db.expires_at and token_db.expires_at < datetime.now() + timedelta(minutes=20)):
        return refresh_token_flow(token_db)
    return token_db.access_token

def refresh_token_flow(token_db):
    print("🔄 [MeLi] Renovando token...")
    app_id = current_app.config.get('MELI_APP_ID')
    secret = current_app.config.get('MELI_SECRET_KEY')
    
    payload = {
        "grant_type": "refresh_token",
        "client_id": app_id,
        "client_secret": secret,
        "refresh_token": token_db.refresh_token
    }
    
    try:
        r = requests.post(f"{MELI_API_URL}/oauth/token", data=payload, headers=BASE_HEADERS)
        if r.status_code == 200:
            data = r.json()
            
            token_db.access_token = data['access_token']
            token_db.refresh_token = data.get('refresh_token', token_db.refresh_token)
            token_db.expires_at = datetime.now() + timedelta(seconds=data.get('expires_in', 21600))
            db.session.commit()
            
            try:
                json_data = {
                    "access_token": token_db.access_token,
                    "refresh_token": token_db.refresh_token,
                    "client_id": app_id,
                    "client_secret": secret,
                    "expires_at": int(token_db.expires_at.timestamp()),
                    "user_id": token_db.user_id,
                    "token_type": "Bearer"
                }
                with open(TOKEN_JSON_PATH, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=4)
                print("✅ tokens.json actualizado")
            except Exception as e:
                print(f"⚠️ Error JSON: {e}")

            return token_db.access_token
        else:
            print(f"❌ Error renovando: {r.text}")
    except Exception as e:
        print(f"❌ Error conexión: {e}")
    return None

def descargar_etiqueta_segura(shipment_id, access_token):
    """
    Descarga etiqueta de forma SEGURA.
    REGLAS CRÍTICAS:
    - Solo llamar si status está en PRINTABLE_STATUSES
    - Si 403: NO reintentar, devolver None
    - Si 401: renovar token 1 sola vez
    """
    url = f"{MELI_API_URL}/shipment_labels"
    params = {"shipment_ids": shipment_id, "response_type": "pdf"}
    headers = BASE_HEADERS.copy()
    headers["Authorization"] = f"Bearer {access_token}"
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        
        # ÉXITO
        if r.status_code == 200:
            filename = f"etiqueta_{shipment_id}.pdf"
            folder = os.path.join(current_app.root_path, 'static', 'etiquetas')
            os.makedirs(folder, exist_ok=True)
            filepath = os.path.join(folder, filename)
            
            with open(filepath, 'wb') as f:
                f.write(r.content)
            
            print(f"✅ Etiqueta descargada: {shipment_id}")
            return f"/static/etiquetas/{filename}"
        
        # PROHIBIDO - NO REINTENTAR
        elif r.status_code == 403:
            print(f"⛔ 403 en {shipment_id} - Bloqueado por MeLi")
            return None
        
        # TOKEN VENCIDO - 1 reintento
        elif r.status_code == 401:
            print(f"⚠️ 401 en {shipment_id} - Renovando token...")
            new_token = get_valid_token(force_refresh=True)
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                r2 = requests.get(url, headers=headers, params=params, timeout=30)
                if r2.status_code == 200:
                    filename = f"etiqueta_{shipment_id}.pdf"
                    folder = os.path.join(current_app.root_path, 'static', 'etiquetas')
                    os.makedirs(folder, exist_ok=True)
                    filepath = os.path.join(folder, filename)
                    
                    with open(filepath, 'wb') as f:
                        f.write(r2.content)
                    
                    print(f"✅ Etiqueta descargada tras renovar: {shipment_id}")
                    return f"/static/etiquetas/{filename}"
            return None
        
        # OTROS ERRORES
        else:
            print(f"⚠️ Error {r.status_code} en {shipment_id}")
            return None
            
    except Exception as e:
        print(f"❌ Excepción descargando {shipment_id}: {e}")
        return None

@meli_bp.route('/sincronizar')
def sincronizar():
    access_token = get_valid_token()
    if not access_token:
        flash('Error de Token', 'danger')
        return redirect('/ordenes/')

    token_db = MeliToken.query.first()
    headers = BASE_HEADERS.copy()
    headers["Authorization"] = f"Bearer {access_token}"
    
    # Ventas de los últimos 7 días
    date_from = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
    
    # --- 1. PAGINACIÓN (Traer 100 sí o sí) ---
    all_orders = []
    limit = 50
    offset = 0
    max_count = 100  # <--- Mantenemos tu requisito de 100

    print(f"🔄 Iniciando Sincronización (Revisando últimas {max_count})...")

    while offset < max_count:
        params = {
            "seller": token_db.user_id,
            "order.status": "paid",
            "sort": "date_desc",
            "order.date_created.from": date_from,
            "limit": limit,
            "offset": offset 
        }
        
        try:
            r = requests.get(f"{MELI_API_URL}/orders/search", headers=headers, params=params)
            if r.status_code != 200:
                print(f"❌ Error API offset {offset}: {r.text}")
                break
                
            results = r.json().get("results", [])
            if not results:
                break 
            
            all_orders.extend(results)
            print(f"   ↳ Lote cargado: {len(results)} ventas (Offset: {offset})")
            
            offset += limit
            time.sleep(0.1)

        except Exception as e:
            print(f"❌ Error conexión: {e}")
            break

    # --- 2. PROCESAMIENTO ---
    shipment_map = {}
    for o in all_orders:
        sid = (o.get("shipping") or {}).get("id")
        if not sid: continue
        sid = str(sid)
        if sid not in shipment_map: shipment_map[sid] = []
        shipment_map[sid].append(o)

    nuevos = 0
    ignorados_full = 0
    ignorados_shipped = 0
    sin_etiqueta = 0
    
    print(f"📦 Procesando {len(shipment_map)} envíos únicos...")

    for sid, orders in shipment_map.items():
        try:
            # A. Chequeo si ya existe
            existing_order = Orden.query.filter_by(meli_shipment_id=sid).first()
            if existing_order and existing_order.etiqueta_url:
                continue

            # B. Consultamos API Envíos
            r_ship = requests.get(f"{MELI_API_URL}/shipments/{sid}", headers=headers)
            if r_ship.status_code != 200: continue
            
            shp_data = r_ship.json()
            logistic = str(shp_data.get("logistic_type", "")).lower()
            status = str(shp_data.get("status", "")).lower()

            # --- FILTROS (LO QUE PEDISTE) ---
            
            # 1. Ignorar FULL
            if logistic == 'fulfillment':
                ignorados_full += 1
                continue 

            # 2. Ignorar YA DESPACHADOS (Nuevo: evita importar cosas viejas)
            if status in ['shipped', 'delivered', 'cancelled']:
                ignorados_shipped += 1
                continue

            # Definimos estados seguros para descargar etiqueta
            # Aceptamos ready_to_print Y ready_to_ship (SOLUCIÓN A TU PROBLEMA DE ETIQUETAS)
            ESTADOS_DESCARGA = ['ready_to_print', 'ready_to_ship']

            # C. ACTUALIZACIÓN (Orden existe pero le falta etiqueta)
            if existing_order:
                if status in ESTADOS_DESCARGA:
                    print(f"🔄 Actualizando etiqueta orden {sid}...")
                    url = descargar_etiqueta_segura(sid, access_token)
                    if url:
                        existing_order.etiqueta_url = url
                        db.session.commit()
                continue

            # D. NUEVAS ÓRDENES (Solo Pendientes de Despacho)
            etiqueta_url = None
            
            # Acá es donde antes fallaba: ahora aceptamos ready_to_ship
            if status in ESTADOS_DESCARGA:
                print(f"✅ Descargando etiqueta {sid} ({status})...")
                etiqueta_url = descargar_etiqueta_segura(sid, access_token)
            else:
                print(f"🛡️ Importando {sid} SIN etiqueta (Estado: {status})")
                sin_etiqueta += 1

            # E. Crear Orden
            first = orders[0]
            buyer = first.get('buyer', {})
            nombre = f"{buyer.get('first_name','')} {buyer.get('last_name','')}".strip() or buyer.get('nickname', 'Cliente')
            
            nueva_orden = Orden(
                numero_orden=str(first['id']),
                origen='MELI',
                estado='PENDIENTE',
                cliente_nombre=nombre,
                meli_shipment_id=sid,
                meli_order_id=str(first['id']),
                etiqueta_url=etiqueta_url,
                fecha_creacion=datetime.now()
            )
            db.session.add(nueva_orden)
            db.session.flush()

            # F. Guardar Ítems
            for o in orders:
                for it in o.get('order_items', []):
                    item_data = it.get('item', {})
                    sku = item_data.get('seller_custom_field') or item_data.get('seller_sku') or item_data.get('id')
                    titulo = item_data.get('title', '')
                    qty = int(it.get('quantity', 1))

                    prod = ProductoMaestro.query.filter_by(sku=sku).first()
                    if not prod:
                        prod = ProductoMaestro(sku=sku, descripcion=titulo)
                        db.session.add(prod)
                        db.session.flush()

                    db.session.add(Item(
                        orden_id=nueva_orden.id,
                        sku=sku,
                        descripcion=titulo,
                        cantidad_pedida=qty
                    ))
            
            nuevos += 1

        except Exception as e:
            print(f"❌ Error procesando {sid}: {e}")

    db.session.commit()
    
    msg = f"Sincronización: {nuevos} nuevas."
    if sin_etiqueta > 0: msg += f" (⚠️ {sin_etiqueta} sin etiqueta)"
    
    flash(msg, 'success' if nuevos > 0 else 'warning')
    return redirect('/ordenes/')


# BONUS: Subida manual para casos de 403
@meli_bp.route('/orden/<int:id>/subir_etiqueta', methods=['POST'])
def subir_etiqueta(id):
    orden = Orden.query.get_or_404(id)
    
    if 'etiqueta' not in request.files:
        flash('No se seleccionó archivo', 'danger')
        return redirect(f'/ordenes/{id}')
    
    file = request.files['etiqueta']
    
    if not file.filename.lower().endswith('.pdf'):
        flash('Solo PDF', 'danger')
        return redirect(f'/ordenes/{id}')
    
    filename = f"etiqueta_{orden.meli_shipment_id}.pdf"
    folder = os.path.join(current_app.root_path, 'static', 'etiquetas')
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    
    file.save(filepath)
    orden.etiqueta_url = f"/static/etiquetas/{filename}"
    db.session.commit()
    
    flash('✅ Etiqueta subida', 'success')
    return redirect(f'/ordenes/{id}')