import os
import re
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

def scan_local_pdfs():
    folders_to_scan = [
        Path(r"C:\Users\hp ProBook 650 G1\Desktop\CONCOUR 2026"),
        Path(r"C:\Users\hp ProBook 650 G1\Desktop\python\cour_ligne\media"),
    ]
    files = []
    for root in folders_to_scan:
        if root.exists():
            for p in root.rglob("*.pdf"):
                files.append(p)
    return files

def extract_number(text):
    m = re.search(r'(\d+)', text)
    return int(m.group(1)) if m else None

def find_match(record, local_files):
    cat_name = record['cat_name']
    kind = record['kind']
    title = record['title']
    num = extract_number(title)
    
    cat_aliases = {
        'finances': ['finance', 'finances'],
        'tresor': ['tresor'],
        'grh': ['grh'],
        'statistique': ['statistique', 'statisque'],
        'ac/aa': ['ac', 'aa', 'acaa'],
        'cisu/aisu': ['cisu', 'aisu', 'cisuaisu'],
        'casu/aasu': ['casu', 'aasu', 'casuaasu'],
        'affaire etrangere': ['affaire etrangere', 'affaires etrangeres', 'affaires_etrangeres'],
        'gsp': ['gsp'],
        'administration sanitaire': ['administration sanitaire', 'ass et gss', 'ass', 'gss'],
        'ingenieurs en soins infirmiers et obstetricaux': ['ingeniere sante', 'isio', 'soins', 'infirmiers', 'obstetricaux'],
        'douane': ['douane'],
        'environnement': ['environnement'],
        'eaux et foret': ['eaux et forets', 'eaux', 'foret'],
        'impt': ['impot', 'impots'],
        'impot': ['impot', 'impots'],
    }
    
    cat_key = cat_name.lower().strip()
    aliases = cat_aliases.get(cat_key, [cat_key])
    
    cat_files = []
    for f in local_files:
        f_str = str(f).lower()
        if any(a in f_str for a in aliases):
            cat_files.append(f)
            
    kind_files = []
    for f in cat_files:
        fname = f.name.lower()
        fdir = str(f.parent).lower()
        if kind == 'corrections':
            if 'corr' in fname or 'corr' in fdir:
                kind_files.append(f)
        elif kind == 'cours_mois':
            if ('sujet' in fname or 'sujet' in fdir or 'cours' in fname) and ('corr' not in fname):
                kind_files.append(f)
        elif kind == 'examens':
            if 'exam' in fname or 'exam' in fdir:
                kind_files.append(f)
                
    if num is not None:
        for f in kind_files:
            f_num = extract_number(f.stem)
            if f_num == num:
                return f
                
    # Special single item fallbacks
    if len(kind_files) == 1 and num == 1:
        return kind_files[0]
        
    return None

if __name__ == '__main__':
    from match_and_sync import get_db_records
    records = get_db_records()
    local_files = scan_local_pdfs()
    
    matched = []
    unmatched = []
    for r in records:
        f = find_match(r, local_files)
        if f:
            matched.append((r, f))
        else:
            unmatched.append(r)
            
    print(f"Total Render DB records: {len(records)}")
    print(f"MATCHED: {len(matched)} / {len(records)}")
    print(f"UNMATCHED: {len(unmatched)} / {len(records)}")
    
    from collections import Counter
    print("\nUnmatched summary:")
    for k, v in Counter((u['cat_name'], u['kind']) for u in unmatched).items():
        print(f"  {k[0]} ({k[1]}): {v}")
