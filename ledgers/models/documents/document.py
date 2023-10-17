from typing import Iterable, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ledgers.ledger import CumulativeLedger

from collections import defaultdict

from django.apps import apps
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.postgres.indexes import HashIndex

from ledgers.enum import DocumentStateEnum
from ledgers.models.documents import DocumentIterator


class DocumentQueryset(models.QuerySet):
    """
    Document Queryset class.

    Adds methods:
    - bulk_actualize_document_number — recalculates document number in bulk
    - bulk_write_ledger_records
    - bulk_resave_related_documents

    and extends some...

    """

    model: 'Document'

    def bulk_actualize_document_number(self, documents: Iterable['Document']) -> None:
        """
        This method recalculates document number for a list of documents inplace (without saving to DB).

        :param documents: a list of documents
        :type documents: Iterable[ledgers.models.document.doc.Document]
        """

        prefixes_and_docs: dict[str, list['Document']] = defaultdict(list)

        # noinspection PyArgumentList
        for _doc in sorted(documents, lambda d: d.execution_date):
            prefixes_and_docs[_doc.prefix].append(_doc)

        for prefix, documents in prefixes_and_docs.items():
            model = documents[0].__class__

            next_iterator = DocumentIterator.objects.next_iterator(model, prefix, len(documents))

            for index, doc in enumerate(documents):
                doc.number_prefix = prefix
                doc.number_iterator = next_iterator + index

                doc.number = f'{doc.number_prefix}-{str(doc.number_iterator).zfill(13)}'

    @transaction.atomic
    def bulk_write_ledger_records(self, documents: Iterable['Document']) -> None:
        """
        This method executes records creation for every related ledger.

        :param documents: a list of documents
        :type documents: Iterable[ledgers.models.document.doc.Document]
        """

        for ledger in self.model.DocumentMeta.related_ledgers:
            if isinstance(ledger, str):
                ledger = apps.get_app_config('ledgers').ledgers[ledger.lower()]

            ledger.bulk_write(documents)

    @transaction.atomic
    def bulk_resave_related_documents(self, documents: Iterable['Document']) -> None:
        """
        This method resaves related documents.

        :param documents: a list of documents
        :type documents: Iterable[ledgers.models.document.doc.Document]
        """

        for lookup in self.model.DocumentMeta.related_documents_lookups:
            related_field = getattr(self.model, lookup, None).field

            docs = list(
                related_field.model.objects.filter(
                    **{
                        f'{related_field.name}__in': documents,
                    }
                ).prefetch_related(
                    related_field.name
                ).all()
            )

            for doc in docs:
                parent_doc: Document = getattr(doc, related_field.name)
                doc.state = parent_doc.state
                doc.execution_date = parent_doc.execution_date

            related_field.model.objects.bulk_save(docs)

    @transaction.atomic
    def _prepare_for_bulk_create(self, objs):
        """
        This extension ensures that document number is generated for new documents.
        """
        super(DocumentQueryset, self)._prepare_for_bulk_create(objs)

        self.bulk_actualize_document_number(objs)

    @transaction.atomic
    def _after_bulk_update(self, documents: Iterable['Document']) -> None:
        """
        This method ensures that all ledger records and related documents will be created/updated after bulk update.

        :param documents: a list of updated documents
        :type documents: Iterable[ledgers.models.document.doc.Document]
        """

        self.bulk_write_ledger_records(documents)
        self.bulk_resave_related_documents(documents)

    @transaction.atomic
    def bulk_create(self, objs, *args, **kwargs):
        """
        This extension ensures that all ledger records and related documents will be created/updated after bulk create.
        """

        objs = super(DocumentQueryset, self).bulk_create(objs, *args, **kwargs)

        self._after_bulk_update(objs)

        return objs

    @transaction.atomic
    def bulk_update(self, objs, fields, batch_size=None):
        """
        This extension ensures that all ledger records and related documents will be created/updated after bulk create.
        """

        objs = super(DocumentQueryset, self).bulk_update(objs, fields, batch_size)

        self._after_bulk_update(objs)

        return objs

    def update(self, **kwargs):
        """
        Extends update method to write records to ledgers.
        """
        result = super().update(**kwargs)

        self._after_bulk_update(self)

        return result

    @transaction.atomic
    def delete(self):
        """
        Extends delete method to write "empty" records to ledgers at first, and then proceed to deletion.
        """
        self.update(_deleted=True)

        return super().delete()


