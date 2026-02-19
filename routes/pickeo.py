from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from database import db
from models.orden import Orden, Item, ProductoMaestro, ProductoCodigo
from datetime import datetime
import os
import requests
import subprocess
from werkzeug.utils import secure_filename
from services.clipper_service import agregar_al_maestro, obtener_codigo_cliente, generar_id_unico
from models.orden import Movimiento
from routes.egresos import ejecutar_egreso_automatico
import json


bp = Blueprint('pickeo', __name__, url_prefix='/pickeo')

# --- VISTA PRINCIPAL DEL PICKEO ---
@bp.route('/orden/<int:orden_id>')
def vista_pickeo(orden_id):
    orden = Orden.query.get_or_404(orden_id)
    return render_template('pickeo.html', orden=orden)

# --- ESCANEO / AGREGAR ITEM CON SOPORTE DE VINCULACIÓN ---
@bp.route('/agregar-item-manual', methods=['POST'])
def agregar_item_manual():
    data = request.json
    orden_id = data.get('orden_id')
    sku_scaneado = data.get('sku').strip().upper()

    orden = Orden.query.get(orden_id)
    if not orden: return jsonify({'success': False, 'error': 'Orden no encontrada'})
    
    # 1. Buscar si es un SKU principal
    item = Item.query.filter_by(orden_id=orden_id, sku=sku_scaneado).first()

    # 2. Si no es SKU principal, buscar en códigos alternativos (Alias)
    if not item:
        codigo_alt = ProductoCodigo.query.filter_by(codigo_barra=sku_scaneado).first()
        if codigo_alt:
            item = Item.query.filter_by(orden_id=orden_id, sku=codigo_alt.sku).first()

    # 3. NO ENCONTRADO -> DEVOLVER ERROR ESPECIAL
    if not item:
        return jsonify({
            'success': False, 
            'error_code': 'UNKNOWN_BARCODE', 
            'scanned_code': sku_scaneado,
            'error': f'Código desconocido: {sku_scaneado}'
        })

    # 4. VALIDACIÓN DE EXCESO
    if item.cantidad_pickeada >= item.cantidad_pedida:
        return jsonify({'success': False, 'error': f'¡EXCESO! Ya tienes {item.cantidad_pickeada} de {item.cantidad_pedida}.'})

    # 5. GUARDAR
    item.cantidad_pickeada += 1
    db.session.commit()
    # AGREGADO: devolvemos item.sku para que el frontend sepa cuál fila mover
    return jsonify({'success': True, 'mensaje': 'Agregado.', 'sku_real': item.sku})

# --- VINCULAR CÓDIGO NUEVO Y AGREGAR (Auto-aprendizaje) ---
@bp.route('/vincular-y-agregar', methods=['POST'])
def vincular_y_agregar():
    data = request.json
    orden_id = data.get('orden_id')
    codigo_nuevo = data.get('codigo_nuevo', '').strip().upper()
    sku_target = data.get('sku_target', '').strip().upper()

    if not codigo_nuevo or not sku_target:
        return jsonify({'success': False, 'error': 'Faltan datos para vincular'})

    # 1. Validar que el SKU objetivo realmente exista en la orden
    item = Item.query.filter_by(orden_id=orden_id, sku=sku_target).first()
    if not item:
         return jsonify({'success': False, 'error': f'El SKU {sku_target} no pertenece a esta orden.'})

    # 2. Guardar el nuevo vínculo
    try:
        existe = ProductoCodigo.query.get(codigo_nuevo)
        if not existe:
            nuevo_vinculo = ProductoCodigo(codigo_barra=codigo_nuevo, sku=sku_target)
            db.session.add(nuevo_vinculo)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error al vincular: {str(e)}'})

    # 3. Sumar Stock (Lógica de agregado)
    if item.cantidad_pickeada >= item.cantidad_pedida:
        return jsonify({'success': False, 'error': f'Vinculado OK, pero orden llena.'})

    item.cantidad_pickeada += 1
    db.session.commit()
    
    return jsonify({'success': True, 'mensaje': f'¡Vinculado a {sku_target} y sumado!'})

@bp.route('/subir-etiqueta', methods=['POST'])
def subir_etiqueta():
    if 'etiqueta' not in request.files:
        return jsonify({'success': False, 'error': 'No se recibió archivo'})
    
    file = request.files['etiqueta']
    orden_id = request.form.get('orden_id')
    orden = Orden.query.get(orden_id)
    
    if file and orden:
        filename = f"etiqueta_manual_{orden_id}.pdf"
        folder = os.path.join(current_app.root_path, 'static', 'docs')
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, filename)
        file.save(path)
        orden.etiqueta_path = f"/static/docs/{filename}"
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Error al guardar archivo o ID de orden'})

