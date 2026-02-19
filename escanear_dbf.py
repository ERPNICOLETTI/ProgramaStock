import dbf
import os

DBF_PATH = r"\\servidor\sistema\VENTAS\SETART.DBF"

print("=== SCAN SETART.DBF ===")

if not os.path.exists(DBF_PATH):
    print("❌ No existe:", DBF_PATH)
    exit()

table = dbf.Table(DBF_PATH)
table.open(mode=dbf.READ_ONLY)

print("Codepage detectado:", table.codepage)
print("Campos:")
for f in table.field_names:
    print(" -", f)

print("\n=== MUESTRA DE REGISTROS ===")

i = 0
for r in table:
    invcod = str(r.INVCOD)
    try:
        invnom = str(r.INVNOM)
    except:
        invnom = "<SIN INVNOM>"

    print(f"[{i}] INVCOD raw:'{invcod}' len={len(invcod)} | upper:'{invcod.strip().upper()}'")
    print(f"     INVNOM raw:'{invnom}'")
    print("     bytes INVCOD:", invcod.encode("utf-8", errors="replace"))
    print("     bytes INVNOM:", invnom.encode("utf-8", errors="replace"))
    print("-" * 60)

    i += 1
    if i == 10:
        break

table.close()

print("=== FIN SCAN ===")
