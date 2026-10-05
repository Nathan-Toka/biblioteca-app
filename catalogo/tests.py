import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import AdminLoanForm
from .models import Book, BookReview, Loan
from .services import BookUnavailable, create_loan, register_return
from .validators import MAX_COVER_SIZE, validate_cover_size

User = get_user_model()


class LibraryWorkflowTests(TestCase):
    def setUp(self):
        self.reader = User.objects.create_user(
            username="leitor",
            password="Senha-segura-2026!",
            first_name="Leitor",
        )
        self.book = Book.objects.create(
            title="O livro da escola",
            author="Autora Exemplo",
            category="Literatura",
            total_copies=1,
            available_copies=1,
            shelf_location="A-01",
        )

    def test_reader_request_confirms_loan_and_sets_thirty_day_deadline(self):
        self.client.force_login(self.reader)

        response = self.client.post(
            reverse("catalogo:solicitar-emprestimo", args=[self.book.pk])
        )

        loan = Loan.objects.get(reader=self.reader, book=self.book)
        self.book.refresh_from_db()
        self.assertRedirects(response, reverse("catalogo:livros"))
        self.assertEqual(loan.due_date, timezone.localdate() + timedelta(days=30))
        self.assertEqual(self.book.available_copies, 0)

    def test_unavailable_book_does_not_create_loan(self):
        self.book.available_copies = 0
        self.book.save()
        self.client.force_login(self.reader)

        response = self.client.post(
            reverse("catalogo:solicitar-emprestimo", args=[self.book.pk])
        )
        catalog_response = self.client.get(reverse("catalogo:livros"))

        self.assertRedirects(response, reverse("catalogo:livros"))
        self.assertFalse(Loan.objects.exists())
        self.assertEqual(Book.objects.get(pk=self.book.pk).available_copies, 0)
        self.assertContains(catalog_response, "Procure o administrador")

    def test_service_rejects_unavailable_copy_without_mutating_inventory(self):
        self.book.available_copies = 0
        self.book.save()

        with self.assertRaises(BookUnavailable):
            create_loan(reader=self.reader, book_id=self.book.pk)

        self.assertEqual(Loan.objects.count(), 0)
        self.assertEqual(Book.objects.get(pk=self.book.pk).available_copies, 0)

    def test_return_restores_inventory_only_once(self):
        loan = create_loan(reader=self.reader, book_id=self.book.pk)

        self.assertTrue(register_return(loan_id=loan.pk))
        self.assertFalse(register_return(loan_id=loan.pk))
        self.book.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)
        self.assertIsNotNone(loan.returned_at)

    def test_reader_registration_creates_account_and_logs_in(self):
        response = self.client.post(
            reverse("catalogo:cadastro"),
            {
                "username": "nova-leitora",
                "first_name": "Nova",
                "last_name": "Leitora",
                "email": "nova@example.com",
                "password1": "UmaSenha-forte-2026!",
                "password2": "UmaSenha-forte-2026!",
            },
        )

        self.assertRedirects(response, reverse("catalogo:livros"))
        self.assertTrue(User.objects.filter(username="nova-leitora").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_reader_registration_returns_to_book_requested_before_login(self):
        detail_url = reverse("catalogo:detalhe-livro", args=[self.book.pk])
        login_response = self.client.get(
            reverse("login"),
            {"next": detail_url},
        )
        self.assertContains(
            login_response,
            f'href="{reverse("catalogo:cadastro")}?next={detail_url}"',
        )

        signup_response = self.client.get(
            reverse("catalogo:cadastro"),
            {"next": detail_url},
        )
        self.assertContains(signup_response, f'value="{detail_url}"')

        response = self.client.post(
            f"{reverse('catalogo:cadastro')}?next={detail_url}",
            {
                "username": "nova-leitora",
                "first_name": "Nova",
                "last_name": "Leitora",
                "email": "nova@example.com",
                "password1": "UmaSenha-forte-2026!",
                "password2": "UmaSenha-forte-2026!",
                "next": detail_url,
            },
        )

        self.assertRedirects(response, detail_url)
        self.assertIn("_auth_user_id", self.client.session)

    def test_reader_registration_rejects_external_next_url(self):
        response = self.client.post(
            reverse("catalogo:cadastro"),
            {
                "username": "nova-leitora",
                "first_name": "Nova",
                "last_name": "Leitora",
                "email": "nova@example.com",
                "password1": "UmaSenha-forte-2026!",
                "password2": "UmaSenha-forte-2026!",
                "next": "https://malicious.example/",
            },
        )

        self.assertRedirects(response, reverse("catalogo:livros"))

    def test_login_and_registration_pages_render(self):
        login_response = self.client.get(reverse("login"))
        signup_response = self.client.get(reverse("catalogo:cadastro"))

        self.assertContains(login_response, "Entrar na biblioteca")
        self.assertContains(signup_response, "Crie sua conta")

    def test_reader_can_log_in_with_registered_password(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.reader.username, "password": "Senha-segura-2026!"},
        )

        self.assertRedirects(response, reverse("catalogo:livros"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_authenticated_reader_can_log_out_with_csrf_protection_enabled(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.reader)

        page = client.get(reverse("catalogo:livros"))
        csrf_token = page.context["csrf_token"]
        response = client.post(reverse("logout"), {"csrfmiddlewaretoken": csrf_token})

        self.assertRedirects(response, reverse("catalogo:livros"))
        self.assertNotIn("_auth_user_id", client.session)

    def test_reader_can_update_own_profile_without_changing_username(self):
        other_reader = User.objects.create_user(
            username="outra-leitora",
            password="Outra-senha-segura-2026!",
            first_name="Outra",
            email="outra@example.com",
        )
        self.client.force_login(self.reader)

        response = self.client.post(
            reverse("catalogo:minha-conta"),
            {
                "first_name": "Leitora Atualizada",
                "last_name": "Silva",
                "email": "leitora@example.com",
                "username": "nome-alterado",
            },
        )

        self.reader.refresh_from_db()
        other_reader.refresh_from_db()
        self.assertRedirects(response, reverse("catalogo:minha-conta"))
        self.assertEqual(self.reader.username, "leitor")
        self.assertEqual(self.reader.first_name, "Leitora Atualizada")
        self.assertEqual(self.reader.last_name, "Silva")
        self.assertEqual(self.reader.email, "leitora@example.com")
        self.assertEqual(other_reader.first_name, "Outra")
        self.assertEqual(other_reader.email, "outra@example.com")

    def test_reader_profile_rejects_an_email_used_by_another_account(self):
        User.objects.create_user(
            username="outra-leitora",
            password="Outra-senha-segura-2026!",
            email="ocupado@example.com",
        )
        self.client.force_login(self.reader)

        response = self.client.post(
            reverse("catalogo:minha-conta"),
            {
                "first_name": "Leitor",
                "last_name": "Atualizado",
                "email": "OCUPADO@example.com",
            },
        )

        self.reader.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.reader.email, "")
        self.assertContains(response, "Já existe uma conta com este e-mail")

    def test_reader_account_and_password_pages_require_authentication(self):
        for route in ("catalogo:minha-conta", "catalogo:alterar-senha"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertRedirects(
                    response,
                    f"{reverse('login')}?next={reverse(route)}",
                )

    def test_reader_can_change_password_and_stays_signed_in(self):
        self.client.force_login(self.reader)

        response = self.client.post(
            reverse("catalogo:alterar-senha"),
            {
                "old_password": "Senha-segura-2026!",
                "new_password1": "Nova-senha-segura-2026!",
                "new_password2": "Nova-senha-segura-2026!",
            },
        )

        self.reader.refresh_from_db()
        self.assertRedirects(response, reverse("catalogo:minha-conta"))
        self.assertTrue(self.reader.check_password("Nova-senha-segura-2026!"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_reader_cannot_change_password_without_current_password(self):
        self.client.force_login(self.reader)

        response = self.client.post(
            reverse("catalogo:alterar-senha"),
            {
                "old_password": "senha-incorreta",
                "new_password1": "Nova-senha-segura-2026!",
                "new_password2": "Nova-senha-segura-2026!",
            },
        )

        self.reader.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.reader.check_password("Senha-segura-2026!"))
        self.assertContains(response, "A senha antiga foi digitada incorretamente")

    def test_reader_dashboard_shows_summary_and_current_navigation(self):
        self.book.total_copies = 3
        self.book.available_copies = 3
        self.book.save()
        overdue_loan = create_loan(reader=self.reader, book_id=self.book.pk)
        overdue_loan.due_date = timezone.localdate() - timedelta(days=1)
        overdue_loan.save(update_fields=["due_date"])
        returned_loan = create_loan(reader=self.reader, book_id=self.book.pk)
        register_return(loan_id=returned_loan.pk)
        self.client.force_login(self.reader)

        response = self.client.get(reverse("catalogo:meus-emprestimos"))

        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, "/static/catalogo.css?v=8")
        self.assertContains(response, "Leitor")
        self.assertContains(response, 'class="summary-number">1</span>', count=3)
        self.assertContains(response, "Atrasados")
        self.assertContains(response, "Devolvidos")

    def test_reader_dashboard_warns_about_overdue_and_next_seven_day_loans(self):
        today = timezone.localdate()
        loans = []
        for title in ("Livro atrasado", "Livro vence em sete dias", "Livro vence depois"):
            book = Book.objects.create(
                title=title,
                author="Autora",
                total_copies=1,
                available_copies=1,
            )
            loans.append(create_loan(reader=self.reader, book_id=book.pk))

        loans[0].due_date = today - timedelta(days=1)
        loans[0].save(update_fields=["due_date"])
        loans[1].due_date = today + timedelta(days=7)
        loans[1].save(update_fields=["due_date"])
        loans[2].due_date = today + timedelta(days=8)
        loans[2].save(update_fields=["due_date"])
        self.client.force_login(self.reader)

        response = self.client.get(reverse("catalogo:meus-emprestimos"))

        self.assertEqual(
            [loan.pk for loan in response.context["overdue_loans"]],
            [loans[0].pk],
        )
        self.assertEqual(
            [loan.pk for loan in response.context["upcoming_loans"]],
            [loans[1].pk],
        )
        self.assertNotIn(
            loans[2].pk,
            [loan.pk for loan in response.context["upcoming_loans"]],
        )
        self.assertContains(response, "Você tem devoluções atrasadas")
        self.assertContains(response, "Prazo de devolução se aproximando")
        self.assertContains(response, "Livro vence em sete dias")

    def test_catalog_filters_books_by_category_and_search_term(self):
        science_book = Book.objects.create(
            title="Ciência para todos",
            author="Autora Nova",
            category="Ciência",
            total_copies=1,
            available_copies=1,
        )
        Book.objects.create(
            title="Outro livro de ciência",
            author="Outro Autor",
            category="Ciência",
            total_copies=1,
            available_copies=1,
        )

        response = self.client.get(
            reverse("catalogo:livros"),
            {"category": "Ciência", "q": "para todos"},
        )

        self.assertEqual(
            [book.pk for book in response.context["books"]],
            [science_book.pk],
        )
        self.assertContains(response, "Todas as categorias")
        self.assertContains(response, "Limpar filtros")

    def test_catalog_sorts_by_author_and_defaults_invalid_sort_to_title(self):
        third_book = Book.objects.create(
            title="Zebra",
            author="Ana",
            category="Literatura",
            total_copies=1,
            available_copies=1,
        )
        first_book = Book.objects.create(
            title="Abacate",
            author="Zeca",
            category="Literatura",
            total_copies=1,
            available_copies=1,
        )

        author_response = self.client.get(
            reverse("catalogo:livros"),
            {"category": "Literatura", "sort": "author"},
        )
        invalid_sort_response = self.client.get(
            reverse("catalogo:livros"),
            {"category": "Literatura", "sort": "invalid"},
        )

        self.assertEqual(
            [book.pk for book in author_response.context["books"]],
            [third_book.pk, self.book.pk, first_book.pk],
        )
        self.assertEqual(
            [book.title for book in invalid_sort_response.context["books"]],
            ["Abacate", "O livro da escola", "Zebra"],
        )

    def test_book_detail_shows_description_location_and_loan_action(self):
        self.book.description = "Uma história sobre leitura.\nPara toda a escola."
        self.book.save()
        self.client.force_login(self.reader)

        response = self.client.get(
            reverse("catalogo:detalhe-livro", args=[self.book.pk])
        )

        self.assertContains(response, "Uma história sobre leitura.")
        self.assertContains(response, "Para toda a escola.")
        self.assertContains(response, "A-01")
        self.assertContains(response, "1 de 1")
        self.assertContains(response, "Solicitar empréstimo")
        self.assertContains(response, reverse("catalogo:livros"))

    def test_anonymous_reader_can_view_reviews_but_must_sign_in_to_submit(self):
        detail_url = reverse("catalogo:detalhe-livro", args=[self.book.pk])
        response = self.client.get(detail_url)
        submit_response = self.client.post(
            reverse("catalogo:avaliar-livro", args=[self.book.pk]),
            {"rating": 5, "comment": "Adorei este livro."},
        )

        self.assertContains(response, "Este livro ainda não recebeu avaliações")
        self.assertContains(response, "Entre na sua conta para avaliar este livro.")
        self.assertRedirects(
            submit_response,
            f"{reverse('login')}?next={reverse('catalogo:avaliar-livro', args=[self.book.pk])}",
        )
        self.assertFalse(BookReview.objects.exists())

    def test_reader_can_create_and_edit_one_review_for_a_book(self):
        self.client.force_login(self.reader)
        review_url = reverse("catalogo:avaliar-livro", args=[self.book.pk])

        create_response = self.client.post(
            review_url,
            {"rating": 4, "comment": "Gostei muito da história."},
        )
        review = BookReview.objects.get(book=self.book, reader=self.reader)
        first_review_id = review.pk
        detail = self.client.get(reverse("catalogo:detalhe-livro", args=[self.book.pk]))
        update_response = self.client.post(
            review_url,
            {"rating": 5, "comment": "Gostei ainda mais na releitura."},
        )

        review.refresh_from_db()
        self.assertRedirects(
            create_response,
            f"{reverse('catalogo:detalhe-livro', args=[self.book.pk])}#avaliacoes",
        )
        self.assertContains(detail, "4,0")
        self.assertContains(detail, "Gostei muito da história.")
        self.assertContains(detail, "Edite sua avaliação")
        self.assertRedirects(
            update_response,
            f"{reverse('catalogo:detalhe-livro', args=[self.book.pk])}#avaliacoes",
        )
        self.assertEqual(review.pk, first_review_id)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Gostei ainda mais na releitura.")
        self.assertEqual(BookReview.objects.filter(book=self.book).count(), 1)

    def test_review_rating_must_be_between_one_and_five(self):
        self.client.force_login(self.reader)
        review_url = reverse("catalogo:avaliar-livro", args=[self.book.pk])

        for rating in (0, 6, "invalid"):
            with self.subTest(rating=rating):
                response = self.client.post(
                    review_url,
                    {"rating": rating, "comment": "Comentário de teste."},
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(BookReview.objects.exists())

    def test_reviews_show_average_and_escape_reader_comments(self):
        other_reader = User.objects.create_user(
            username="outra-leitora",
            password="Senha-segura-2026!",
            first_name="Ana",
            last_name="Leitora",
        )
        BookReview.objects.create(
            book=self.book,
            reader=self.reader,
            rating=5,
            comment="Excelente.",
        )
        BookReview.objects.create(
            book=self.book,
            reader=other_reader,
            rating=3,
            comment="<script>alert('x')</script>",
        )

        detail = self.client.get(reverse("catalogo:detalhe-livro", args=[self.book.pk]))
        catalog = self.client.get(reverse("catalogo:livros"))

        self.assertContains(detail, "4,0")
        self.assertContains(detail, "2 avaliações")
        self.assertContains(detail, "Ana Leitora")
        self.assertContains(detail, "&lt;script&gt;")
        self.assertNotContains(detail, "<script>alert('x')</script>")
        self.assertContains(catalog, "aria-label=\"Média 4,0 de 5 estrelas, 2 avaliações\"")

    def test_unavailable_book_detail_does_not_offer_loan_action(self):
        self.book.available_copies = 0
        self.book.save()

        response = self.client.get(
            reverse("catalogo:detalhe-livro", args=[self.book.pk])
        )

        self.assertContains(response, "Indisponível no momento")
        self.assertContains(response, "Converse presencialmente")
        self.assertNotContains(response, ">Solicitar empréstimo</button>")

    def test_catalog_book_title_links_to_its_detail(self):
        response = self.client.get(reverse("catalogo:livros"))

        self.assertContains(
            response,
            reverse("catalogo:detalhe-livro", args=[self.book.pk]),
        )

    def test_admin_uploads_cover_and_readers_see_it_in_catalog_and_details(self):
        admin = User.objects.create_superuser(
            username="bibliotecario",
            email="admin@example.com",
            password="OutraSenha-forte-2026!",
        )
        image_buffer = BytesIO()
        Image.new("RGB", (20, 30), color=(30, 90, 60)).save(
            image_buffer,
            format="PNG",
        )
        upload = SimpleUploadedFile(
            "capa-livro.png",
            image_buffer.getvalue(),
            content_type="image/png",
        )

        with tempfile.TemporaryDirectory() as media_directory:
            with override_settings(MEDIA_ROOT=media_directory):
                self.client.force_login(admin)
                response = self.client.post(
                    reverse("admin:catalogo_book_add"),
                    {
                        "title": "Livro com capa",
                        "author": "Autora",
                        "category": "Literatura",
                        "description": "Descrição completa do livro.",
                        "total_copies": 2,
                        "available_copies": 2,
                        "shelf_location": "B-02",
                        "cover_image": upload,
                    },
                )

                self.assertRedirects(response, reverse("admin:catalogo_book_changelist"))
                uploaded_book = Book.objects.get(title="Livro com capa")
                self.assertTrue(uploaded_book.cover_image.name.startswith("capas/"))

                detail = self.client.get(
                    reverse("catalogo:detalhe-livro", args=[uploaded_book.pk])
                )
                catalog = self.client.get(reverse("catalogo:livros"))

                self.assertContains(detail, f'src="{uploaded_book.cover_image.url}"')
                self.assertContains(detail, "Descrição completa do livro.")
                self.assertContains(catalog, f'src="{uploaded_book.cover_image.url}"')
                self.assertTrue(
                    (Path(media_directory) / uploaded_book.cover_image.name).is_file()
                )

    def test_cover_upload_rejects_non_image_files(self):
        admin = User.objects.create_superuser(
            username="bibliotecario",
            email="admin@example.com",
            password="OutraSenha-forte-2026!",
        )
        self.client.force_login(admin)
        upload = SimpleUploadedFile(
            "not-an-image.png",
            b"this is not an image",
            content_type="image/png",
        )

        response = self.client.post(
            reverse("admin:catalogo_book_add"),
            {
                "title": "Livro sem capa inválida",
                "author": "Autora",
                "total_copies": 1,
                "available_copies": 1,
                "cover_image": upload,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Book.objects.filter(title="Livro sem capa inválida").exists())
        self.assertContains(response, "Envie uma imagem válida")

    def test_cover_validator_rejects_files_over_five_megabytes(self):
        oversized_file = SimpleUploadedFile(
            "capa-grande.png",
            b"x" * (MAX_COVER_SIZE + 1),
            content_type="image/png",
        )

        with self.assertRaisesMessage(ValidationError, "no máximo 5 MB"):
            validate_cover_size(oversized_file)

    def test_admin_can_record_a_physical_handoff(self):
        admin = User.objects.create_superuser(
            username="bibliotecario",
            email="admin@example.com",
            password="OutraSenha-forte-2026!",
        )
        self.client.force_login(admin)
        dashboard = self.client.get(reverse("admin:index"))
        self.assertContains(dashboard, reverse("admin:auth_group_changelist"))
        self.assertContains(dashboard, reverse("admin:auth_user_changelist"))
        self.assertContains(dashboard, reverse("admin:catalogo_loan_changelist"))
        self.assertContains(dashboard, reverse("admin:catalogo_book_changelist"))
        self.assertContains(dashboard, reverse("admin-register-loan"))
        self.assertContains(dashboard, reverse("admin-loan-report"))
        self.assertContains(dashboard, "/static/admin-dashboard.css?v=2")

        form_response = self.client.get(reverse("admin-register-loan"))
        self.assertContains(form_response, "Registrar entrega presencial")
        self.assertContains(form_response, "Leitor (leitor)")

        response = self.client.post(
            reverse("admin-register-loan"),
            {
                "action": "loan",
                "reader": self.reader.pk,
                "book": self.book.pk,
            },
        )

        self.assertRedirects(response, reverse("admin:catalogo_loan_changelist"))
        self.assertTrue(Loan.objects.filter(reader=self.reader, book=self.book).exists())
        self.assertEqual(Book.objects.get(pk=self.book.pk).available_copies, 0)

    def test_admin_loan_form_lists_active_staff_and_reader_names(self):
        staff_reader = User.objects.create_user(
            username="professora",
            password="Senha-segura-2026!",
            first_name="Maria",
            last_name="Silva",
            is_staff=True,
        )
        form = AdminLoanForm()
        choices = list(form.fields["reader"].choices)
        choice_labels = [label for _, label in choices]

        self.assertIn(
            f"Maria Silva ({staff_reader.username})",
            choice_labels,
        )
        self.assertIn(
            f"{self.reader.get_full_name()} ({self.reader.username})",
            choice_labels,
        )

    def test_admin_action_records_physical_return_and_restores_availability(self):
        loan = create_loan(reader=self.reader, book_id=self.book.pk)
        admin = User.objects.create_superuser(
            username="bibliotecario",
            email="admin@example.com",
            password="OutraSenha-forte-2026!",
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("admin:catalogo_loan_changelist"),
            {
                "action": "mark_as_returned",
                "_selected_action": [str(loan.pk)],
            },
        )

        loan.refresh_from_db()
        self.assertRedirects(response, reverse("admin:catalogo_loan_changelist"))
        self.assertIsNotNone(loan.returned_at)
        self.assertEqual(Book.objects.get(pk=self.book.pk).available_copies, 1)

    def test_admin_registers_early_return_from_physical_handoff_page(self):
        loan = create_loan(reader=self.reader, book_id=self.book.pk)
        admin = User.objects.create_superuser(
            username="bibliotecario",
            email="admin@example.com",
            password="OutraSenha-forte-2026!",
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("admin-register-loan"),
            {"action": "return", "return-loan": str(loan.pk)},
        )

        loan.refresh_from_db()
        self.assertRedirects(response, reverse("admin-register-loan"))
        self.assertIsNotNone(loan.returned_at)
        self.assertLess(loan.returned_at.date(), loan.due_date)
        self.assertEqual(Book.objects.get(pk=self.book.pk).available_copies, 1)

    def test_admin_loan_report_filters_and_exports_matching_rows(self):
        self.book.total_copies = 2
        self.book.available_copies = 2
        self.book.save()
        overdue = create_loan(reader=self.reader, book_id=self.book.pk)
        overdue.due_date = timezone.localdate() - timedelta(days=1)
        overdue.save(update_fields=["due_date"])
        returned_book = Book.objects.create(
            title="Outro livro devolvido",
            author="Outro Autor",
            total_copies=1,
            available_copies=1,
        )
        returned = create_loan(reader=self.reader, book_id=returned_book.pk)
        register_return(loan_id=returned.pk)
        active = create_loan(reader=self.reader, book_id=self.book.pk)
        admin = User.objects.create_superuser(
            username="bibliotecario",
            email="admin@example.com",
            password="OutraSenha-forte-2026!",
        )
        self.client.force_login(admin)

        response = self.client.get(
            reverse("admin-loan-report"),
            {"status": "overdue", "q": "O livro"},
        )
        csv_response = self.client.get(
            reverse("admin-loan-report"),
            {"status": "overdue", "q": "O livro", "export": "csv"},
        )

        self.assertContains(response, "Relatório de empréstimos")
        self.assertContains(response, "/static/admin-reports.css?v=3")
        self.assertEqual(response.context["total_count"], 1)
        self.assertEqual(response.context["overdue_count"], 1)
        self.assertEqual([loan.pk for loan in response.context["page_obj"]], [overdue.pk])
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        self.assertIn("attachment;", csv_response["Content-Disposition"])
        self.assertIn("relatorio-emprestimos-", csv_response["Content-Disposition"])
        self.assertIn(b"\xef\xbb\xbf", csv_response.content[:3])
        self.assertIn(b"O livro da escola", csv_response.content)
        self.assertNotIn(b"Outro livro devolvido", csv_response.content)
        self.assertNotIn(b"Em andamento", csv_response.content)
        self.assertContains(response, "export=csv")

    def test_admin_loan_report_rejects_invalid_date_range(self):
        admin = User.objects.create_superuser(
            username="bibliotecario",
            email="admin@example.com",
            password="OutraSenha-forte-2026!",
        )
        self.client.force_login(admin)

        response = self.client.get(
            reverse("admin-loan-report"),
            {"start_date": "2026-10-10", "end_date": "2026-10-01"},
        )
        csv_response = self.client.get(
            reverse("admin-loan-report"),
            {
                "start_date": "2026-10-10",
                "end_date": "2026-10-01",
                "export": "csv",
            },
        )

        self.assertContains(response, "A data final precisa ser igual ou posterior")
        self.assertEqual(response.context["total_count"], 0)
        self.assertEqual(csv_response.status_code, 200)
        self.assertContains(csv_response, "A data final precisa ser igual ou posterior")
        self.assertContains(csv_response, "Corrija os filtros destacados")

    def test_loan_report_requires_loan_view_permission(self):
        staff_user = User.objects.create_user(
            username="funcionario",
            password="Senha-segura-2026!",
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse("admin-loan-report"))

        self.assertEqual(response.status_code, 403)
