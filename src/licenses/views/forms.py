"""Customer HTML input fields; licensing mutations remain in services."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)


class RedeemForm(forms.Form):
    license_key = forms.CharField(
        label=_("License key"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "off", "class": "font-mono"}),
    )


class DeviceNameForm(forms.Form):
    display_name = forms.CharField(
        label=_("Name"),
        strip=False,
        min_length=1,
        max_length=200,
        widget=forms.TextInput(attrs={"x-ref": "name"}),
    )
