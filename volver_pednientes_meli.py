import sqlite3
import os

# Ruta a tu base de datos (Ajustala si es necesario)
DB_PATH = r"C:\Users\Usuario\Desktop\ERP-PINO\Programa Stock\pickeo.db"

def volver_a_pendiente():
    if not os.path.exists(DB_PATH):
        print(f"❌ ERROR: No encuentro la base de datos en: {DB_PATH}")
        return

    # Pedimos el ID de Venta de MELI (El largo)
    venta_id = input("Ingrese el N° de Venta MELI (ej: 2000014884557392): ").strip()

    if not venta_id:
        print("❌ Debe ingresar un número.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Buscar la orden para ver si existe
        # Buscamos por numero_orden O por meli_order_id para estar seguros
        cursor.execute("""
            SELECT id, cliente_nombre, estado 
            FROM orden 
            WHERE numero_orden = ? OR meli_order_id = ?
        """, (venta_id, venta_id))
        
        orden = cursor.fetchone()

        if not orden:
            print(f"❌ No encontré ninguna orden con el número {venta_id}.")
            return

        orden_id_interno = orden[0]
        cliente = orden[1]
        estado_actual = orden[2]

        print(f"\n✅ Orden Encontrada: ID Interno {orden_id_interno}")
        print(f"   Cliente: {cliente}")
        print(f"   Estado Actual: {estado_actual}")

        confirmacion = input("\n¿Confirmas volverla a PENDIENTE para re-sincronizar? (S/N): ")
        
        if confirmacion.upper() == "S":
            # A. Actualizar la tabla ORDEN (Para que se vea Pendiente en la web)
            cursor.execute("""
                UPDATE orden 
                SET estado = 'PENDIENTE', 
                    manual_etapa = NULL 
                WHERE id = ?
            """, (orden_id_interno,))

            # B. Actualizar la tabla MOVIMIENTO (CRUCIAL para el Sincronizador)
            # Borramos las marcas de exportación para que parezca nueva
            cursor.execute("""
                UPDATE movimiento 
                SET exportado = 0, 
                    lote_id = NULL, 
                    fecha_impacto = NULL
                WHERE orden_id = ?
            """, (orden_id_interno,))
            
            items_liberados = cursor.rowcount
            
            conn.commit()
            print(f"\n🚀 ¡LISTO! La orden volvió a PENDIENTE.")
            print(f"👉 Se liberaron {items_liberados} items.")
            print("👉 La próxima vez que corras el Sincronizador, esta orden se volverá a enviar a Clipper.")
        else:
            print("Operación cancelada.")

    except Exception as e:
        print(f"❌ Error en la base de datos: {e}")
        conn.rollback()
    
    finally:
        conn.close()
        input("\nPresione Enter para salir...")

if __name__ == "__main__":
    volver_a_pendiente()