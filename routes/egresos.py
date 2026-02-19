from flask import Blueprint, render_template, request, jsonify
from database import db
from models.orden import Orden, Item, Movimiento, ProductoMaestro, Cliente, ProductoCodigo
from services.clipper_service import agregar_al_maestro
from services.remito_service import generar_remito_a4
from datetime import datetime
import subprocess
import os


bp = Blueprint('egresos', __name__, url_prefix='/egresos')

@bp.route('/')
def index():
    hoy_str = datetime.now().strftime('%Y%m%d')
    base_ref = f"EGR-{hoy_str}" 
    orden = Orden.query.filter_by(numero_orden=base_ref, origen='EGRESO', estado='PENDIENTE').first()
    if not orden:
        verificar = Orden.query.filter_by(numero_orden=base_ref).first()
        nombre = f"{base_ref}-{datetime.now().strftime('%H%M%S')}" if verificar else base_ref
        orden = Orden(numero_orden=nombre, origen='EGRESO', estado='PENDIENTE')
        db.session.add(orden)
        db.session.commit()
    
    clientes = Cliente.query.order_by(Cliente.nombre).all()
    return render_template('egresos.html', orden=orden, clientes=clientes)

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

    # Lógica de Búsqueda Inteligente
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

@bp.route('/vincular-y-agregar', methods=['POST'])
def vincular_y_agregar():
    data = request.json
    try:
        nuevo = ProductoCodigo(codigo_barra=data['codigo_nuevo'], sku=data['sku_target'])
        db.session.add(nuevo)
        db.session.commit()
    except: db.session.rollback()
    return agregar_manual()

# Importar al principio:
from services.clipper_service import agregar_al_maestro, obtener_codigo_cliente, generar_id_unico

@bp.route('/finalizar', methods=['POST'])
def finalizar():
    data = request.json
    orden_id = data.get('orden_id')
    imprimir_remito = data.get('imprimir_remito', False)
    deposito_origen = data.get('origen', 'INVP01')
    cliente_seleccionado = data.get('cliente', '*') 
    
    orden = Orden.query.get_or_404(orden_id)
    if not orden.items: return jsonify({'success': False, 'error': 'Lista vacía.'})

    orden.destino = f"DESDE_{deposito_origen}"
    if cliente_seleccionado != "*":
        cli_obj = Cliente.query.get(cliente_seleccionado)
        if cli_obj: orden.cliente_nombre = cli_obj.nombre
    else: orden.cliente_nombre = "CLIENTE GENERICO"

    # --- PREPARAR DATOS ---
    cli_code = obtener_codigo_cliente(orden.cliente_nombre)
    orden_serial = generar_id_unico(orden)

    for item in orden.items:
        mov = Movimiento(
            orden_id=orden.id,
            sku=item.sku,
            cantidad=item.cantidad_pickeada,
            fecha=datetime.utcnow(),
            origen_stock="SALON" if deposito_origen == "INVP01" else "DEPO"
        )
        db.session.add(mov)


    # --- 1. GUARDADO CRÍTICO EN SQL ---
    # Esto DEBE ocurrir antes de llamar al sincronizador
    db.session.commit() 
    print(">>> SQL Guardado (Movimientos listos para sincronizar).")

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

    # --- 3. Generar PDF y Cerrar Orden ---
    pdf_url = generar_remito_a4(orden.items, orden.numero_orden, deposito_origen) if imprimir_remito else None
    
    timestamp = datetime.now().strftime('%H%M%S')
    orden.numero_orden = f"{orden.numero_orden}-{timestamp}" 
    orden.estado = 'COMPLETA'
    
    # Guardamos el cambio de estado de la orden
    db.session.commit()
    
    return jsonify({'success': True, 'pdf_url': pdf_url})

@bp.route('/borrar-item', methods=['POST'])
def borrar_item():
    data = request.json
    item = Item.query.filter_by(orden_id=data['orden_id'], sku=data['sku']).first()
    if item: db.session.delete(item); db.session.commit(); return jsonify({'success': True})
    return jsonify({'success': False})

# ==========================================================
# FUNCIÓN REUTILIZABLE PARA EGRESOS AUTOMÁTICOS (ML)
# ==========================================================
def ejecutar_egreso_automatico(
    orden: Orden,
    deposito_origen="INVP01",
    cliente_forzado="ML"
):
    if not orden.items:
        return

    # ==================================================
    # CLIENTE ML FORZADO (FULL BLOQUEADO)
    # ==================================================
    cli_code = "ML"
    orden.cliente_nombre = "ML"

    orden_serial = generar_id_unico(orden)
    lista_dbf = []

    for item in orden.items:
        mov = Movimiento(
            orden_id=orden.id,
            sku=item.sku,
            cantidad=item.cantidad_pickeada,
            fecha=datetime.utcnow(),
            origen_stock="SALON" if deposito_origen == "INVP01" else "DEPO"
        )
        db.session.add(mov)


        cantidad = item.cantidad_pickeada

        if deposito_origen == "INVP02":
            val_invpen = -cantidad
            val_invact = 0
        else:
            val_invpen = 0
            val_invact = -cantidad

        lista_dbf.append({
    'invcod': item.sku,
    'cliente': 'ML',   # ← FORZADO ABSOLUTO
    'orden': orden_serial,
    'tipo': 'EGRESO',
    'cant': cantidad,
    'invpen': val_invpen,
    'invact': val_invact
})


    db.session.commit()

    # if lista_dbf:
    #     agregar_al_maestro(lista_dbf)
    
    # NOTA: Aquí NO llamamos al sincronizador.
    # ML se queda esperando en la base de datos hasta que aprietes "Procesar Lote".