# --- BORRAR ITEM DEL PICKEO ---
@bp.route('/borrar-item', methods=['POST'])
def borrar_item():
    data = request.json
    orden_id = data.get('orden_id')
    sku = data.get('sku')
    
    item = Item.query.filter_by(orden_id=orden_id, sku=sku).first()
    if item:
        item.cantidad_pickeada = 0
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Item no encontrado'})

# --- GUARDAR DATOS PAQUETE (PESO/DIMENSIONES) ---
@bp.route('/guardar-datos-paquete', methods=['POST'])
def guardar_datos_paquete():
    data = request.json
    orden_id = data.get('orden_id')
    
    orden = Orden.query.get(orden_id)
    if not orden:
        return jsonify({'success': False, 'error': 'Orden no encontrada'})

    try:
        orden.peso = float(data.get('peso', 0))
        orden.largo = float(data.get('largo', 0))
        orden.ancho = float(data.get('ancho', 0))
        orden.alto = float(data.get('alto', 0))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
    # --- NUEVA RUTA: ENVIAR MEDIDAS A ADMIN ---
# --- ENVIAR MEDIDAS A ADMIN (Soporte Multi-Bulto) ---
@bp.route('/enviar-medidas-admin', methods=['POST'])
def enviar_medidas_admin():
    data = request.json
    orden_id = data.get('orden_id')
    paquetes = data.get('paquetes', []) # Lista de bultos nueva
    
    orden = Orden.query.get(orden_id)
    if not orden:
        return jsonify({'success': False, 'error': 'Orden no encontrada'})

    try:
        # Si viene del sistema viejo (sin lista), creamos una lista falsa con 1 bulto
        if not paquetes:
            peso = float(data.get('peso', 0))
            if peso > 0:
                paquetes = [{
                    'peso': peso,
                    'largo': float(data.get('largo', 0)),
                    'ancho': float(data.get('ancho', 0)),
                    'alto': float(data.get('alto', 0))
                }]
        
        # 1. TRUCO: Guardamos la lista JSON en 'observaciones'
        if paquetes:
            orden.observaciones = json.dumps(paquetes)

        # 2. Calcular Totales (Para estadísticas y compatibilidad)
        orden.peso = sum(float(p.get('peso', 0)) for p in paquetes)
        
        # Usamos la medida máxima de los paquetes como referencia
        if paquetes:
            orden.largo = max(float(p.get('largo', 0)) for p in paquetes)
            orden.ancho = max(float(p.get('ancho', 0)) for p in paquetes)
            orden.alto = max(float(p.get('alto', 0)) for p in paquetes)

        # 3. Cambiar Estado
        orden.estado = 'ESPERANDO_ADMIN'
        orden.manual_etapa = 'PREPARACION' 
        
        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# --- CONFIRMAR EMBALADO (FINALIZAR PICKEO) ---
@bp.route('/confirmar-embalado', methods=['POST'])
def confirmar_embalado():
    data = request.json
    orden_id = data.get('orden_id')
    orden = Orden.query.get(orden_id)

    if not orden:
        return jsonify(success=False, error='Orden no encontrada')

    # Validar pickeo completo
    for item in orden.items:
        if item.cantidad_pickeada < item.cantidad_pedida:
            return jsonify(success=False, error=f'Falta completar {item.sku}')

    # Flujo
    if orden.origen == 'MANUAL':
        orden.estado = 'ESPERANDO_ADMIN'
        orden.manual_etapa = 'PREPARACION'
    else:
        orden.estado = 'LISTO_DESPACHO'

    db.session.commit()
    return jsonify(success=True)


