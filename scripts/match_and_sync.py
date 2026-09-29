import os
import sys
import psycopg2
from pathlib import Path

DB_PARAMS = {
    'dbname': 'qualiteplus_dpuh',
    'user': 'qualiteplus_dpuh_user',
    'password': 'lUCJXRBAgiH5SObNXGtFnrPgWzRkiiXM',
    'host': 'dpg-d87lhfh9rddc73fs3h7g-a.oregon-postgres.render.com',
    'port': 5432,
    'sslmode': 'require',
}

def get_db_records():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    records = []
    for table, kind in [
        ('courses_monthlycoursecontent', 'cours_mois'),
        ('courses_monthlycorrection', 'corrections'),
        ('courses_monthlyexam', 'examens'),
    ]:
        cur.execute(f'''
            SELECT t.id, c.name, c.slug, t.year, t.month, t.title, t.pdf
            FROM {table} t
            JOIN courses_category c ON t.category_id = c.id
            ORDER BY c.name, t.year, t.month, t.title
        ''')
        for row in cur.fetchall():
            records.append({
                'table': table,
                'kind': kind,
                'id': row[0],
                'cat_name': row[1],
                'cat_slug': row[2],
                'year': row[3],
                'month': row[4],
                'title': row[5],
                'current_pdf': row[6],
            })
    conn.close()
    return records

if __name__ == '__main__':
    records = get_db_records()
    print(f"Total records in Render DB: {len(records)}")
    by_cat = {}
    for r in records:
        key = (r['cat_name'], r['year'], r['month'], r['kind'])
        by_cat.setdefault(key, []).append(r)
    
    for k, v in sorted(by_cat.items()):
        titles = [item['title'] for item in v]
        print(f"[{k[0]}] {k[1]}-{k[2]:02d} ({k[3]}): {len(v)} records -> {titles[:8]}")
