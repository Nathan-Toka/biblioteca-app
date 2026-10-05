from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("", views.book_list, name="livros"),
    path("livros/<int:book_id>/", views.book_detail, name="detalhe-livro"),
    path("livros/<int:book_id>/avaliar/", views.review_book, name="avaliar-livro"),
    path("cadastro/", views.register_reader, name="cadastro"),
    path("minha-conta/", views.my_account, name="minha-conta"),
    path("minha-conta/alterar-senha/", views.change_my_password, name="alterar-senha"),
    path("meus-emprestimos/", views.my_loans, name="meus-emprestimos"),
    path(
        "livros/<int:book_id>/emprestar/",
        views.request_loan,
        name="solicitar-emprestimo",
    ),
]
