from flask import session
from models.orden import Item # Necesario para la función de Picklist

# --- UTILIDADES DE SESIÓN ADMIN ---
def is_admin_logged_in():
    """Verifica si el administrador ha iniciado sesión (usando la sesión de Flask)."""
    return session.get('admin_logged_in') == True

# --- UTILIDADES DE PICKLIST ---
def agrupar_items_para_picklist(ordenes):
    """
    Consolida los ítems pendientes de múltiples órdenes en una única lista de pickeo.
    Esta lógica se saca de routes/ordenes.py para modularizar.
    """
    agrupado = {}
    total_unidades = 0
    for orden in ordenes:
        # Aseguramos que la orden tenga ítems para evitar errores
        if not hasattr(orden, 'items'): continue
            
        for item in orden.items:
            # Filtramos solo los ítems pendientes
            pendiente = item.cantidad_pedida - item.cantidad_pickeada
            if pendiente > 0:
                sku = item.sku.strip().upper()
                if sku in agrupado:
                    agrupado[sku]['cantidad'] += pendiente
                else:
                    agrupado[sku] = {'sku': sku, 'descripcion': item.descripcion, 'cantidad': pendiente}
                total_unidades += pendiente
                
    lista = list(agrupado.values())
    lista.sort(key=lambda x: x['sku'])
    return lista, total_unidades