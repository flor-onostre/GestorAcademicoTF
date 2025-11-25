from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages


class ForcePasswordChangeMiddleware:
    """
    Redirige a cambio de contraseña si el usuario tiene must_change_password=True.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, "must_change_password", False):
            allowed = {
                reverse("change_password"),
                reverse("logout"),
            }
            if request.path not in allowed:
                messages.warning(
                    request,
                    "Debes cambiar tu contraseña antes de continuar.",
                )
                return redirect("change_password")
        return self.get_response(request)
