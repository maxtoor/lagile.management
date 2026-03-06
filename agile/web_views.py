from django.views.generic import TemplateView

from .runtime_settings import build_runtime_ui_context, get_runtime_setting


class BasePortalView(TemplateView):
    template_name = 'employee_app.html'
    app_page = 'programming'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['app_page'] = self.app_page
        context['date_display_format'] = get_runtime_setting('AGILE_DATE_DISPLAY_FORMAT', 'IT')
        context.update(build_runtime_ui_context())
        return context


class EmployeeAppView(BasePortalView):
    app_page = 'programming'


class ProfilePageView(BasePortalView):
    app_page = 'profile'


class AdminApprovalsView(BasePortalView):
    app_page = 'approvals'


class AdminChangeRequestsView(BasePortalView):
    app_page = 'changes'


class AdminOverviewPageView(BasePortalView):
    app_page = 'overview'
