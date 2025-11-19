from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    name = "accounts"
    verbose_name = _("Cuentas")

    def ready(self) -> None:
        from django.db.models.signals import post_save
        from .models import User
        from .signals import post_save_account_receiver

        post_save.connect(post_save_account_receiver, sender=User)

        return super().ready()
