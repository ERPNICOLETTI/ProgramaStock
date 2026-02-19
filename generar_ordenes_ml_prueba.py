import sqlite3
from datetime import datetime

DB_PATH = "pickeo.db"

SKU = "PSN1"
DESCRIPCION = "Producto prueba PSN1"
CANTIDAD = 1


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def generar_numero_orden():
    # Número único tipo ML-TEST-20260130113345
    return "MLTEST-" + datetime.now().strftime("%Y%m%d%H%M%S")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # IDs
    cur.execute("SELECT MAX(id) FROM orden")
    orden_id = (cur.fetchone()[0] or 0) + 1

    cur.execute("SELECT MAX(id) FROM item")
    item_id = (cur.fetchone()[0] or 0) + 1

    numero_orden = generar_numero_orden()

    print("Creando orden:", numero_orden)

    # =========================
    # ORDEN
    # =========================
    data = {
        "id": orden_id,
        "numero_orden": numero_orden,
        "origen": "ML",
        "destino": "CLIENTE",
        "fecha_creacion": now(),
        "estado": "EN_PREPARACION",
        "cliente_nombre": f"ML TEST {numero_orden}",
        "direccion": "PRUEBA ML",
        "localidad": "TEST",
        "cp": "0000",
        "email": "test@ml.com",
        "telefono": "000000",
        "tipo_flujo": "ML",
    }

    columnas = ",".join(data.keys())
    placeholders = ",".join(["?"] * len(data))

    cur.execute(
        f"INSERT INTO orden ({columnas}) VALUES ({placeholders})",
        list(data.values())
    )

    # =========================
    # ITEM
    # =========================
    data_item = {
        "id": item_id,
        "orden_id": orden_id,
        "sku": SKU,
        "descripcion": DESCRIPCION,
        "cantidad_pedida": CANTIDAD,
        "cantidad_pickeada": 0,
    }

    columnas = ",".join(data_item.keys())
    placeholders = ",".join(["?"] * len(data_item))

    cur.execute(
        f"INSERT INTO item ({columnas}) VALUES ({placeholders})",
        list(data_item.values())
    )

    conn.commit()
    conn.close()

    print("✅ Orden creada:", numero_orden)


if __name__ == "__main__":
    main()