# ==============================================================================
# CONFIRMAR DESPACHO FINAL (LOGICA DE COLAS SEPARADAS)
# ==============================================================================
@bp.route('/confirmar-despacho-final', methods=['POST'])
def confirmar_despacho_final():
    data = request.get_json(force=True) or {}
    orden_id = data.get('orden_id')
    
    orden = Orden.query.get_or_404(orden_id)
    origen_actual = str(orden.origen).upper().strip()

    # --- 1. GUARDAR EN SQL (BUFFER) ---
    # Detectamos si es una orden que va al sistema Clipper
    es_lote_clipper = origen_actual in ('ML', 'MELI', 'FULL', 'MERCADOLIBRE')
    
    if es_lote_clipper:
        salon_map = data.get("salon", {}) or {}

        for item in orden.items:
            total = item.cantidad_pickeada
            cant_salon = int(salon_map.get(item.sku, 0))
            cant_salon = max(0, min(cant_salon, total))
            cant_depo = total - cant_salon

            if cant_salon > 0:
                db.session.add(
                    Movimiento(
                        orden_id=orden.id,
                        sku=item.sku,
                        cantidad=cant_salon,
                        origen_stock="SALON",
                        fecha=datetime.utcnow()
                    )
                )

            if cant_depo > 0:
                db.session.add(
                    Movimiento(
                        orden_id=orden.id,
                        sku=item.sku,
                        cantidad=cant_depo,
                        origen_stock="DEPO",
                        fecha=datetime.utcnow()
                    )
                )


    # --- 2. FINALIZAR ORDEN ---
    orden.estado = 'DESPACHADO'
    db.session.commit()

    # --- 3. DETECTOR FIN DE COLA (SEPARADO POR TIPO) ---
    if es_lote_clipper:
        
        # DEFINIR EL GRUPO A CONTROLAR
        if origen_actual == 'FULL':
            # Si acabo de cerrar una FULL, solo me importa si quedan otras FULL
            grupo_a_checkear = ['FULL']
            nombre_cola = "FULL"
        else:
            # Si cerré ML, me fijo si quedan otras de ML (ignorando FULL)
            grupo_a_checkear = ['ML', 'MELI', 'MERCADOLIBRE']
            nombre_cola = "ML ESTANDAR"

        # CONTAR PENDIENTES SOLO DE ESE GRUPO
        pendientes = Orden.query.filter(
            Orden.origen.in_(grupo_a_checkear),
            Orden.estado.in_(['PENDIENTE', 'EN_PREPARACION', 'LISTO_DESPACHO', 'ESPERANDO_ADMIN'])
        ).count()

        print(f">>> [PICKEO] Fin de Cola ({nombre_cola}): Quedan {pendientes}.")

        # SI EL GRUPO ESTÁ VACÍO -> DISPARAR
        if pendientes == 0:
            print(f">>> 🚀 SE ACABÓ LA COLA {nombre_cola}: Disparando sincronización...")
            try:
                # Importante: El script sincronizador_blindado.py ya debe tener
                # la lógica que hicimos antes para diferenciar nombres en el DBF.
                script_path = r"Z:\VENTAS\MOVSTK\sincronizador_blindado.py"
                
                subprocess.Popen(
                    ["python", script_path, "--full"],
                    cwd=os.path.dirname(script_path),
                    shell=True
                )
            except Exception as e:
                print(f"⚠️ Error disparando batch: {e}")
        else:
            print(f">>> Acumulando en buffer {nombre_cola}...")

    return jsonify(success=True)

# --- IMPRESIÓN INDIVIDUAL DE BULTOS (NON-BLOCKING / ASÍNCRONA) ---
@bp.route('/imprimir-archivo', methods=['POST'])
def imprimir_archivo_especifico():
    """Imprime en segundo plano para no congelar la pantalla del operario."""
    import threading # <--- Necesario para el truco de velocidad
    
    # Importar tu servicio de impresión
    from services.etiquetas_ml_service import imprimir_etiqueta_ml 
    
    data = request.json
    url_relativa = data.get('url')
    
    if not url_relativa:
        return jsonify(success=False, error="Falta URL")

    # Validación de ruta
    if url_relativa.startswith('/'):
        url_relativa = url_relativa[1:]
    path_absoluto = os.path.join(current_app.root_path, url_relativa)

    if not os.path.exists(path_absoluto):
        return jsonify(success=False, error="Archivo no encontrado")

    # --- LA MAGIA: FUNCIÓN EN SEGUNDO PLANO ---
    def tarea_impresion_background(path):
        """Esta función corre en paralelo y no frena al usuario"""
        try:
            # Aquí es donde ocurre el 'lag' real de la impresora
            imprimir_etiqueta_ml(path)
            print(f"✅ Impresión finalizada en background: {path}")
        except Exception as e:
            print(f"❌ Error imprimiendo en background: {e}")

    # Lanzamos el hilo y nos olvidamos (Fire & Forget)
    hilo = threading.Thread(target=tarea_impresion_background, args=(path_absoluto,))
    hilo.start()

    # Respondemos AL INSTANTE al usuario, aunque la impresora tarde
    return jsonify({'success': True, 'message': 'Enviado a cola de impresión'})







