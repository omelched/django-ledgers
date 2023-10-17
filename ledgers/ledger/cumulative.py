import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ledgers.models import Document

from django.utils import timezone
from datetime import UTC
from django_cte import With
from django.db import models, transaction
from django.utils.functional import classproperty
from django.contrib.contenttypes.models import ContentType
from django.db.models import functions
from django.db.models.sql.constants import LOUTER

from .meta import LedgerMeta, CumulativeLedgerMeta
from ledgers.models import CumulativeLedgerMovementRecord, CumulativeLedgerTotalsRecord
from ledgers.ledger.fields.dimensions import Dimension
from ledgers.ledger.fields.resources import Resource
from ledgers.enum import DocumentStateEnum, CumulativeLedgerRecordActionEnum


class CumulativeLedger(metaclass=CumulativeLedgerMeta):
    mvm_model: CumulativeLedgerMovementRecord
    tot_model: CumulativeLedgerTotalsRecord

    _dimensions: list[Dimension]
    _resources: list[Resource]
    _TOTALS_FINAL_DATE = timezone.make_aware(datetime.datetime.max.replace(microsecond=0), timezone=UTC)

    class LedgerMeta(LedgerMeta):
        abstract = True

    # noinspection PyMethodParameters
    @classproperty
    def dimensions(cls) -> list[Dimension]:
        return cls._dimensions

    # noinspection PyMethodParameters
    @classproperty
    def resources(cls) -> list[Resource]:
        return cls._resources

    # noinspection PyMethodParameters
    @classproperty
    def dimensions_db_names(cls) -> list[str]:
        return [dim.db_name for dim in cls.dimensions]

    # noinspection PyMethodParameters
    @classproperty
    def resources_db_names(cls) -> list[str]:
        return [res.db_name for res in cls.resources]

    @classmethod
    @transaction.atomic
    def _delete_previous_movements(cls, document: 'Document') -> set[tuple[Any]]:
        """
        This method deletes movements from ledger for specific document.

        :param document: document
        :type document: ledgers.models.documents.document.Document

        :return: affected keys for totals to be recalculated
        :rtype: set[tuple[Any]]
        """
        ct = ContentType.objects.get_for_model(type(document))

        qs = cls.mvm_model.objects.filter(registrator_content_type_id=ct.pk, registrator_id=document.pk)
        affected_keys_values = list(qs.order_by().values_list(*cls.dimensions_db_names).distinct())

        affected_keys = set()
        for key_dimensions in affected_keys_values:
            key_dimensions = tuple(key_dimensions)
            affected_keys.add(key_dimensions)

        qs.delete()

        return affected_keys

    @classmethod
    @transaction.atomic
    def _write_movements(cls, document: 'Document') -> set[tuple[Any]]:
        """
        This method writes movements in ledger for specific document.

        :param document: document
        :type document: ledgers.models.documents.document.Document

        :return: affected keys for totals to be recalculated
        :rtype: set[tuple[Any]]
        """
        affected_keys = set()

        if document.deleted or document.state == DocumentStateEnum.DRAFT:
            return affected_keys

        ct = ContentType.objects.get_for_model(type(document))

        # records for this document type must be implemented in subclass directly
        movements_records = getattr(cls, f'movements_for_{ct.model}')(document)
        cls.mvm_model.objects.bulk_create(movements_records)

        for movements_record in movements_records:
            key_dimensions = []

            for dim_db_name in cls.dimensions_db_names:
                value = getattr(movements_record, dim_db_name)
                key_dimensions.append(value)

            key_dimensions = tuple(key_dimensions)

            affected_keys.add(key_dimensions)

        return affected_keys

    @classmethod
    @transaction.atomic
    def calculate_totals(cls, keys: set[tuple[Any]]):
        """
        This method calculates and wtites totals for provided keys.

        :param keys: dimension's keys to recalculate totals for
        :type keys: set[tuple[Any]]
        """

        new_totals = []

        dimensions = [
            dict(
                zip(
                    cls.dimensions_db_names,
                    dimension_values
                )
            )
            for dimension_values in keys
        ]

        q = models.Q()
        for dimension in dimensions:
            q |= models.Q(**dimension)

        _ = cls.tot_model.objects.filter(q).select_for_update()

        remains = list(
            cls.movements_remains_qs(
                period_q=None,
                dimensions_q=q,
            ).values(
                *cls.dimensions_db_names,
                *[f'{res_db_name}_mvm_sum' for res_db_name in cls.resources_db_names],
            )
        )

        totals = {
            tuple(row[dim_db_name] for dim_db_name in cls.dimensions_db_names): {
                f'{res_db_name}_total': row[f'{res_db_name}_mvm_sum']
                for res_db_name
                in cls.resources_db_names
            }
            for row
            in remains
        }

        for dimension in dimensions:
            # noinspection PyCallingNonCallable
            new_totals.append(
                cls.tot_model(
                    period=cls._TOTALS_FINAL_DATE,
                    **dimension,
                    **totals[tuple(dimension.values())],
                )
            )

        cls.tot_model.objects.bulk_create(
            new_totals,
            update_conflicts=True,
            update_fields=[f'{res_db_name}_total' for res_db_name in cls.resources_db_names],
            unique_fields=['period', *cls.dimensions_db_names],
        )

    @classmethod
    def movements_remains_qs(cls, period_q: models.Q = None, dimensions_q: models.Q = None,
                             over_dimensions: list[str] = None, resourses: list[str] = None):

        period_q = period_q or models.Q()
        dimensions_q = dimensions_q or models.Q()
        over_dimensions = over_dimensions or cls.dimensions_db_names
        resourses = resourses or cls.resources_db_names

        qs = cls.mvm_model.objects.filter(
            period_q,
            dimensions_q,
            enabled=True,
        ).values(*over_dimensions).annotate(
            **{
                f'{res}_mvm_sum': (
                        functions.Coalesce(
                            models.Sum(
                                res,
                                filter=models.Q(action=CumulativeLedgerRecordActionEnum.INCOME)
                            ),
                            0
                        ) -
                        functions.Coalesce(
                            models.Sum(
                                res,
                                filter=models.Q(action=CumulativeLedgerRecordActionEnum.OUTCOME)
                            ),
                            0
                        )
                )
                for res
                in resourses
            },
        )
        return qs

    @classmethod
    def remains_qs(cls, period: datetime.datetime = None, dimensions_q: models.Q = None, resourses: list[str] = None):
        """
        Algorithm to query remains for arbitraty date `date`:
        - get value from "totals table"
        - get all records from "movements table" between `date` and datetime.datetime.max
        - aggregate(sum) records from movements table
        - add "movements table"'s aggregates from "totals table"'s value
        """

        if not period:
            period = timezone.now()

        if not dimensions_q:
            dimensions_q = models.Q()

        if not resourses:
            resourses = cls.resources_db_names

        dimensions = cls.dimensions_db_names

        movements_cte = With(
            cls.movements_remains_qs(
                period_q=models.Q(period__gte=period),
                dimensions_q=dimensions_q,
                over_dimensions=dimensions,
                resourses=resourses,
            )
        )

        qs = movements_cte.join(
            cls.tot_model.objects.filter(
                dimensions_q,
                period=cls._TOTALS_FINAL_DATE,
            ),
            **{dim: getattr(movements_cte.col, dim) for dim in dimensions},
            _join_type=LOUTER,
        ).with_cte(movements_cte).values(*dimensions).annotate(
            **{
                f'{res}_remains': models.F(f'{res}_total') - functions.Coalesce(
                    getattr(movements_cte.col, f'{res}_mvm_sum'),
                    0,
                )
                for res
                in resourses
            },
        )

        return qs

    @classmethod
    def _bulk_delete_previous_records(cls, documents: list['Document']) -> set[tuple[Any]]:
        """
        This method deletes movements from ledger for a list of documents.

        :param documents: documents
        :type documents: list[ledgers.models.documents.document.Document]

        :return: affected keys for totals to be recalculated
        :rtype: set[tuple[Any]]
        """
        ct = ContentType.objects.get_for_model(type(documents[0]))

        qs = cls.mvm_model.objects.filter(content_type=ct, object_id__in=[d.pk for d in documents])
        affected_keys_values = list(qs.order_by().values_list(*cls.dimensions_db_names).distinct())

        affected_keys = set()
        for key_dimensions in affected_keys_values:
            key_dimensions = tuple(key_dimensions)
            affected_keys.add(key_dimensions)

        qs.delete()

        return affected_keys

    @classmethod
    @transaction.atomic
    def _bulk_write_movements(cls, documents: list['Document']) -> set[tuple[Any]]:
        """
        This method writes movements in ledger for a list of documents.

        :param documents: documents
        :type documents: list[ledgers.models.documents.document.Document]

        :return: affected keys for totals to be recalculated
        :rtype: set[tuple[Any]]
        """
        affected_keys = set()

        ct = ContentType.objects.get_for_model(type(documents[0]))

        movements_records = []
        for document in documents:

            if document.deleted or document.state == DocumentStateEnum.DRAFT:
                continue

            # TODO: call bulk_movements_for_...(documents) if implemented by ledger
            movements_records.extend(getattr(cls, f'movements_for_{ct.model}')(document))

        cls.mvm_model.objects.bulk_create(movements_records)

        for movements_record in movements_records:
            key_dimensions = []

            for dim_db_name in cls.dimensions_db_names:
                value = getattr(movements_record, dim_db_name)
                key_dimensions.append(value)

            key_dimensions = tuple(key_dimensions)

            affected_keys.add(key_dimensions)

        return affected_keys

    @classmethod
    @transaction.atomic
    def write(cls, document):

        deleted_keys = cls._delete_previous_movements(document)
        created_keys = cls._write_movements(document)

        affected_keys = deleted_keys.union(created_keys)

        cls.calculate_totals(affected_keys)

    @classmethod
    @transaction.atomic
    def bulk_write(cls, documents):
        # TODO: assert documents are homogenous

        deleted_keys = cls._bulk_delete_previous_records(documents)
        created_keys = cls._bulk_write_movements(documents)

        affected_keys = deleted_keys.union(created_keys)

        cls.calculate_totals(affected_keys)
