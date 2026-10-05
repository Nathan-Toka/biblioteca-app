import csv
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.admin.sites import site
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from .forms import (
    AdminLoanForm,
    BookReviewForm,
    EarlyReturnForm,
    LoanReportFilterForm,
    ReaderPasswordChangeForm,
    ReaderProfileForm,
    ReaderRegistrationForm,
)
from .models import Book, BookReview, Loan
from .services import BookUnavailable, create_loan, register_return


def book_list(request):
    books = Book.objects.annotate(
        review_count=Count("reviews"),
        average_rating=Avg("reviews__rating"),
    )
    query = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "").strip()
    sort_fields = {
        "title": ("title", "author"),
        "author": ("author", "title"),
    }
    selected_sort = request.GET.get("sort", "title")
    if selected_sort not in sort_fields:
        selected_sort = "title"

    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(category__icontains=query)
        )
    if selected_category:
        books = books.filter(category=selected_category)
    books = books.order_by(*sort_fields[selected_sort])

    categories = (
        Book.objects.exclude(category="")
        .order_by("category")
        .values_list("category", flat=True)
        .distinct()
    )
    return render(
        request,
        "catalogo/book_list.html",
        {
            "books": books,
            "query": query,
            "categories": categories,
            "selected_category": selected_category,
            "selected_sort": selected_sort,
        },
    )


def book_detail(request, book_id):
    book = get_object_or_404(Book, pk=book_id)
    reviews = book.reviews.select_related("reader")
    review_count = reviews.count()
    average_rating = reviews.aggregate(average=Avg("rating"))["average"]
    reader_review = None
    review_form = None
    if request.user.is_authenticated:
        reader_review = reviews.filter(reader=request.user).first()
        review_form = BookReviewForm(instance=reader_review)
    return render(
        request,
        "catalogo/book_detail.html",
        {
            "book": book,
            "reviews": reviews,
            "review_count": review_count,
            "average_rating": average_rating,
            "reader_review": reader_review,
            "review_form": review_form,
        },
    )


@login_required
def review_book(request, book_id):
    if request.method != "POST":
        return redirect("catalogo:detalhe-livro", book_id=book_id)
    book = get_object_or_404(Book, pk=book_id)
    form = BookReviewForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            review, created = BookReview.objects.update_or_create(
                book=book,
                reader=request.user,
                defaults=form.cleaned_data,
            )
        if created:
            messages.success(request, "Sua avaliação foi publicada.")
        else:
            messages.success(request, "Sua avaliação foi atualizada.")
        return redirect(
            f"{reverse('catalogo:detalhe-livro', args=[book.pk])}#avaliacoes"
        )

    reviews = book.reviews.select_related("reader")
    review_count = reviews.count()
    average_rating = reviews.aggregate(average=Avg("rating"))["average"]
    reader_review = reviews.filter(reader=request.user).first()
    context = {
        "book": book,
        "reviews": reviews,
        "review_count": review_count,
        "average_rating": average_rating,
        "reader_review": reader_review,
        "review_form": form,
    }
    return render(request, "catalogo/book_detail.html", context, status=400)


def register_reader(request):
    if request.user.is_authenticated:
        return redirect("catalogo:livros")
    next_url = request.POST.get("next") or request.GET.get("next", "")
    form = ReaderRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reader = form.save()
        login(request, reader)
        messages.success(request, "Cadastro realizado. Boas-vindas à biblioteca!")
        if url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("catalogo:livros")
    return render(
        request,
        "registration/signup.html",
        {"form": form, "next": next_url},
    )


@login_required
def request_loan(request, book_id):
    if request.method != "POST":
        messages.error(request, "Use o botão de empréstimo para enviar a solicitação.")
        return redirect("catalogo:livros")

    book = get_object_or_404(Book, pk=book_id)
    try:
        loan = create_loan(reader=request.user, book_id=book.pk)
    except BookUnavailable as error:
        messages.warning(request, str(error))
    else:
        messages.success(
            request,
            f"Empréstimo confirmado. Devolva “{loan.book.title}” até "
            f"{loan.due_date.strftime('%d/%m/%Y')}.",
        )
    return redirect("catalogo:livros")


@login_required
def my_loans(request):
    loans = Loan.objects.filter(reader=request.user).select_related("book")
    active_loans = loans.filter(returned_at__isnull=True)
    today = timezone.localdate()
    upcoming_deadline = today + timedelta(days=7)
    overdue_loans = active_loans.filter(due_date__lt=today)
    upcoming_loans = active_loans.filter(
        due_date__gte=today,
        due_date__lte=upcoming_deadline,
    )
    return render(
        request,
        "catalogo/my_loans.html",
        {
            "loans": loans,
            "today": today,
            "overdue_loans": overdue_loans,
            "upcoming_loans": upcoming_loans,
            "upcoming_deadline": upcoming_deadline,
            "active_count": active_loans.count(),
            "overdue_count": active_loans.filter(due_date__lt=today).count(),
            "returned_count": loans.filter(returned_at__isnull=False).count(),
        },
    )


