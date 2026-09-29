from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from courses.admin_views import admin_exam_results_recap_view

admin.site.site_header = "SUJETLigne — administration"
admin.site.site_title = "SUJETLigne"
admin.site.index_title = "Tableau de bord"

from django.views.generic import RedirectView

urlpatterns = [
    path(
        "admin/exam-results-recap/",
        admin.site.admin_view(admin_exam_results_recap_view),
        name="admin_exam_results_recap",
    ),
    path("admin/", admin.site.urls),
    # Raccourcis courants évitant les erreurs 404
    path("connexion/", RedirectView.as_view(pattern_name="accounts:login", permanent=False)),
    path("login/", RedirectView.as_view(pattern_name="accounts:login", permanent=False)),
    path("inscription/", RedirectView.as_view(pattern_name="accounts:signup", permanent=False)),
    path("deconnexion/", RedirectView.as_view(pattern_name="accounts:logout", permanent=False)),
    path("formateur/", RedirectView.as_view(pattern_name="courses:formateur_dashboard", permanent=False)),
    path("cours/", RedirectView.as_view(pattern_name="courses:course_list", permanent=False)),
    path("comptes/", include("accounts.urls")),
    path("", include("courses.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns+=staticfiles_urlpatterns()