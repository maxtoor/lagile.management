from django.apps import AppConfig


class AgileConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agile'
    verbose_name = 'LAgile'

    def ready(self):
        # Ensure monitor polling requests do not flood access logs.
        import logging
        from .logging_filters import ExcludeLogMonitorPollFilter

        server_logger = logging.getLogger('django.server')
        server_logger.addFilter(ExcludeLogMonitorPollFilter())
