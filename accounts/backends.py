from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class NomBackend(ModelBackend):
    """Connexion avec le nom de famille et le mot de passe."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        nom = username.strip()
        if not nom:
            return None
        for user in User.objects.filter(last_name__iexact=nom):
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
