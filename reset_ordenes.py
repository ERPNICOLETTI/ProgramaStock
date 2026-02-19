from app import app
from database import db
from models.orden import Orden, Item, Picklist, Movimiento
from sqlalchemy import text

def reiniciar_ordenes():
    print("\n" + "="*50)
    print("⚠️  ATENCIÓN: ESTO BORRARÁ TODAS LAS ÓRDENES, MOVIMIENTOS Y EL HISTORIAL")
    print("   (Tus Productos, Clientes y Proveedores NO se borrarán)")
    print("="*50)
    
    confirmacion = input("Escribe 'SI' para confirmar: ")
    
    if confirmacion != 'SI':
        print("❌ Cancelado.")
        return

    with app.app_context():
        try:
            # 1. Borramos las tablas relacionadas (Orden inverso a las dependencias)
            print("⏳ Borrando Items...")
            db.session.query(Item).delete()
            
            print("⏳ Borrando Movimientos...")
            db.session.query(Movimiento).delete()
            
            print("⏳ Borrando Órdenes...")
            db.session.query(Orden).delete()
            
            print("⏳ Borrando Picklists...")
            db.session.query(Picklist).delete()
            
            db.session.commit() # Confirmamos el borrado de datos primero

            # 2. Intentamos reiniciar los contadores de ID (Opcional)
            # Ponemos esto en un try/except por si sqlite_sequence no existe aún
            try:
                print("⏳ Reiniciando contadores de ID a 1...")
                # Flask/SQLAlchemy a veces usa el nombre de la clase o el __tablename__
                # Intentamos borrar las secuencias conocidas
                tablas_a_reiniciar = ['orden', 'item', 'picklist', 'movimiento']
                
                for tabla in tablas_a_reiniciar:
                    db.session.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{tabla}'"))
                
                db.session.commit()
                print("✅ Contadores reiniciados.")
            except Exception as e:
                # Si falla esto, no importa, los datos ya se borraron arriba
                print(f"⚠️ Nota técnica: No se reiniciaron los contadores (Tabla sqlite_sequence no encontrada o vacía). Esto es normal en DBs nuevas.")

            print("\n✅ ¡LISTO! Sistema limpio. Bandeja de salida vacía.")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Ocurrió un error crítico: {e}")

if __name__ == "__main__":
    reiniciar_ordenes()