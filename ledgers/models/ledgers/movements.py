from django.db import models
from django.utils.translation import gettext_lazy as _
from django_cte import CTEManager

from ledgers.models.ledgers.bases import PeriodicLedgerRecord, DependentLedgerRecord
from ledgers.enum import CumulativeLedgerRecordActionEnum


class CumulativeLedgerMovementRecord(PeriodicLedgerRecord, DependentLedgerRecord):
    """
    Cumulative ledger movement record abstract class.

    These records have attributes:
    - action — specifies whether this record adds or substracts cumulatable value
    """

    class Meta:
        abstract = True

        # recommended indexes (add to subclasses)
        indexes = [
            *PeriodicLedgerRecord.Meta.indexes,
            *DependentLedgerRecord.Meta.indexes,
            models.Index(
                fields=["period", "registrator_content_type", "registrator_id", "action", "enabled", ],
            ),
            models.Index(
                fields=["period", "action", "enabled", ],
            ),
            models.Index(
                fields=["period", "enabled", ],
            )
        ]

        # recommended constraints (copy to subclasses)
        constraints = [
            models.UniqueConstraint(
                fields=["period", "registrator_content_type", "registrator_id", "line_index", ],
                name="unique_record",
            )
        ]

    action = models.CharField(
        null=False,
        blank=False,
        max_length=1,
        choices=CumulativeLedgerRecordActionEnum.choices,
        editable=True,
        verbose_name=_('action'),
    )

    objects = CTEManager()
