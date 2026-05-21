from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.CustomLoginView.as_view(), name="login"),
    path("deconnexion/", views.CustomLogoutView.as_view(), name="logout"),
    path("inscription/", views.signup, name="signup"),
    path("mot-de-passe/", views.password_change, name="password_change"),
    path("mot-de-passe/oublie/", views.password_reset_request, name="password_reset"),
]
