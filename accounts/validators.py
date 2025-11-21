import re

from django.core import validators
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


@deconstructible
class ASCIIUsernameValidator(validators.RegexValidator):
    regex = r"^[a-zA-Z]+\/(...)\/(....)"
    message = _(
        "Ingresá un nombre de usuario válido. Solo se permiten letras, "
        "números y los caracteres @/./+/-/_."
    )
    flags = re.ASCII
