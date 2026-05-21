from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy

from .forms import (
    NameAuthenticationForm,
    PasswordChangeForm,
    PasswordResetByNameForm,
    SignUpForm,
)

LOGIN_BACKEND = settings.AUTHENTICATION_BACKENDS[0]


def _login_success_url(user):
    """Après connexion : accueil formateur si rôle formateur, sinon accueil public."""
    from courses.formateur_permissions import (
        user_can_access_content_formateur_space,
        user_can_access_full_formateur_space,
    )

    if user_can_access_full_formateur_space(user):
        return reverse("courses:formateur_dashboard")
    if user_can_access_content_formateur_space(user):
        return reverse("courses:formateur_contenu_dashboard")
    return reverse(settings.LOGIN_REDIRECT_URL)


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = NameAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        return _login_success_url(self.request.user)


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy("courses:home")


def signup(request):
    if request.user.is_authenticated:
        return redirect("courses:home")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend=LOGIN_BACKEND)
            return redirect("courses:home")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Votre mot de passe a été modifié avec succès.")
            return redirect("courses:home")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "accounts/password_change.html", {"form": form})


def password_reset_request(request):
    if request.user.is_authenticated:
        return redirect("courses:home")
    if request.method == "POST":
        form = PasswordResetByNameForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Votre mot de passe a été réinitialisé. Connectez-vous avec votre nom.",
            )
            return redirect("accounts:login")
    else:
        form = PasswordResetByNameForm()
    return render(request, "accounts/password_reset_request.html", {"form": form})
