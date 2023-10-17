from django.db import models

from .base import LedgerField


class Resource(LedgerField):
    pass


class Integer(Resource):

    @property
    def django_field(self):
        return models.IntegerField(
            null=self._null,
            blank=self._null,
        )
