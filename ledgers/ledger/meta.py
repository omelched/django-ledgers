from typing import Any
import inspect

from django.db import models
from django.apps import apps

from ledgers.models.ledgers import CumulativeLedgerMovementRecord, CumulativeLedgerTotalsRecord
from ledgers.ledger.fields.dimensions import Dimension
from ledgers.ledger.fields.resources import Resource


class LedgerMeta:
    abstract = False
    movements_class = CumulativeLedgerMovementRecord
    totals_class = CumulativeLedgerTotalsRecord


class CumulativeLedgerMeta(type):
    """ Cumulative Ledger Metaclass.

    This metaclass constructs a CumulativeLedger type from declared fields.
    Fields can be declared as:
        - dimensions
        - resources
        - attributes

    Dimensions — fields which, when combined, represent a unique slice to store movement records.
    Resources — fields which will be aggregated and totalled across many movement records.
    Attributes — fields which may store additional data bound to movement record.

    From declared fields, two Django Models are designed:
    - Movements table (inherits from ledgers.models.ledger.cumulative.CumulativeLedgerMovementRecord)
    - Totals table (inherits from ledgers.models.ledger.cumulative.CumulativeLedgerTotalsRecord)

    e.g. a cumulative ledger which stores item balances across warehouses.

    Dimensions:
        - warehouse (ref to Warehouse table)
        - item      (ref to Item table)
    Resources:
        - amount    (countable data type (int/float/numeric))
    Attributes:
        - comment   (arbitraty data)

    Movements table
        - columns:
            - period                    <-|
            - registrator_content_type    |
            - registrator_id              |- inherited from CumulativeLedgerMovementRecord (1)
            - line_index                  |
            - enabled                     |
            - action                    <-|
            - warehouse_id
            - item_id
            - amount
            - comment
        - indexes:
            - period                                                               <-|
            - registrator_content_type, registrator_id, line_index, enabled          |
            - registrator_id                                                         |- inh. as (1)
            - period, registrator_content_type, registrator_id, action, enabled      |
            - period, action, enabled                                              <-|
            - period, action, enabled, warehouse_id, item_id
        - constraints:
            - period, registrator_content_type, registrator_id, line_index   <- inh. as (1)

    Totals table
        - columns:
            - period        <- inherited from CumulativeLedgerTotalsRecord (2)
            - warehouse_id
            - item_id
            - total_amount
        - indexes:
            - period                <- inh. as (2)
            - warehouse_id, item_id
        - constraints:
            - period, warehouse_id, item_id

    Movements and Totals Models are registered at django ORM, and added to new class as protected attributes.

    # TODO: methods to access data
    """

    @classmethod
    def movements_model_factory(cls,
                                movements_model_name: str,
                                movements_model_bases: tuple[type],
                                is_abstract: bool,
                                dimensions: dict[str, Dimension],
                                resources: dict[str, Resource],
                                attributes: dict[str, models.Field],
                                extra_python_attributes: dict[str, Any]):

        meta = type(
            '_meta',
            (CumulativeLedgerMovementRecord.Meta,),
            {
                'abstract': is_abstract,
                'indexes': [
                    *CumulativeLedgerMovementRecord.Meta.indexes,
                    models.Index(
                        fields=[
                            'period', 'enabled', *dimensions.keys()
                        ]
                    ),
                ],
            }
        )

        model_fields = {}

        for name, dimension in dimensions.items():
            model_fields[name] = dimension.django_field

        for name, resource in resources.items():
            model_fields[name] = resource.django_field

        model_fields.update(attributes)

        if not len(model_fields) == sum(map(len, [dimensions, resources, attributes])):
            # TODO: exception when same named fields
            raise ValueError

        model_attrs = {
            'Meta': meta,
            **model_fields,
            **extra_python_attributes,
        }

        model = type(
            movements_model_name,
            movements_model_bases,
            model_attrs,
        )

        return model

    @classmethod
    def totals_model_factory(cls,
                             totals_model_name: str,
                             totals_model_bases: tuple[type],
                             is_abstract: bool,
                             dimensions: dict[str, Dimension],
                             resources: dict[str, Resource],
                             extra_python_attributes: dict[str, Any]):
        meta = type(
            '_meta',
            (CumulativeLedgerTotalsRecord.Meta,),
            {
                'abstract': is_abstract,
                'indexes': [
                    *CumulativeLedgerTotalsRecord.Meta.indexes,
                    models.Index(
                        fields=[
                            'period', *dimensions.keys(),
                        ]
                    ),
                ],
                'constraints': [
                    *(CumulativeLedgerTotalsRecord.Meta.constraints
                      if hasattr(CumulativeLedgerTotalsRecord.Meta, 'constraints') else []),
                    models.UniqueConstraint(
                        'period', *dimensions.keys(),
                        name=f'unique_dimensions_{totals_model_name}'
                    ),
                ]
            }
        )

        model_fields = {}

        for name, dimension in dimensions.items():
            model_fields[name] = dimension.django_field

        for name, resource in resources.items():
            model_fields[f'{name}_total'] = resource.django_field

        if not len(model_fields) == sum(map(len, [dimensions, resources])):
            # TODO: exception when same named fields
            raise ValueError

        model_attrs = {
            'Meta': meta,
            **model_fields,
            **extra_python_attributes,
        }

        model = type(
            totals_model_name,
            totals_model_bases,
            model_attrs,
        )

        return model

    @staticmethod
    def extract_contributable(attrs):
        def _has_contribute_to_class(value):
            return not inspect.isclass(value) and hasattr(value, "contribute_to_class")

        dimensions = {}
        resources = {}
        attributes = {}
        non_contributables = {}

        for obj_name, obj in attrs.items():
            if isinstance(obj, Dimension):
                dimensions[obj_name] = obj
                obj.set_name(obj_name)
            elif isinstance(obj, Resource):
                resources[obj_name] = obj
                obj.set_name(obj_name)
            elif _has_contribute_to_class(obj):
                attributes[obj_name] = obj
            else:
                non_contributables[obj_name] = obj

        return dimensions, resources, attributes, non_contributables

    def __new__(cls, name, bases, attrs, **kwargs):
        # Copy python metadata to new attrs
        module = attrs.pop("__module__")
        new_attrs = {"__module__": module}

        classcell = attrs.pop("__classcell__", None)
        if classcell is not None:
            new_attrs["__classcell__"] = classcell

        # Save meta and contributable attributes
        attr_meta = attrs.pop("LedgerMeta", LedgerMeta)
        abstract = attr_meta.abstract
        # Extract contributable
        dimensions, resources, attributes, non_contributables = cls.extract_contributable(attrs)

        # TODO: validate dim, res, attr after parse

        # Copy non-contributables
        new_attrs.update(non_contributables)

        # Create new class
        new_class = super().__new__(cls, name, bases, new_attrs, **kwargs)

        # Create models
        mvm_model = new_class.movements_model_factory(f'{name}_movements', (attr_meta.movements_class,), abstract,
                                                      dimensions, resources, attributes, {"__module__": module})
        tot_model = new_class.totals_model_factory(f'{name}_totals', (attr_meta.totals_class,), abstract, dimensions,
                                                   resources, {"__module__": module})

        # Add models to class
        setattr(new_class, 'mvm_model', mvm_model)
        setattr(new_class, 'tot_model', tot_model)

        # Add dimensions to class
        setattr(new_class, '_dimensions', dimensions.values())
        setattr(new_class, '_resources', resources.values())

        if not abstract:
            ledgers_app_config = apps.get_app_config('ledgers')

            app_config = apps.get_containing_app_config(module)
            app_label = app_config.label

            ledgers_app_config.register_ledger(app_label, new_class)

        return new_class
