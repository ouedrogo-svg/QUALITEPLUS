import os
import sys
import re
from pathlib import Path
import psycopg2
import cloudinary
import cloudinary.uploader
from django.conf import settings

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from scripts.execute_sync import DB_PARAMS

def main():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()

    isio_dir = Path(r"C:\Users\hp ProBook 650 G1\Desktop\CONCOUR 2026\CONCOUR PROFESSIONNEL 2027\INGENIERE SANTE")
    for f in sorted(isio_dir.rglob("*.pdf")):
        name = f.name
        m = re.search(r'(CORRECTION|SUJET)-0?(\d+)', name)
        if not m:
            continue
        kind_str, num = m.group(1), int(m.group(2))
        table = 'courses_monthlycorrection' if kind_str == 'CORRECTION' else 'courses_monthlycoursecontent'
        kind = 'corrections' if kind_str == 'CORRECTION' else 'cours_mois'
        
        cur.execute(f"""
            SELECT t.id, t.title FROM {table} t
            JOIN courses_category c ON t.category_id = c.id
            WHERE c.name LIKE '%%SOINS%%' AND t.title LIKE %s
        """, (f"%{num}%",))
        row = cur.fetchone()
        if row:
            obj_id, title = row
            res = cloudinary.uploader.upload(
                str(f),
                folder=kind,
                resource_type="raw",
                use_filename=True,
                unique_filename=True
            )
            public_id = res['public_id']
            cur.execute(f"UPDATE {table} SET pdf = %s WHERE id = %s", (public_id, obj_id))
            conn.commit()
            print(f"[OK] FIXED ISIO: {table}.id={obj_id} ({title}) -> {public_id}")
        else:
            print(f"[WARN] No match for {name}")

    conn.close()

if __name__ == '__main__':
    main()
