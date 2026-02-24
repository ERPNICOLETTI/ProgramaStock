from app import app
from database import db
from models.orden import Cambio, ItemCambio

def main():
    print("Creando tablas Cambio e ItemCambio si no existen...")
    with app.app_context():
        db.create_all()
    print("Creacion de tablas completada.")

if __name__ == "__main__":
    main()
