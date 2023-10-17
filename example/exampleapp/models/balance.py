from django.db import models
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .itemmovement import ItemMovement

from ledgers.ledger import CumulativeLedger
from ledgers.ledger.fields import dimensions, resources
from ledgers.enum import CumulativeLedgerRecordActionEnum
from .warehouse import Warehouse
from .item import Item


class BalanceAtWarehousesLedger(CumulativeLedger):
    warehouse = dimensions.ForeignKey(
        to=Warehouse,
        null=False,
    )
    item = dimensions.ForeignKey(
        to=Item,
        null=False,
    )
    amount = resources.Integer()
    comment = models.CharField(max_length=200, null=False, default='')

    @classmethod
    def movements_for_itemmovement(cls, doc: 'ItemMovement'):
        # noinspection PyCallingNonCallable
        return (
            cls.mvm_model(
                period=doc.execution_date,
                registrator=doc,
                line_index=0,
                action=CumulativeLedgerRecordActionEnum.OUTCOME,
                warehouse_id=doc.from_warehouse_id,
                item_id=doc.item_id,
                amount=doc.amount,
            ),
            cls.mvm_model(
                period=doc.execution_date,
                registrator=doc,
                line_index=1,
                action=CumulativeLedgerRecordActionEnum.INCOME,
                warehouse_id=doc.to_warehouse_id,
                item_id=doc.item_id,
                amount=doc.amount,
            ),
        )
