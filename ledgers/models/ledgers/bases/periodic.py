from django.db import models
from django.utils.translation import gettext_lazy as _


class PeriodicLedgerRecord(models.Model):
    """Periodic ledger record abstract class.

    These records have attributes:
    - period — a period in time when record becomes "active"
    """
    class Meta:
        abstract = True

        # recommended indexes (add to subclasses)
        indexes = [
            models.Index(
                fields=["period", ],
            ),
        ]

    period = models.DateTimeField(
        null=False,
        blank=False,
        verbose_name=_('record\'s period')
    )
