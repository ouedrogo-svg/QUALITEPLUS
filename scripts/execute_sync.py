import os
import sys
import re
import logging
from pathlib import Path
import psycopg2
import cloudinary
import cloudinary.uploader
import cloudinary.api
from django.conf import settings

# Setup Django for settings
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Configure Cloudinary
cloudinary.config(
    cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
    api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
    api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
    secure=True
)

DB_PARAMS = {
    'dbname': 'qualiteplus_dpuh',
    'user': 'qualiteplus_dpuh_user',
    'password': 'lUCJXRBAgiH5SObNXGtFnrPgWzRkiiXM',
    'host': 'dpg-d87lhfh9rddc73fs3h7g-a.oregon-postgres.render.com',
    'port': 5432,
    'sslmode': 'require',
}

from scripts.test_match import scan_local_pdfs, find_match
from scripts.match_and_sync import get_db_records

def main():
    logger.info("Démarrage de la synchronisation vers Cloudinary et PostgreSQL Render...")
    logger.info(f"Cloudinary Cloud: {settings.CLOUDINARY_STORAGE['CLOUD_NAME']}")
    
    # Récupérer les enregistrements de la base Render
    records = get_db_records()
    logger.info(f"Nombre d'enregistrements en base Render: {len(records)}")
    
    # Scanner les PDF locaux
    local_files = scan_local_pdfs()
    logger.info(f"Nombre de PDF locaux scannés: {len(local_files)}")
    
    # Trouver les correspondances
    matched_items = []
    for r in records:
        matched_file = find_match(r, local_files)
        if matched_file:
            matched_items.append((r, matched_file))
            
    logger.info(f"Total des fichiers trouvés à téléverser : {len(matched_items)} / {len(records)}")
    
    # Connexion à PostgreSQL Render
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    
    success_count = 0
    error_count = 0
    
    for idx, (rec, file_path) in enumerate(matched_items, 1):
        table = rec['table']
        obj_id = rec['id']
        kind = rec['kind'] # 'cours_mois', 'corrections', 'examens'
        cat_name = rec['cat_name']
        title = rec['title']
        
        logger.info(f"[{idx}/{len(matched_items)}] Traitement {cat_name} | {kind} | {title} (ID {obj_id})")
        logger.info(f"   Fichier local: {file_path.name}")
        
        try:
            # Téléversement vers Cloudinary
            upload_result = cloudinary.uploader.upload(
                str(file_path),
                folder=kind,
                resource_type="raw",
                use_filename=True,
                unique_filename=True,
            )
            public_id = upload_result['public_id']
            logger.info(f"   ✅ Cloudinary upload réussi : {public_id}")
            
            # Mise à jour dans la base Render PostgreSQL
            update_query = f"UPDATE {table} SET pdf = %s WHERE id = %s"
            cur.execute(update_query, (public_id, obj_id))
            conn.commit()
            logger.info(f"   ✅ PostgreSQL Render mis à jour : {table}.id={obj_id} -> {public_id}")
            success_count += 1
            
        except Exception as e:
            logger.error(f"   ❌ Erreur pour ID {obj_id} ({file_path.name}): {e}")
            conn.rollback()
            error_count += 1
            
    conn.close()
    
    logger.info("\n" + "="*50)
    logger.info("RÉSUMÉ DE LA SYNCHRONISATION")
    logger.info(f"Succès : {success_count}")
    logger.info(f"Erreurs : {error_count}")
    logger.info("="*50)

if __name__ == '__main__':
    main()
