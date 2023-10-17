from django.db import models

from .item import Item
from .warehouse import Warehouse
from ledgers.models import Document
from .balance import BalanceAtWarehousesLedger


class ItemMovement(Document):
    class DocumentMeta(Document.DocumentMeta):
        related_ledgers = [BalanceAtWarehousesLedger]
        default_prefix = 'MVM'

    from_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name='+',
    )
    to_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name='+',
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    amount = models.IntegerField(
        null=False,
        blank=False,
    )
