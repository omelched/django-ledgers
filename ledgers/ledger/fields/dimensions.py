from django.db import models

from .base import LedgerField


class Dimension(LedgerField):
    pass


class ForeignKey(Dimension):

    def __init__(self, to, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._to = to

    @property
    def django_field(self):
        return models.ForeignKey(
            to=self._to,
            on_delete=models.SET_NULL if self._null else models.CASCADE,
            null=self._null,
            blank=self._null,
            related_name=f'%(app_label)s_%(class)s',
        )

    @property
    def db_name(self) -> str:
        return f'{self._name}_id'
