from flask import Blueprint, render_template, request, jsonify
from database import db
from models.orden import Orden, Item, Movimiento, ProductoMaestro, Proveedor, ProductoCodigo
from services.clipper_service import agregar_al_maestro, obtener_codigo_proveedor, generar_id_unico
from services.etiquetas_service import generar_etiquetas_termicas
from datetime import datetime
import subprocess
import os

bp = Blueprint('ingresos', __name__, url_prefix='/ingresos')

@bp.route('/')
def index():
    # 1. Buscamos si ya hay una orden PENDIENTE para retomarla
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    orden = Orden(
        numero_orden=f"ING-{timestamp}",
        origen='INGRESO',
        estado='PENDIENTE'
    )
    db.session.add(orden)
    db.session.commit()
       
    proveedores = Proveedor.query.order_by(Proveedor.nombre).all()
    return render_template('ingresos.html', orden=orden, proveedores=proveedores)

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

    
    return jsonify([{'sku': p.sku, 'descripcion': p.descripcion} for p in resultados])

# --- LÓGICA INTELIGENTE (APRENDIZAJE) ---
@bp.route('/agregar-manual', methods=['POST'])
def agregar_manual():
    data = request.json
    orden_id = data['orden_id']
    input_code = data['sku'].strip().upper()
    cantidad = int(data.get('cantidad', 1))
    orden = Orden.query.get_or_404(orden_id)

    # 1. Búsqueda Directa (SKU)
    sku_found = None
    prod_maestro = ProductoMaestro.query.get(input_code)
    if prod_maestro:
        sku_found = prod_maestro.sku

    # 2. Búsqueda por Código Vinculado (Tabla Aprendida)
    if not sku_found:
        vinculo = ProductoCodigo.query.get(input_code)
        if vinculo:
            sku_found = vinculo.sku
            prod_maestro = ProductoMaestro.query.get(sku_found)

    # 3. Búsqueda por EAN Legacy
    if not sku_found:
        prod_ean = ProductoMaestro.query.filter_by(ean=input_code).first()
        if prod_ean:
            sku_found = prod_ean.sku
            prod_maestro = prod_ean

    # SI NO SE ENCUENTRA NADA -> ERROR ESPECIAL PARA VINCULAR
    if not sku_found:
        return jsonify({'success': False, 'error_code': 'UNKNOWN_BARCODE', 'scanned_code': input_code})

    # SI SE ENCONTRÓ, AGREGAMOS/SUMAMOS
    item = Item.query.filter_by(orden_id=orden.id, sku=sku_found).first()
    if item:
        item.cantidad_pickeada += cantidad
        item.cantidad_pedida += cantidad
        mensaje = f"Sumados {cantidad}: {item.descripcion}"
    else:
        item = Item(orden=orden, sku=sku_found, descripcion=prod_maestro.descripcion, cantidad_pedida=cantidad, cantidad_pickeada=cantidad)
        db.session.add(item)
        mensaje = f"Agregado: {item.descripcion}"

    db.session.commit()
    return jsonify({'success': True, 'mensaje': mensaje, 'item': {'sku': item.sku, 'descripcion': item.descripcion, 'cantidad': item.cantidad_pickeada}})

@bp.route('/vincular-y-agregar', methods=['POST'])
def vincular_y_agregar():
    """ Aprende el código y lo agrega a la orden """
    data = request.json
    # orden_id no se usa directamente aquí pero viene en el data
    nuevo_codigo = data.get('codigo_nuevo').strip().upper()
    sku_target = data.get('sku_target').strip().upper()
    
    # 1. Guardar Aprendizaje
    try:
        nuevo_vinculo = ProductoCodigo(codigo_barra=nuevo_codigo, sku=sku_target)
        db.session.add(nuevo_vinculo)
        db.session.commit()
    except:
        db.session.rollback()

    # 2. Llamar a la lógica de agregar normal
    return agregar_manual()

