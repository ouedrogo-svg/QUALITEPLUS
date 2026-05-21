from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm as DjangoPasswordChangeForm,
)
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.text import slugify

PASSWORD_SAME_AS_IDENTITY_MSG = (
    "Le mot de passe ne peut pas être identique à votre nom ou à votre prénom."
)


def _password_same_as_identity(password: str, last_name: str, first_name: str) -> bool:
    if not password:
        return False
    pwd = password.casefold()
    for value in (last_name, first_name):
        if value and pwd == value.strip().casefold():
            return True
    return False


def _unique_username(first_name: str, last_name: str) -> str:
    base = slugify(f"{first_name}-{last_name}") or "utilisateur"
    username = base
    n = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}-{n}"
        n += 1
    return username


class SignUpForm(forms.ModelForm):
    last_name = forms.CharField(label="Nom", max_length=150)
    first_name = forms.CharField(label="Prénom", max_length=150)
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmation du mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ("last_name", "first_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(["last_name", "first_name", "password1", "password2"])
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("Les mots de passe ne correspondent pas.")
        return password2

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        last_name = cleaned.get("last_name", "")
        first_name = cleaned.get("first_name", "")
        if password and _password_same_as_identity(password, last_name, first_name):
            self.add_error("password1", PASSWORD_SAME_AS_IDENTITY_MSG)
            return cleaned
        if password:
            user = User(
                first_name=first_name,
                last_name=last_name,
            )
            validate_password(password, user)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = _unique_username(user.first_name, user.last_name)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class NameAuthenticationForm(AuthenticationForm):
    """Le champ « username » du formulaire parent porte le nom de famille."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(["username", "password"])
        self.fields["username"].label = "Nom"
        self.fields["username"].widget.attrs.update(
            {
                "class": "form-control",
                "autocomplete": "username",
                "placeholder": "Votre nom de famille",
            }
        )
        self.fields["password"].label = "Mot de passe"
        self.fields["password"].widget.attrs.update(
            {
                "class": "form-control",
                "autocomplete": "current-password",
            }
        )

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username is not None and password:
            nom = username.strip()
            if _password_same_as_identity(password, nom, ""):
                raise ValidationError(
                    PASSWORD_SAME_AS_IDENTITY_MSG,
                    code="password_identity",
                )
            self.user_cache = authenticate(
                self.request,
                username=nom,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class PasswordChangeForm(DjangoPasswordChangeForm):
    """Changement de mot de passe pour un utilisateur connecté."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["old_password"].label = "Mot de passe actuel"
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password2"].label = "Confirmation du nouveau mot de passe"
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_new_password1(self):
        password = super().clean_new_password1()
        user = self.user
        if _password_same_as_identity(password, user.last_name, user.first_name):
            raise ValidationError(PASSWORD_SAME_AS_IDENTITY_MSG)
        return password


class PasswordResetByNameForm(forms.Form):
    """Réinitialisation sans e-mail : nom, prénom et nouveau mot de passe."""

    last_name = forms.CharField(label="Nom", max_length=150)
    first_name = forms.CharField(label="Prénom", max_length=150)
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Confirmation du nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip()

    def clean_new_password2(self):
        password1 = self.cleaned_data.get("new_password1")
        password2 = self.cleaned_data.get("new_password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("Les mots de passe ne correspondent pas.")
        return password2

    def clean(self):
        cleaned = super().clean()
        last_name = cleaned.get("last_name", "")
        first_name = cleaned.get("first_name", "")
        password = cleaned.get("new_password1")
        if not last_name or not first_name or not password:
            return cleaned

        users = User.objects.filter(
            last_name__iexact=last_name,
            first_name__iexact=first_name,
            is_active=True,
        )
        count = users.count()
        if count == 0:
            raise ValidationError(
                "Aucun compte actif ne correspond à ce nom et ce prénom."
            )
        if count > 1:
            raise ValidationError(
                "Plusieurs comptes portent ce nom et ce prénom. "
                "Contactez l’administrateur pour réinitialiser votre mot de passe."
            )
        user = users.get()
        if _password_same_as_identity(password, user.last_name, user.first_name):
            self.add_error("new_password1", PASSWORD_SAME_AS_IDENTITY_MSG)
            return cleaned
        validate_password(password, user)
        cleaned["_user"] = user
        return cleaned

    def save(self):
        user = self.cleaned_data["_user"]
        user.set_password(self.cleaned_data["new_password1"])
        user.save(update_fields=["password"])
        return user
