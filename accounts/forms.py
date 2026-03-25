from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class LoginForm(forms.Form):
    email = forms.EmailField(
        label='Adresse E-mail',
        widget=forms.EmailInput(attrs={
            'placeholder': 'dupont@gmail.com',
            'autocomplete': 'email',
        }),
    )
    password = forms.CharField(
        label='Mot de passe',
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        }),
    )


class RegisterForm(UserCreationForm):
    nom = forms.CharField(
        label='Nom complet',
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Jean Dupont'}),
    )
    email = forms.EmailField(
        label='Adresse E-mail',
        widget=forms.EmailInput(attrs={'placeholder': 'exemple@mail.com'}),
    )

    class Meta:
        model = User
        fields = ('nom', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs['placeholder'] = '••••••••'
        self.fields['password2'].widget.attrs['placeholder'] = '••••••••'
        self.fields['password2'].label = 'Confirmer le mot de passe'

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Un compte existe déjà avec cette adresse e-mail.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.username = self.cleaned_data['email']
        user.is_active = False  # Activé après confirmation par e-mail
        nom = self.cleaned_data.get('nom', '').strip()
        if nom:
            parts = nom.split(None, 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ''
        if commit:
            user.save()
        return user


# Taille max. upload document (octets)
DOCUMENT_IMPORT_MAX_BYTES = 8 * 1024 * 1024

ALLOWED_DOC_EXTENSIONS = (".pdf", ".doc", ".docx")


class DocumentImportForm(forms.Form):
    """Upload PDF / Word pour remplir la zone de texte d'analyse."""

    document = forms.FileField(
        label="Document",
        widget=forms.FileInput(
            attrs={
                "accept": ".pdf,.doc,.docx,application/pdf,"
                "application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        ),
    )

    def clean_document(self):
        f = self.cleaned_data["document"]
        if f.size > DOCUMENT_IMPORT_MAX_BYTES:
            raise ValidationError("Fichier trop volumineux (maximum 8 Mo).")
        name = (f.name or "").lower()
        if not any(name.endswith(ext) for ext in ALLOWED_DOC_EXTENSIONS):
            raise ValidationError("Types acceptés : PDF, Word (.doc, .docx).")
        return f
