from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ledgers.models.documents import Document

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.postgres.indexes import HashIndex

from ledgers.utils.arrays import is_homogenous


class DependentLedgerManager(models.Manager):
    """ A manager subclass for dependent ledger.
    Manages write and bulk write in ledger for document(s).

    Adds methods:
    - write — called upon document save.
    - bulk_write — a write implementation for an aray of documents (with same content type!).
    """

    def get_registrator_content_type(self, document) -> ContentType:
        """ This method gets content type for document and checks whether it can write in this ledger.

        :param document: document which content type is requested.
        :type document: ledgers.models.document.doc.Document

        :raises:
            ValueError: if document cannot write in this ledger.

        :return: content type of document
        :rtype: django.contrib.contenttypes.models.ContentType
        """
        ct = ContentType.objects.get_for_model(type(document))

        descriptor = f'{ct.app_label}.{ct.model}'.lower()

        if descriptor not in self.model.ALLOWED_REGISTRATOR_DESCRIPTORS:
            raise ValueError(f'Document {descriptor} cannot write to ledger {self.model.__name__}!')
        else:
            return ct

    @transaction.atomic
    def write(self, document: 'Document') -> None:
        """ Creates and saves ledger records from document.
        MUST be called on document save IF this ledger had dependency with document.

        :param document: a Document to generate records.
        :type document: ledgers.models.document.doc.Document
        """

        # get content type of document
        ct = self.get_registrator_content_type(document=document)

        # delete previous records
        self.get_queryset().filter(registrator=document).delete()

        # call records creation method
        records = getattr(self, f'records_for_{ct.model}')(document)

        # save records to DB
        self.get_queryset().bulk_create(records)

    @transaction.atomic
    def bulk_write(self, documents: list['Document']):
        """ Bulk impormentation of `write` method for a list of Documents.

        :param documents: a list of Documents to generate records.
        :type documents: list[ledgers.models.document.doc.Document]
        """

        if not documents:
            raise ValueError('Documents were not provided.')

        # assert that `documents` is homogenous
        if not is_homogenous(documents):
            raise ValueError('Documents are not homogenous.')

        # get content type of documents
        ct = self.get_registrator_content_type(document=documents[0])

        # delete previous records of those documents
        self.get_queryset().filter(registrator__in=documents).delete()

        # if model has an optimized records creation method
        if hasattr(self, f'bulk_records_for_{ct.model}'):
            # call it
            records = getattr(self, f'bulk_records_for_{ct.model}')(documents)
        else:
            # else fallback to standart records creation method in cycle
            records = []

            write_fn = getattr(self, f'records_for_{ct.model}')

            for document in documents:
                records.extend(write_fn(document))

        # save records to DB
        self.get_queryset().bulk_create(records)


class DependentLedgerRecord(models.Model):
    """Dependent ledger record abstract class.

    These records have attributes:
    - registrator — a reference to an arbitrary subclass of abstracts.models.document.Document.
    Implemented via contenttypes Generic Foreign Key (registrator_content_type + registrator_id).
    - enabled — a flag to specify whether this record is active and can be used in aggregates.

    ALLOWED_REGISTRATOR_DESCRIPTORS — used to limit documents which may write in this ledger.
    """

    class Meta:
        abstract = True

        # recommended indexes (add to subclasses)
        indexes = [
            models.Index(
                fields=["registrator_content_type", "registrator_id", "line_index", "enabled", ],
            ),
            HashIndex(
                fields=["registrator_id", ],
            ),
        ]

        # recommended constraints (copy to subclasses)
        constraints = [
            models.UniqueConstraint(
                fields=["registrator_content_type", "registrator_id", "line_index", ],
                name="unique_record",
            )
        ]

    ALLOWED_REGISTRATOR_DESCRIPTORS: list[str] = None

    registrator_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        verbose_name=_('registrator content type'),
    )
    registrator_id = models.CharField(
        max_length=36,
        null=False,
        blank=False,
        verbose_name=_('registrator id'),
    )
    registrator = GenericForeignKey(
        'registrator_content_type',
        'registrator_id',
    )
    line_index = models.PositiveIntegerField(
        null=False,
        blank=False,
        verbose_name=_('line index across this document'),
    )
    enabled = models.BooleanField(
        null=False,
        blank=False,
        default=True,
        verbose_name=_('this record activity flag'),
    )

    objects = DependentLedgerManager()
