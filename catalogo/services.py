from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Book, Loan


class BookUnavailable(Exception):
    """O último exemplar foi emprestado ou não está disponível."""


@transaction.atomic
def create_loan(*, reader, book_id):
    reserved = Book.objects.filter(
        pk=book_id,
        available_copies__gt=0,
    ).update(available_copies=F("available_copies") - 1)
    if reserved != 1:
        raise BookUnavailable("Não há exemplar disponível. Procure o administrador da biblioteca.")

    book = Book.objects.get(pk=book_id)
    today = timezone.localdate()
    return Loan.objects.create(
        reader=reader,
        book=book,
        borrowed_at=timezone.now(),
        due_date=today + timedelta(days=30),
    )


@transaction.atomic
def register_return(*, loan_id):
    loan = Loan.objects.get(pk=loan_id)
    marked = Loan.objects.filter(
        pk=loan_id,
        returned_at__isnull=True,
    ).update(returned_at=timezone.now())
    if marked != 1:
        return False

    restored = Book.objects.filter(
        pk=loan.book_id,
        available_copies__lt=F("total_copies"),
    ).update(available_copies=F("available_copies") + 1)
    if restored != 1:
        raise RuntimeError("Não foi possível atualizar a disponibilidade do exemplar devolvido.")
    return True
