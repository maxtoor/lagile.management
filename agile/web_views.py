from django.views.generic import TemplateView
from django.conf import settings


class BasePortalView(TemplateView):
    template_name = 'employee_app.html'
    app_page = 'programming'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['app_page'] = self.app_page
        context['date_display_format'] = settings.AGILE_DATE_DISPLAY_FORMAT
        context['login_logo_url'] = settings.AGILE_LOGIN_LOGO_URL
        context['company_name'] = settings.AGILE_COMPANY_NAME
        context['copyright_year'] = settings.AGILE_COPYRIGHT_YEAR
        return context


class EmployeeAppView(BasePortalView):
    app_page = 'programming'


class AdminApprovalsView(BasePortalView):
    app_page = 'approvals'


class AdminChangeRequestsView(BasePortalView):
    app_page = 'changes'


class AdminOverviewPageView(BasePortalView):
    app_page = 'overview'
