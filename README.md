# django-ledgers<sup>_v0.1.0_</sup>

Django app which implements ledgers to store cumulative data.

## Description

A **Ledger** is an abstraction over Django ORM which consists of 2 tables:
- movements — stores periodic data about ledger's state change.
- totals — stores pre-calculated cumulative result for some period. 

Ledger's state is changed via **Documents** — an "atomic" abstraction over set of simultaneous changes.

### Examples

#### Warehouse remains

Items:

```python
from django.db import models


class Item(models.Model):
    name = models.CharField(max_length=200, unique=True)

```

can be stored at Warehouse:

```python
class Warehouse(models.Model):
    name = models.CharField()

```

via Warehouse Balance Ledger:

```python
from ledgers.enum import CumulativeLedgerRecordActionEnum
from ledgers.ledger import CumulativeLedger
from ledgers.ledger.fields import dimensions, resources


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
    def movements_for_itemmovement(cls, doc):
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

```

and changed via Item Movement:

```python
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

```

Then, on creating an ItemMovement:
```python
from ledgers.enum import DocumentStateEnum

# prepare instances
t_shirt = Item.objects.get_or_create(name='T-shirt')
london_warehouse = Warehouse.objects.get_or_create(name='London')
tokyo_warehouse = Warehouse.objects.get_or_create(name='Tokyo')

# prepare and save document
doc = ItemMovement(
    state=DocumentStateEnum.ACTIVE,
    item=t_shirt,
    from_warehouse=london_warehouse,
    to_warehouse=tokyo_warehouse,
    amount=100,
)
doc.save()

```

Movements and totals tables will be updated, and actual remains for any period can be fetched:
```python
from example.exampleapp.models import Item, Warehouse, BalanceAtWarehousesLedger
from datetime import timedelta


# prepare instances
t_shirt = Item.objects.get_or_create(name='T-shirt')
london_warehouse = Warehouse.objects.get_or_create(name='London')
tokyo_warehouse = Warehouse.objects.get_or_create(name='Tokyo')

remains_before_document_date = BalanceAtWarehousesLedger.remains_qs(
    period=doc.execution_date - timedelta(days=1),
)
remains_after_document_date = BalanceAtWarehousesLedger.remains_qs()

print(list(remains_before_document_date))
# [
#   {
#       'warehouse_id': 1,
#       'item_id': 1,
#       'amount_remains': 0
#   },
#   {
#       'warehouse_id': 2,
#       'item_id': 1,
#       'amount_remains': 0
#   }
# ]

print(list(remains_after_document_date))
# [
#   {
#       'warehouse_id': 1,
#       'item_id': 1,
#       'amount_remains': -10
#   },
#   {
#       'warehouse_id': 2,
#       'item_id': 1,
#       'amount_remains': 10
#   }
# ]

```

### Features

**django-ledgers** @ [v0.1.0](https://github.com/omelched/django-ledgers/releases/tag/v0.1.0) can:

- store push tokens from FCM or HMS
- link push tokens with their users and applications
- store push notifications
- store push notifications extra kwargs (e.g. deeplinks)
- compose recipients via UI based on user-specified conditions
- watch notifications schedule on calendar 
- send scheduled push notifications
- store applications as swappable model

### Usage example

_TODO_

#### exampleproj

[Example project](example/exampleproj) is a showcase django project.
You can reference to it for usage cases, examples, testing.
You must never deploy `exampleproj` in production due to exposed `SECRET_KEY`.

## Getting Started

### Dependencies

#### Python packages

* `django`
* `django-cte`

### Installing

#### Using Python Package Index

* make sure to use latest `pip`:
  ```shell
  python3 -m pip install --upgrade pip
  ```

* install `django-ledgers`:
  ```shell
  python3 -m pip install django-ledgers
  ```
  
#### OR download package from releases

* download release asset (`.tar.gz` or `.whl`)

* make sure to use latest `pip`:
  ```shell
  python3 -m pip install --upgrade pip
  ```

* install `djangoFCM` from file:
  ```shell
  python3 -m pip install /path/to/downloaded/asset.tar.gz # or .whl
  ```

#### OR clone from repository 

* clone project:
  ```shell
  git clone \
          --depth=1 \
          --branch=master \
          git@github.com:omelched/django-ledgers.git \
          </path/to/downloads>
  ```

* move `/django-ledgers/ledgers` solely to folder containing django apps
  ```shell
  mv      </path/to/downloads>/django-ledgers/ledgers \
          </path/to/django/project/apps>
  ```
  
* remove leftovers
  ```shell
  rm -rf  </path/to/downloads>/django-ledgers
  ```

### Configuring

#### Installing application

Add `django-ledgers` to `INSTALLED_APPS` in your Django project `settings.py`.

If you installed package [the third way](#or-clone-from-repository), `</path/to/django/project/apps>`
must be added to `PYTHONPATH`. If you not sure add code below in your Django project `manage.py` before calling `main()`:
```python
sys.path.append('</path/to/django/project/apps>')
```

Subclass `ledgers.ledger.cumulative.CumulativeLedger` and `ledgers.models.documents.document.Document`.

#### Migrations

Execute database migrations:
```shell
python example/manage.py migrate
```

Collect static:
```shell
python example/manage.py collectstatic
```

## Authors

[@omelched](https://github.com/omelched) _(Denis Omelchenko)_

### Contributors

<img width=20% src="https://64.media.tumblr.com/7b59c6105c40d611aafac4539500fee1/tumblr_njiv6sUfgO1tvqkkro1_640.gifv" title="tumbleweed" alt="tumbleweed"/>

## Changelist

**django-ledgers** version history and changelist
available at [releases](https://github.com/omelched/django-ledgers/releases) page.

## License

This project is licensed under the **MIT** License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

This project is inspired by 1C ORM. More on topic:
- https://its.1c.ru/db/pubapplied/content/123/hdoc (writing)
- https://its.1c.ru/db/pubapplied/content/130/hdoc (querying)