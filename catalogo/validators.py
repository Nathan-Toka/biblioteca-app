from django.core.exceptions import ValidationError


MAX_COVER_SIZE = 5 * 1024 * 1024


def validate_cover_size(image):
    if image.size > MAX_COVER_SIZE:
        raise ValidationError("A imagem da capa deve ter no máximo 5 MB.")