class Document(models.Model):
    """
    Document abstract class.

    Documents are data aggregations, which atomically modifies database upon save,
    through ledgers and related documents.

    Document-specific attributes:
    - state — current state of document — active or draft.
        It is a convention, that draft document will not have any ledger records.
    - execution_date — a "date" of document
    - number_prefix, number_iterator, number — document's unique number and its elements

    """

    class Meta:
        abstract = True
        indexes = [
            HashIndex(fields=['number']),
            models.Index(fields=['number_prefix', 'number_iterator']),
            models.Index(fields=['execution_date']),
        ]

    class DocumentMeta:
        """
        A Document metadata class which stores:
        - related_ledgers — a list of ledgers, records to which will be written upon save
        - related_documents_lookups — a list of reverse lookups to this model to find "related" documents
        - default_prefix — a string which contains default prefix
        """
        # TODO: assert is an abstract.src.CumulativeLedger descriptor / class
        related_ledgers: list[Union['CumulativeLedger', str]] = []

        # TODO: assert is a reverse lookup to Document
        # TODO: assert no circular dependencies
        related_documents_lookups: list[str] = []

        default_prefix: str = 'DOC'

    state = models.CharField(
        null=False,
        blank=False,
        max_length=1,
        choices=DocumentStateEnum.choices,
        default=DocumentStateEnum.DRAFT,
        editable=True,
        verbose_name=_('document state'),
    )
    _deleted = models.BooleanField(
        default=False,
        null=False,
        blank=False,
        editable=False,
        verbose_name=_('marked as deleted')
    )
    execution_date = models.DateTimeField(
        null=False,
        blank=False,
        default=timezone.now,
        editable=True,
        verbose_name=_('document execution date'),
    )
    number_prefix = models.CharField(
        max_length=3,
        null=False,
        blank=False,
        editable=False,
        verbose_name=_('document prefix'),
    )
    number_iterator = models.PositiveIntegerField(
        null=False,
        blank=False,
        editable=False,
        verbose_name=_('document number (as integer)'),
    )
    number = models.CharField(
        max_length=13,
        null=False,
        blank=False,
        editable=False,
        verbose_name=_('document number'),
    )

    objects = models.Manager.from_queryset(DocumentQueryset)()

    @property
    def prefix(self) -> str:
        """
        Default prefix may be overriden by instance data.

        :return: document's prefix
        :rtype: str
        """

        return self.DocumentMeta.default_prefix

    def actualize_document_number(self) -> None:
        """
        Method recalculates document number.

        Document number template is XXX-0000000000000
                              prefix ^        ^ iterator
        """
        self.number_prefix = self.prefix

        self.number_iterator = DocumentIterator.objects.next_iterator(self.__class__, self.number_prefix)

        self.number = f'{self.number_prefix}-{str(self.number_iterator).zfill(13)}'

    def direct_save(self) -> None:
        """
        A fallback method to save document without triggering ledger / related doc saves.
        """
        super(Document, self).save()

    @transaction.atomic
    def write_ledgers_records(self) -> None:
        """
        This method writes ledger records for document.
        """
        for ledger in self.DocumentMeta.related_ledgers:
            if isinstance(ledger, str):
                ledger = apps.get_app_config('ledgers').ledgers[ledger.lower()]

            ledger.write(self)

    @transaction.atomic
    def resave_related_documents(self) -> None:
        """
        This method resaves all related documents.

        It changes 'state', 'execution_date' and '_deleted' arguments to match parent document.

        """

        for lookup in self.DocumentMeta.related_documents_lookups:
            related_field = getattr(self.__class__, lookup, None).field
            docs = list(
                related_field.model.objects.filter(
                    **{
                        f'{related_field.name}': self,
                    }
                ).prefetch_related(
                    related_field.name
                ).all()
            )

            for doc in docs:
                doc.state = self.state
                doc.execution_date = self.execution_date

            related_field.model.objects.bulk_update(docs, ['state', 'execution_date', '_deleted'])

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Extends save method to ensure that instance has document number, writes ledger records and
        resaves related documents after original save.
        """
        if not self.number:
            self.actualize_document_number()

        super(Document, self).save(*args, **kwargs)

        self.write_ledgers_records()
        self.resave_related_documents()

    @transaction.atomic
    def delete(self, *args, **kwargs):
        """
        Extends delete method to write "empty" records to ledgers at first, and then proceed to deletion.
        """
        self._deleted = True
        self.save(update_fields=['_deleted'])

        super(Document, self).delete(*args, **kwargs)

    @property
    def deleted(self):
        return self._deleted

    def __str__(self):
        return f'{self.number}'
