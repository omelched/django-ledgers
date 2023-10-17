from django.contrib import admin

from ..models import Warehouse, Item, ItemMovement, BalanceAtWarehousesLedger


admin.site.register(Warehouse)
admin.site.register(Item)
admin.site.register(ItemMovement)
admin.site.register(BalanceAtWarehousesLedger.mvm_model)
admin.site.register(BalanceAtWarehousesLedger.tot_model)