@bp.route('/finalizar', methods=['POST'])
def finalizar():
    print(">>> INICIO: Finalizar Ingreso")
    
    data = request.json
    orden_id = data.get('orden_id')
    imprimir_solicitado = data.get('imprimir', False)
    destino = data.get('destino', 'INVP01')
    cliente_seleccionado = data.get('cliente', '*') 
    
    orden = Orden.query.get_or_404(orden_id)
    if not orden.items: return jsonify({'success': False, 'error': 'Lista vacía.'})

    orden.destino = destino
    if cliente_seleccionado != "*":
        prov = Proveedor.query.get(cliente_seleccionado)
        if prov: orden.cliente_nombre = prov.nombre
    else:
        orden.cliente_nombre = "INGRESO STOCK"

    # --- 0. VÁLVULA DE SEGURIDAD (Limitar impresión masiva) ---
    total_unidades = sum(item.cantidad_pickeada for item in orden.items)
    LIMITE_SEGURIDAD = 150 # Límite para evitar Timeout
    
    imprimir = imprimir_solicitado
    msg_seguridad = ""

    if imprimir and total_unidades > LIMITE_SEGURIDAD:
        imprimir = False
        msg_seguridad = f". ⚠️ Demasiadas unidades ({total_unidades}). Imprimí por lotes."
        print(f">>> ALERTA: {total_unidades} unidades. Impresión desactivada por seguridad.")

    # --- 1. PREPARAR DATOS ---
    print(f">>> Procesando {len(orden.items)} items...")
    lista_dbf = []
    prov_code = obtener_codigo_proveedor(orden.cliente_nombre)
    orden_serial = generar_id_unico(orden)

    for item in orden.items:
        mov = Movimiento(
            orden_id=orden.id,
            sku=item.sku,
            cantidad=item.cantidad_pickeada,
            fecha=datetime.utcnow(),
            origen_stock="DEPO" if destino == "INVP02" else "SALON"
        )
        db.session.add(mov)

        
        # DBF
        cantidad = item.cantidad_pickeada
        if destino == "INVP02": val_invpen = cantidad; val_invact = 0
        else: val_invpen = 0; val_invact = cantidad

        lista_dbf.append({
            'invcod': item.sku, 'cliente': prov_code, 'orden': orden_serial,
            'tipo': 'INGRESO', 'cant': cantidad,
            'invpen': val_invpen, 'invact': val_invact
        })

    db.session.commit()
    print(">>> SQL Guardado.")

    # --- 2. ESCRIBIR DBF (Con protección) ---
    # --- NUEVO: Disparo al Sincronizador (Carril Rápido) ---
    print(">>> Disparando sincronizador blindado...")
    try:
        # Ruta absoluta al script que creaste
        script_path = r"Z:\VENTAS\MOVSTK\sincronizador_blindado.py"
        
        # Ejecutar en segundo plano (Popen) sin esperar respuesta
        subprocess.Popen(
            ["python", script_path],
            cwd=os.path.dirname(script_path),
            shell=True
        )
    except Exception as e:
        print(f"⚠️ No se pudo iniciar el sincronizador: {e}")

    # --- 3. ETIQUETAS (Con protección) ---
    msg_etiquetas = ""
    if imprimir:
        print(">>> Generando etiquetas...")
        try:
            res = generar_etiquetas_termicas(orden.items, orden.numero_orden)
            msg_etiquetas = f" ({res.get('msg', 'Impreso')})"
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
        'mensaje': f"Ingreso Guardado{msg_etiquetas}{msg_seguridad}"
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

@bp.route('/imprimir-solo-etiqueta', methods=['POST'])
def imprimir_solo_etiqueta():
    """
    Recibe un SKU y Descripción, genera e imprime la etiqueta 
    SIN guardar nada en base de datos ni generar movimientos.
    """
    data = request.json
    sku = data.get('sku')
    descripcion = data.get('descripcion', 'SIN DESCRIPCION')
    cantidad = int(data.get('cantidad', 1))

    # Clase simulada (Mismo truco que usamos en imprimir_lote_manual)
    class ItemSimulado:
        def __init__(self, s, d, c):
            self.sku = s
            self.descripcion = d
            self.cantidad_pickeada = c 
            self.cantidad = c
    
    # Creamos el objeto temporal
    item_temp = ItemSimulado(sku, descripcion, cantidad)

    try:
        # CORRECCIÓN APLICADA AQUÍ: 
        # 1er argumento: Lista de items ([item_temp])
        # 2do argumento: Nombre para el archivo ("MANUAL")
        resultado = generar_etiquetas_termicas([item_temp], "MANUAL")
        
        return jsonify(resultado)
    except Exception as e:
        print(f"Error imprimiendo etiqueta suelta: {e}")
        return jsonify({'success': False, 'msg': str(e)})

# --- AHORA SÍ: ALINEADO A LA IZQUIERDA ---
@bp.route('/borrar-item', methods=['POST'])
def borrar_item():
    data = request.json
    orden_id = data.get('orden_id')
    sku = data.get('sku')
    
    # Buscamos el item en la base de datos
    item = Item.query.filter_by(orden_id=orden_id, sku=sku).first()
    
    if item:
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'mensaje': 'Eliminado'})
    
    return jsonify({'success': False, 'error': 'Item no encontrado'})