from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy


class DocumentStateEnum(models.TextChoices):
    DRAFT = 'D', _('Draft')
    ACTIVE = 'A', pgettext_lazy('document state', 'Active')


class CumulativeLedgerRecordActionEnum(models.TextChoices):
    INCOME = 'I', _('Income')
    OUTCOME = 'O', _('Outcome')


class CumulativeLedgerSettingsTotalsPeriodEnum(models.TextChoices):
    DAY = 'D', _('Day')
    WEEK = 'W', _('Week')
    MONTH = 'M', _('Month')
    QUARTER = 'Q', _('Quarter')
    YEAR = 'Y', _('Year')
