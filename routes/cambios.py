from flask import Blueprint, request, jsonify
from database import db
from models.orden import Orden, Item, Cambio, ItemCambio, Movimiento
from datetime import datetime
import json

bp = Blueprint('cambios', __name__, url_prefix='/cambios')

def generar_orden_cambio(cambio, item_cambio):
    """
    Función helper que inyecta una nueva Orden de tipo CAMBIO en el sistema
    para que los preparadores de pedidos la pickeen y empaqueten como cualquier otra.
    """
    orden_original = cambio.orden_original
    
    # 1. Crear nueva Orden satélite
    nueva_orden = Orden(
        numero_orden=f"CAMBIO-{orden_original.numero_orden}",
        origen="MANUAL",
        cliente_nombre=orden_original.cliente_nombre,
        nro_factura=orden_original.nro_factura,
        dni=orden_original.dni,
        direccion=orden_original.direccion,
        localidad=orden_original.localidad,
        cp=orden_original.cp,
        email=orden_original.email,
        telefono=orden_original.telefono,
        # Observaciones que avisan al armador que es un Cambio
        observaciones=f"CAMBIO DE SKU: {item_cambio.sku_devuelto}",
        
        estado="EN_PREPARACION", # Entra directamente a la cola de armado
        tipo_flujo="MANUAL",
        manual_etapa="PREPARACION"
    )
    db.session.add(nueva_orden)
    db.session.flush() # Obtenemos el ID de nueva_orden
    
    # 2. Crear Item que el cliente nuevo se va a llevar (el reemplazo)
    if item_cambio.sku_nuevo and item_cambio.cantidad_nueva > 0:
        nuevo_item = Item(
            orden_id=nueva_orden.id,
            sku=item_cambio.sku_nuevo,
            descripcion=item_cambio.sku_nuevo, # Se puede mejorar buscando en ProductoMaestro
            cantidad_pedida=item_cambio.cantidad_nueva
        )
        db.session.add(nuevo_item)
        
    return nueva_orden

@bp.route('/crear', methods=['POST'])
def crear_cambio():
    """
    Crea el registro de Cambio y decide si despachar ya (ANDREANI) o esperar (NORMAL).
    """
    try:
        data = request.get_json()
        factura_u_orden = data.get('nro_factura', '').strip()
        sku_devuelto = data.get('sku_devuelto', '').strip()
        cantidad_devuelta = int(data.get('cantidad_devuelta', 1))
        sku_nuevo = data.get('sku_nuevo', '').strip()
        cantidad_nueva = int(data.get('cantidad_nueva', 1))
        modalidad = data.get('modalidad', 'NORMAL')
        
        # Buscar la orden por número de factura o número de orden
        orden = Orden.query.filter(
            (Orden.nro_factura == factura_u_orden) | 
            (Orden.numero_orden == factura_u_orden)
        ).first()
        
        if not orden:
            return jsonify({'success': False, 'error': f'Orden original "{factura_u_orden}" no encontrada'})
            
        nuevo_cambio = Cambio(
            orden_original_id=orden.id,
            modalidad=modalidad,
            estado_ingreso='PENDIENTE',
            estado_egreso='PENDIENTE'
        )
        db.session.add(nuevo_cambio)
        db.session.flush()
        
        nuevo_item_cambio = ItemCambio(
            cambio_id=nuevo_cambio.id,
            sku_devuelto=sku_devuelto,
            cantidad_devuelta=cantidad_devuelta,
            sku_nuevo=sku_nuevo,
            cantidad_nueva=cantidad_nueva
        )
        db.session.add(nuevo_item_cambio)
        
        # LOGICA ANDREANI: Cross-shipping (Se despacha el nuevo inmediatamente)
        if modalidad == 'ANDREANI':
            generar_orden_cambio(nuevo_cambio, nuevo_item_cambio)
            nuevo_cambio.estado_egreso = 'EN_PROCESO'
            
        db.session.commit()
        return jsonify({'success': True, 'mensaje': 'Cambio creado exitosamente'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/recibir/<int:cambio_id>', methods=['POST'])
def recibir_cambio(cambio_id):
    """
    Recibe físicamente el paquete de vuelta.
    Devuelve la mercadería al stock (Movimiento a DEPO) y si era NORMAL, dispara el envío de reemplazo.
    """
    try:
        data = request.get_json()
        condicion = data.get('condicion', 'OK')
        
        cambio = Cambio.query.get(cambio_id)
        if not cambio:
            return jsonify({'success': False, 'error': 'Cambio no encontrado'})
            
        if cambio.estado_ingreso == 'COMPLETADO':
            return jsonify({'success': False, 'error': 'El ingreso de este cambio ya fue procesado'})
            
        item = cambio.items[0]
        item.condicion_recibida = condicion
        
        # Generar Movimiento para sumar el stock devuelto
        if condicion == 'OK': # Solo sumamos si no está roto
            mov_ingreso = Movimiento(
                orden_id=cambio.orden_original_id,
                sku=item.sku_devuelto,
                cantidad=item.cantidad_devuelta, # Positivo, ingresa
                origen_stock='DEPO' 
            )
            db.session.add(mov_ingreso)
            
        cambio.estado_ingreso = 'COMPLETADO'
        
        # LOGICA NORMAL: Recién ahora que recibimos el roto, mandamos el nuevo
        if cambio.modalidad == 'NORMAL' and cambio.estado_egreso == 'PENDIENTE':
            generar_orden_cambio(cambio, item)
            cambio.estado_egreso = 'EN_PROCESO'
            
        db.session.commit()
        return jsonify({'success': True, 'mensaje': 'Paquete recibido y stock actualizado'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})
