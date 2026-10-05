from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .validators import validate_cover_size


class Book(models.Model):
    title = models.CharField("título", max_length=200)
    author = models.CharField("autor", max_length=160)
    category = models.CharField("categoria", max_length=100, blank=True)
    description = models.TextField("descrição", blank=True)
    cover_image = models.ImageField(
        "imagem da capa",
        upload_to="capas/",
        blank=True,
        validators=[validate_cover_size],
        help_text="Opcional. Envie uma imagem JPG, PNG ou WebP de até 5 MB.",
    )
    total_copies = models.PositiveIntegerField("exemplares totais", default=1)
    available_copies = models.PositiveIntegerField("exemplares disponíveis", default=1)
    shelf_location = models.CharField("localização na estante", max_length=120, blank=True)
    created_at = models.DateTimeField("cadastrado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["title", "author"]
        verbose_name = "livro"
        verbose_name_plural = "livros"
        constraints = [
            models.CheckConstraint(
                condition=Q(available_copies__lte=F("total_copies")),
                name="available_copies_not_over_total",
            ),
        ]

    def __str__(self):
        return f"{self.title} — {self.author}"

    def clean(self):
        super().clean()
        if self.available_copies > self.total_copies:
            raise ValidationError(
                {"available_copies": "A quantidade disponível não pode superar o total."}
            )
        if self.pk:
            active_loans = self.loans.filter(returned_at__isnull=True).count()
            copies_outside_shelf = self.total_copies - self.available_copies
            if copies_outside_shelf < active_loans:
                raise ValidationError(
                    "O total e a disponibilidade não podem deixar empréstimos ativos sem exemplar."
                )


class Loan(models.Model):
    reader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="library_loans",
        verbose_name="leitor",
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.PROTECT,
        related_name="loans",
        verbose_name="livro",
    )
    borrowed_at = models.DateTimeField("emprestado em", default=timezone.now)
    due_date = models.DateField("devolução prevista")
    returned_at = models.DateTimeField("devolvido em", null=True, blank=True)

    class Meta:
        ordering = ["returned_at", "due_date", "book__title"]
        verbose_name = "empréstimo"
        verbose_name_plural = "empréstimos"

    def __str__(self):
        return f"{self.book} — {self.reader}"

    @property
    def is_overdue(self):
        return self.returned_at is None and self.due_date < timezone.localdate()

    @property
    def is_active(self):
        return self.returned_at is None


class BookReview(models.Model):
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="livro",
    )
    reader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="book_reviews",
        verbose_name="leitor",
    )
    rating = models.PositiveSmallIntegerField("avaliação")
    comment = models.TextField("comentário", max_length=2000)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]
        verbose_name = "avaliação de livro"
        verbose_name_plural = "avaliações de livros"
        constraints = [
            models.UniqueConstraint(
                fields=["book", "reader"],
                name="one_review_per_reader_per_book",
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5),
                name="book_review_rating_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"{self.book} — {self.rating}/5 ({self.reader})"
