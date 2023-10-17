from django.apps import AppConfig


class LedgersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ledgers'

    def __init__(self, app_name, app_module):
        super(LedgersConfig, self).__init__(app_name, app_module)
        self.ledgers = {}
        self.documents = {}

    def register_ledger(self, app_label, ledger):
        ledger_name = ledger.__name__.lower()
        self.ledgers[f'{app_label}.{ledger_name}'] = ledger

    def register_document(self, document):
        doc_name = document.__name__.lower()
        self.documents[f'{document._meta.app_label}.{doc_name}'] = document

    def ready(self):
        from ledgers.models import Document

        for model in self.apps.get_models():
            if issubclass(model, Document):
                self.register_document(model)

