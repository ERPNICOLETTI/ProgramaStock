from flask import Blueprint, render_template, request, jsonify
from database import db
from models.orden import Orden, Item, Movimiento, ProductoMaestro, ProductoCodigo
from services.clipper_service import agregar_al_maestro, generar_id_unico
from services.etiquetas_service import generar_etiquetas_termicas
from datetime import datetime
import subprocess
import os

bp = Blueprint('transferencias', __name__, url_prefix='/transferencias')

@bp.route('/')
def index():
    hoy_str = datetime.now().strftime('%Y%m%d')
    numero_ref = f"TR-{hoy_str}" 
    
    # --- CORRECCIÓN AQUÍ ---
    # Antes buscábamos solo 'PENDIENTE'. Si la orden cambiaba de estado (ej. EN_PREPARACION),
    # el sistema no la veía, intentaba crearla de nuevo y fallaba por duplicado.
    # Ahora buscamos por número de orden directo. Si existe, la usamos.
    orden = Orden.query.filter_by(numero_orden=numero_ref).first()
    
    if not orden:
        orden = Orden(numero_orden=numero_ref, origen='TRANSFERENCIA', estado='PENDIENTE')
        db.session.add(orden)
        db.session.commit()
    
    return render_template('transferencias.html', orden=orden)

@bp.route('/buscar', methods=['GET'])
def buscar_productos():
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])

    palabras = query.upper().split()

    filtros = []
    for p in palabras:
        filtros.append(
            (ProductoMaestro.sku.contains(p)) |
            (ProductoMaestro.descripcion.contains(p))
        )

    resultados = ProductoMaestro.query.filter(*filtros).limit(20).all()

    return jsonify([
        {'sku': p.sku, 'descripcion': p.descripcion}
        for p in resultados
    ])


@bp.route('/agregar-manual', methods=['POST'])
def agregar_manual():
    data = request.json
    orden_id = data['orden_id']
    input_code = data['sku'].strip().upper()
    cantidad = int(data.get('cantidad', 1))
    orden = Orden.query.get_or_404(orden_id)
    
    # Lógica Inteligente
    sku_found = None
    if ProductoMaestro.query.get(input_code): sku_found = input_code
    elif ProductoCodigo.query.get(input_code): sku_found = ProductoCodigo.query.get(input_code).sku
    elif ProductoMaestro.query.filter_by(ean=input_code).first(): sku_found = ProductoMaestro.query.filter_by(ean=input_code).first().sku

    if not sku_found: return jsonify({'success': False, 'error_code': 'UNKNOWN_BARCODE', 'scanned_code': input_code})

    prod = ProductoMaestro.query.get(sku_found)
    item = Item.query.filter_by(orden_id=orden.id, sku=sku_found).first()
    if item:
        item.cantidad_pickeada += cantidad; item.cantidad_pedida += cantidad
        mensaje = f"Sumados {cantidad}: {item.descripcion}"
    else:
        item = Item(orden=orden, sku=sku_found, descripcion=prod.descripcion, cantidad_pedida=cantidad, cantidad_pickeada=cantidad)
        db.session.add(item)
        mensaje = f"Agregado: {item.descripcion}"

    db.session.commit()
    return jsonify({'success': True, 'mensaje': mensaje, 'item': {'sku': item.sku, 'descripcion': item.descripcion, 'cantidad': item.cantidad_pickeada}})


@bp.route('/borrar-item', methods=['POST'])
def borrar_item():
    data = request.json
    orden_id = data.get('orden_id')
    sku = data.get('sku')
    
    try:
        # Buscamos el item específico en esa orden de transferencia
        item = Item.query.filter_by(orden_id=orden_id, sku=sku).first()
        
        if item:
            db.session.delete(item) # Lo borramos físicamente de la base de datos
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Item no encontrado'})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/vincular-y-agregar', methods=['POST'])
def vincular_y_agregar():
    data = request.json
    try:
        nuevo = ProductoCodigo(codigo_barra=data['codigo_nuevo'], sku=data['sku_target'])
        db.session.add(nuevo)
        db.session.commit()
    except: db.session.rollback()
    return agregar_manual()

