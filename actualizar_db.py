import sqlite3

DB_PATH = "pickeo.db"

def columna_existe(cur, tabla, columna):
    cur.execute(f"PRAGMA table_info({tabla})")
    return columna in [row[1] for row in cur.fetchall()]

def main():
    print("🔍 Abriendo base:", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if columna_existe(cur, "movimiento", "origen_stock"):
        print("✅ La columna origen_stock ya existe. No se hace nada.")
        conn.close()
        return

    print("➕ Agregando columna origen_stock...")
    cur.execute("ALTER TABLE movimiento ADD COLUMN origen_stock TEXT")
    conn.commit()

    print("✅ Migración completada. La base quedó intacta.")
    conn.close()

if __name__ == "__main__":
    main()
