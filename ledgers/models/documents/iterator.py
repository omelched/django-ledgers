from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ledgers.models import Document

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ledgers.utils.decorators import concurrent_transaction


class DocumentIteratorManager(models.Manager):

    @concurrent_transaction
    def _next_iterator(self, content_type_id: str, prefix: str, increment: int = 1) -> int:
        """
        To save modifications "outside" possible atomic block — this method is called in separate thread.
        This might result in a deadlock if "parent" thread locks this table.

        :param content_type_id: contenttype id
        :type content_type_id: str
        :param prefix: prefix lookup
        :type prefix: str
        :param increment: increment amount
        :type increment: int

        :return: next iterator from database
        :rtype: int
        """

        iterator, created = self.get_queryset().select_for_update().get_or_create(
            model_id=content_type_id,
            prefix=prefix,
            defaults={
                'number': increment,
            }
        )

        if created:
            return 1

        result = iterator.number

        iterator.number = models.F('number') + increment
        iterator.save()

        return result

    def next_iterator(self, document_model: 'Document', prefix: str, increment: int = 1) -> int:
        """
        This method gets next iterator for given document model and prefix.

        To solve race conditions, filtered row is locked, as there is no native Django
        '... RETURNING ...' implementation.

        :param document_model: document model
        :type document_model: ledgers.models.document.doc.Document
        :param prefix: prefix lookup
        :type prefix: str
        :param increment: increment amount
        :type increment: int

        :return: next iterator from database
        :rtype: int
        """

        content_type = ContentType.objects.get_for_model(document_model)

        return self._next_iterator(content_type.pk, prefix, increment)

    @transaction.atomic
    def rebuid(self):
        self.get_queryset().select_for_update().delete()

        iterators = []

        for descriptor, document_model in self.model.app_config.documents.items():
            content_type_id = ContentType.objects.get_for_model(document_model).pk

            qs = document_model.objects.values('number_prefix').annotate(
                max_iterator=models.Max('number_iterator')
            )

            for item in qs:
                iterators.append(
                    self.model(
                        model_id=content_type_id,
                        prefix=item['prefix'],
                        number=item['max_iterator'],
                    )
                )

        self.get_queryset().bulk_create(iterators)


class DocumentIterator(models.Model):
    """
    This model stores last number iterator for given document model and prefix.
    """

    class Meta:
        indexes = [
            models.Index(fields=['model', 'prefix']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['model', 'prefix'],
                name='u_model_prefix',
            ),
        ]

    model = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name='iterators',
        null=False,
        blank=False,
        editable=False,
        verbose_name=_('document model'),
    )
    prefix = models.CharField(
        max_length=3,
        null=False,
        blank=False,
        editable=False,
        verbose_name=_('document prefix'),
    )
    number = models.PositiveIntegerField(
        null=False,
        blank=False,
        editable=False,
        verbose_name=_('document number (as integer)'),
    )

    objects = DocumentIteratorManager()