@bp.route('/finalizar', methods=['POST'])
def finalizar():
    print(">>> INICIO: Finalizar Transferencia") 
    
    data = request.json
    orden_id = data['orden_id']
    imprimir_solicitado = data.get('imprimir', False) 
    sentido = data.get('sentido', 'DEPO_A_SALON') # Definimos la variable
    
    orden = Orden.query.get_or_404(orden_id)
    if not orden.items: return jsonify({'success': False, 'error': 'Lista vacía.'})

    orden.destino = sentido          
    orden.cliente_nombre = "INTERNO" 
    
    # --- 0. CALCULAR TOTAL DE UNIDADES ---
    total_unidades = sum(item.cantidad_pickeada for item in orden.items)
    LIMITE_SEGURIDAD = 150 
    
    imprimir = imprimir_solicitado
    msg_seguridad = ""

    if imprimir and total_unidades > LIMITE_SEGURIDAD:
        imprimir = False
        msg_seguridad = f". ⚠️ NO se imprimieron etiquetas por seguridad (Son {total_unidades}). Hacelo por lotes."
        print(f">>> ALERTA: {total_unidades} unidades. Se desactiva impresión automática.")

    # --- 1. PREPARAR DATOS ---
    print(f">>> Procesando {len(orden.items)} items...")
    
    # BUCLE CORREGIDO (Solo uno)
    for item in orden.items:
        cantidad = item.cantidad_pickeada

        if sentido == "DEPO_A_SALON":
            # Sale de depósito
            db.session.add(Movimiento(
                orden_id=orden.id, sku=item.sku, cantidad=cantidad,
                origen_stock="DEPO", fecha=datetime.utcnow()
            ))
            # Entra a salón
            db.session.add(Movimiento(
                orden_id=orden.id, sku=item.sku, cantidad=cantidad,
                origen_stock="SALON", fecha=datetime.utcnow()
            ))
        else:
            # Sale de salón
            db.session.add(Movimiento(
                orden_id=orden.id, sku=item.sku, cantidad=cantidad,
                origen_stock="SALON", fecha=datetime.utcnow()
            ))
            # Entra a depósito
            db.session.add(Movimiento(
                orden_id=orden.id, sku=item.sku, cantidad=cantidad,
                origen_stock="DEPO", fecha=datetime.utcnow()
            ))

    db.session.commit()
    print(">>> SQL Guardado.")

    # --- 2. DISPARO CARRIL RÁPIDO ---
    print(">>> Disparando sincronizador blindado...")
    try:
        script_path = r"Z:\VENTAS\MOVSTK\sincronizador_blindado.py"
        subprocess.Popen(
            ["python", script_path],
            cwd=os.path.dirname(script_path),
            shell=True
        )
    except Exception as e:
        print(f"⚠️ Error trigger: {e}")

    # --- 3. GENERAR ETIQUETAS ---
    msg_etiquetas = ""
    if imprimir:
        print(">>> Generando etiquetas PDF...")
        try:
            res = generar_etiquetas_termicas(orden.items, orden.numero_orden)
            msg_etiquetas = f" ({res['msg']})"
            print(">>> PDF OK.")
        except Exception as e:
            print(f"!!! ERROR ETIQUETAS: {e}")
            msg_etiquetas = " (Error PDF)"

    # --- 4. FINALIZAR ---
    timestamp = datetime.now().strftime('%H%M%S')
    orden.numero_orden = f"{orden.numero_orden}-{timestamp}" 
    orden.estado = 'COMPLETA'
    db.session.commit()
    
    print(">>> FIN PROCESO.")
    return jsonify({
        'success': True, 
        'mensaje': f"Transferencia finalizada{msg_etiquetas}{msg_seguridad}"
    })

@bp.route('/imprimir-lote-manual', methods=['POST'])
def imprimir_lote_manual():
    """
    Permite imprimir X cantidad de etiquetas de un SKU específico 
    de una orden ya cerrada (útil cuando salta la válvula de seguridad).
    """
    data = request.json
    sku = data.get('sku')
    cantidad = int(data.get('cantidad', 100)) # Por defecto lotes de 100
    numero_orden = data.get('numero_orden', 'LOTE-MANUAL')
    
    # Creamos un objeto falso (item simulado) para pasarselo al generador
    class ItemSimulado:
        def __init__(self, s, c):
            self.sku = s
            self.descripcion = "LOTE MANUAL"
            self.cantidad_pickeada = c

    items_simulados = [ItemSimulado(sku, cantidad)]
    
    try:
        
        res = generar_etiquetas_termicas(items_simulados, numero_orden)
        return jsonify({'success': True, 'mensaje': f"Imprimiendo lote de {cantidad} para {sku}"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})