from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.forms import UserCreationForm

from .models import Book, BookReview, Loan

User = get_user_model()


class ReaderRegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Nome", max_length=150)
    last_name = forms.CharField(label="Sobrenome", max_length=150)
    email = forms.EmailField(label="E-mail", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(
            ("username", "first_name", "last_name", "email", "password1", "password2")
        )
        self.fields["username"].label = "Nome de usuário"
        self.fields["password1"].label = "Senha"
        self.fields["password2"].label = "Confirme a senha"

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email


class ReaderProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        labels = {
            "first_name": "Nome",
            "last_name": "Sobrenome",
            "email": "E-mail",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.get("instance")
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email


class ReaderPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Senha atual"
        self.fields["new_password1"].label = "Nova senha"
        self.fields["new_password2"].label = "Confirme a nova senha"


class BookReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        label="Sua avaliação",
        choices=(
            (5, "5 estrelas"),
            (4, "4 estrelas"),
            (3, "3 estrelas"),
            (2, "2 estrelas"),
            (1, "1 estrela"),
        ),
        coerce=int,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = BookReview
        fields = ("rating", "comment")
        labels = {"comment": "Comentário"}
        widgets = {
            "comment": forms.Textarea(
                attrs={
                    "rows": 5,
                    "maxlength": 2000,
                    "placeholder": "Conte o que achou deste livro...",
                }
            ),
        }


class ReaderLoanForm(forms.Form):
    book = forms.ModelChoiceField(
        queryset=Book.objects.none(),
        label="Livro",
        empty_label="Selecione um livro",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["book"].queryset = Book.objects.filter(
            available_copies__gt=0
        ).order_by("title")


class ReaderChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        full_name = user.get_full_name().strip()
        if full_name:
            return f"{full_name} ({user.get_username()})"
        return user.get_username()


class AdminLoanForm(ReaderLoanForm):
    reader = ReaderChoiceField(
        queryset=User.objects.none(),
        label="Leitor",
        empty_label="Selecione um leitor",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reader"].queryset = User.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name", "username")
        self.order_fields(("reader", "book"))


class ActiveLoanChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, loan):
        due_date = loan.due_date.strftime("%d/%m/%Y")
        reader = loan.reader.get_full_name() or loan.reader.username
        return f"{loan.book.title} — {reader} (previsto para {due_date})"


class EarlyReturnForm(forms.Form):
    loan = ActiveLoanChoiceField(
        queryset=Loan.objects.none(),
        label="Empréstimo ativo",
        empty_label="Selecione um empréstimo",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["loan"].queryset = (
            Loan.objects.filter(returned_at__isnull=True)
            .select_related("book", "reader")
            .order_by("due_date", "book__title")
        )


class LoanReportFilterForm(forms.Form):
    STATUS_CHOICES = (
        ("all", "Todas as situações"),
        ("active", "Em andamento"),
        ("overdue", "Atrasados"),
        ("returned", "Devolvidos"),
    )

    q = forms.CharField(
        label="Buscar leitor ou livro",
        required=False,
        max_length=100,
        widget=forms.SearchInput(attrs={"placeholder": "Nome, usuário ou título"}),
    )
    status = forms.ChoiceField(
        label="Situação",
        choices=STATUS_CHOICES,
        required=False,
        initial="all",
    )
    start_date = forms.DateField(
        label="Emprestado a partir de",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        label="Emprestado até",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error(
                "end_date",
                "A data final precisa ser igual ou posterior à data inicial.",
            )
        return cleaned_data
