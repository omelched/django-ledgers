from django_cte import CTEManager

from ledgers.models.ledgers.bases import PeriodicLedgerRecord


class CumulativeLedgerTotalsRecord(PeriodicLedgerRecord):
    """ Cumulative ledger totals records.

    This is an implementation of 1C's totals tables.
    Source:
        - https://its.1c.ru/db/pubapplied/content/123/hdoc (writing)
        - https://its.1c.ru/db/pubapplied/content/130/hdoc (querying)

    A brief explanation:

    To optimize querying remains for specific date, totals are calculated and stored.
    Totals are calculated and stored for final date (datetime.datetime.max).

    Algorithm to query remains for arbitraty date `date`:
    - get value from "totals table"
    - get all records from "movements table" between `date` and datetime.datetime.max
    - aggregate(sum) records from movements table
    - substract "movements table"'s aggregates from "totals table"'s value

    e.g.

    totals table:
    9999-12-31 23:59:59 — 500                       (_TOTALS_FINAL)

    and movements table:
    ...
    2023-04-20 00:00:00 — +100                      (m1)
    2023-04-21 00:00:00 — -250                      (m2)
    2023-04-25 00:00:00 — -350                      (m3)
    2023-04-26 00:00:00 — +100                      (m4)
    ...

    Then querying for date "2023-04-23 00:00:00" will be as:
     500             - ( -350 + 100 ) = 750
    (__TOTALS_FINAL)     (m3)  (m4)

    Totals are recalculated either:
    - manually
    - on movements tavle write

    This ensures that querying old data is not affected by the size of ledger movements,
    but rather from frequency of records per totals period.
    """

    class Meta(PeriodicLedgerRecord.Meta):
        abstract = True
        indexes = [
            *PeriodicLedgerRecord.Meta.indexes,
        ]

    objects = CTEManager()
