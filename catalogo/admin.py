from django.contrib import admin, messages

from .models import Book, BookReview, Loan
from .services import register_return


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "author",
        "category",
        "total_copies",
        "available_copies",
        "shelf_location",
    )
    list_filter = ("category",)
    search_fields = ("title", "author", "category", "shelf_location")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Identificação",
            {"fields": ("title", "author", "category", "description", "cover_image")},
        ),
        (
            "Acervo físico",
            {"fields": ("total_copies", "available_copies", "shelf_location")},
        ),
        ("Histórico", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(BookReview)
class BookReviewAdmin(admin.ModelAdmin):
    list_display = ("book", "reader", "rating", "created_at", "updated_at")
    list_filter = ("rating", "created_at")
    search_fields = (
        "book__title",
        "reader__username",
        "reader__first_name",
        "reader__last_name",
        "comment",
    )
    list_select_related = ("book", "reader")
    readonly_fields = ("book", "reader", "created_at", "updated_at")
    fields = ("book", "reader", "rating", "comment", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    change_list_template = "admin/catalogo/loan/change_list.html"
    list_display = ("book", "reader", "borrowed_at", "due_date", "status")
    list_filter = ("returned_at", "due_date")
    search_fields = (
        "book__title",
        "reader__username",
        "reader__first_name",
        "reader__last_name",
    )
    list_select_related = ("book", "reader")
    list_display_links = None
    actions = ("mark_as_returned",)

    @admin.display(description="situação")
    def status(self, loan):
        if loan.returned_at:
            return "Devolvido"
        if loan.is_overdue:
            return "Atrasado"
        return "Em andamento"

    @admin.action(
        description="Registrar devolução presencial dos empréstimos selecionados",
        permissions=["view"],
    )
    def mark_as_returned(self, request, queryset):
        returned = 0
        for loan in queryset:
            if register_return(loan_id=loan.pk):
                returned += 1
        if returned:
            self.message_user(
                request,
                f"{returned} devolução(ões) registrada(s).",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "Nenhum dos empréstimos selecionados estava ativo.",
                level=messages.WARNING,
            )

    def get_readonly_fields(self, request, obj=None):
        return ("reader", "book", "borrowed_at", "due_date", "returned_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and (
            request.user.is_superuser or request.user.has_perm("catalogo.view_loan")
        )


admin.site.site_header = "Biblioteca escolar — administração"
admin.site.site_title = "Administração da biblioteca"
admin.site.index_title = "Gerencie o acervo e os empréstimos"
