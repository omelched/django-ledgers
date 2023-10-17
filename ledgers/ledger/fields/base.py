from abc import ABCMeta

from django.db import models


class LedgerField(metaclass=ABCMeta):
    def __init__(self, null=True):
        self._null = null
        self._name = None

    @property
    def name(self) -> None | str:
        return self._name

    @property
    def django_field(self) -> models.Field:
        raise NotImplemented

    def set_name(self, value: str) -> None:
        self._name = value

    @property
    def db_name(self) -> str:
        return self._name