@login_required
def my_account(request):
    form = ReaderProfileForm(
        request.POST or None,
        instance=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Seus dados foram atualizados.")
        return redirect("catalogo:minha-conta")
    return render(
        request,
        "catalogo/my_account.html",
        {"form": form},
    )


@login_required
def change_my_password(request):
    form = ReaderPasswordChangeForm(
        user=request.user,
        data=request.POST or None,
    )
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Sua senha foi alterada com segurança.")
        return redirect("catalogo:minha-conta")
    return render(
        request,
        "catalogo/change_password.html",
        {"form": form},
    )


def admin_register_loan(request):
    if not request.user.is_superuser and not request.user.has_perm("catalogo.view_loan"):
        raise PermissionDenied
    action = request.POST.get("action") if request.method == "POST" else None
    form = AdminLoanForm(request.POST if action == "loan" else None)
    return_form = EarlyReturnForm(
        request.POST if action == "return" else None,
        prefix="return",
    )
    if request.method == "POST" and action == "return":
        if return_form.is_valid():
            loan = return_form.cleaned_data["loan"]
            if register_return(loan_id=loan.pk):
                messages.success(
                    request,
                    f"Devolução de “{loan.book.title}” registrada antes do prazo previsto.",
                )
            else:
                messages.warning(request, "Este empréstimo já foi devolvido.")
            return redirect("admin-register-loan")
    elif request.method == "POST" and action == "loan" and form.is_valid():
        try:
            loan = create_loan(
                reader=form.cleaned_data["reader"],
                book_id=form.cleaned_data["book"].pk,
            )
        except BookUnavailable as error:
            form.add_error("book", str(error))
        else:
            messages.success(
                request,
                f"Empréstimo de “{loan.book.title}” registrado para "
                f"{loan.reader.get_full_name() or loan.reader.username}.",
            )
            return redirect("admin:catalogo_loan_changelist")
    context = {
        **site.each_context(request),
        "form": form,
        "return_form": return_form,
        "title": "Registrar entrega presencial",
    }
    return render(request, "admin/catalogo/register_loan.html", context)


def loan_report(request):
    if not request.user.is_active or not (
        request.user.is_superuser or request.user.has_perm("catalogo.view_loan")
    ):
        raise PermissionDenied

    form = LoanReportFilterForm(request.GET or None)
    today = timezone.localdate()
    loans = Loan.objects.select_related("book", "reader")
    export_csv = request.GET.get("export") == "csv"
    export_error = ""

    if form.is_valid():
        filters = form.cleaned_data
        if filters["q"]:
            loans = loans.filter(
                Q(book__title__icontains=filters["q"])
                | Q(reader__username__icontains=filters["q"])
                | Q(reader__first_name__icontains=filters["q"])
                | Q(reader__last_name__icontains=filters["q"])
            )
        if filters["status"] == "active":
            loans = loans.filter(returned_at__isnull=True)
        elif filters["status"] == "overdue":
            loans = loans.filter(returned_at__isnull=True, due_date__lt=today)
        elif filters["status"] == "returned":
            loans = loans.filter(returned_at__isnull=False)
        if filters["start_date"]:
            loans = loans.filter(borrowed_at__date__gte=filters["start_date"])
        if filters["end_date"]:
            loans = loans.filter(borrowed_at__date__lte=filters["end_date"])
    else:
        if export_csv:
            export_error = "Corrija os filtros destacados antes de exportar o relatório."
        loans = loans.none()

    loans = loans.order_by("-borrowed_at", "book__title")
    total_count = loans.count()
    active_count = loans.filter(returned_at__isnull=True).count()
    overdue_count = loans.filter(
        returned_at__isnull=True,
        due_date__lt=today,
    ).count()
    returned_count = loans.filter(returned_at__isnull=False).count()

    if export_csv and form.is_valid():
        return export_loan_report_csv(loans, today)

    page_obj = Paginator(loans, 50).get_page(request.GET.get("page"))
    context = {
        **site.each_context(request),
        "title": "Relatório de empréstimos",
        "form": form,
        "page_obj": page_obj,
        "total_count": total_count,
        "active_count": active_count,
        "overdue_count": overdue_count,
        "returned_count": returned_count,
        "today": today,
        "export_error": export_error,
    }
    return render(request, "admin/catalogo/reports/loans.html", context)


def export_loan_report_csv(loans, today: date):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")
    response["Content-Disposition"] = (
        f'attachment; filename="relatorio-emprestimos-{today:%Y%m%d}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        ["Leitor", "Usuário", "Livro", "Emprestado em", "Devolução prevista", "Devolvido em", "Situação"]
    )
    for loan in loans.iterator():
        if loan.returned_at:
            status = "Devolvido"
        elif loan.due_date < today:
            status = "Atrasado"
        else:
            status = "Em andamento"
        values = [
            loan.reader.get_full_name() or loan.reader.username,
            loan.reader.username,
            loan.book.title,
            timezone.localtime(loan.borrowed_at).strftime("%d/%m/%Y %H:%M"),
            loan.due_date.strftime("%d/%m/%Y"),
            (
                timezone.localtime(loan.returned_at).strftime("%d/%m/%Y %H:%M")
                if loan.returned_at
                else ""
            ),
            status,
        ]
        writer.writerow([safe_csv_cell(value) for value in values])
    return response


def safe_csv_cell(value):
    value = "" if value is None else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value
