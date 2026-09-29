"""
Script de migration : transférer les fichiers locaux vers Cloudinary
et mettre à jour les chemins dans la base de données.
"""

import os
import sys
import django
from pathlib import Path

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.getcwd())
django.setup()

from django.conf import settings
from courses.models import MonthlyCourseContent, MonthlyCorrection, MonthlyExam
import cloudinary
import cloudinary.uploader
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(settings.MEDIA_ROOT)


def upload_to_cloudinary(local_path: str, folder: str) -> str:
    """Upload un fichier local vers Cloudinary et retourne le chemin public."""
    try:
        result = cloudinary.uploader.upload(
            local_path,
            folder=folder,
            resource_type="raw",
            use_filename=True,
            unique_filename=False,
        )
        logger.info(f"✅ Upload réussi: {local_path} -> {result['public_id']}")
        return result['public_id']
    except Exception as e:
        logger.error(f"❌ Erreur upload {local_path}: {e}")
        return None


def migrate_monthly_course_content():
    """Migrer les fichiers MonthlyCourseContent."""
    logger.info("=== Migration MonthlyCourseContent ===")
    for obj in MonthlyCourseContent.objects.filter(pdf__isnull=False).exclude(pdf=''):
        local_path = MEDIA_ROOT / obj.pdf.name
        if local_path.exists():
            cloudinary_path = upload_to_cloudinary(str(local_path), "cours_mois")
            if cloudinary_path:
                obj.pdf.name = cloudinary_path
                obj.save(update_fields=['pdf'])
                logger.info(f"✅ Mis à jour MonthlyCourseContent {obj.id}")
        else:
            logger.warning(f"⚠️ Fichier local introuvable: {local_path}")


def migrate_monthly_correction():
    """Migrer les fichiers MonthlyCorrection."""
    logger.info("=== Migration MonthlyCorrection ===")
    for obj in MonthlyCorrection.objects.filter(pdf__isnull=False).exclude(pdf=''):
        local_path = MEDIA_ROOT / obj.pdf.name
        if local_path.exists():
            cloudinary_path = upload_to_cloudinary(str(local_path), "corrections")
            if cloudinary_path:
                obj.pdf.name = cloudinary_path
                obj.save(update_fields=['pdf'])
                logger.info(f"✅ Mis à jour MonthlyCorrection {obj.id}")
        else:
            logger.warning(f"⚠️ Fichier local introuvable: {local_path}")


def migrate_monthly_exam():
    """Migrer les fichiers MonthlyExam."""
    logger.info("=== Migration MonthlyExam ===")
    for obj in MonthlyExam.objects.filter(pdf__isnull=False).exclude(pdf=''):
        local_path = MEDIA_ROOT / obj.pdf.name
        if local_path.exists():
            cloudinary_path = upload_to_cloudinary(str(local_path), "examens")
            if cloudinary_path:
                obj.pdf.name = cloudinary_path
                obj.save(update_fields=['pdf'])
                logger.info(f"✅ Mis à jour MonthlyExam {obj.id}")
        else:
            logger.warning(f"⚠️ Fichier local introuvable: {local_path}")


def main():
    logger.info("Début de la migration vers Cloudinary...")
    logger.info(f"Cloudinary configuré: {bool(settings.CLOUDINARY_STORAGE.get('CLOUD_NAME'))}")
    
    # Configuration explicite de Cloudinary
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_STORAGE.get('CLOUD_NAME'),
        api_key=settings.CLOUDINARY_STORAGE.get('API_KEY'),
        api_secret=settings.CLOUDINARY_STORAGE.get('API_SECRET'),
        secure=True
    )
    
    if not settings.CLOUDINARY_STORAGE.get('CLOUD_NAME'):
        logger.error("❌ Cloudinary n'est pas configuré. Vérifiez les variables d'environnement.")
        return
    
    migrate_monthly_course_content()
    migrate_monthly_correction()
    migrate_monthly_exam()
    
    logger.info("=== Migration terminée ===")


if __name__ == '__main__':
    main()
