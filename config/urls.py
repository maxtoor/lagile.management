from django.contrib import admin
from django.urls import include, path

from agile.web_views import AdminApprovalsView, AdminChangeRequestsView, AdminOverviewPageView, EmployeeAppView

urlpatterns = [
    path('admin/approvals/', AdminApprovalsView.as_view(), name='admin-approvals'),
    path('admin/change-requests/', AdminChangeRequestsView.as_view(), name='admin-change-requests'),
    path('admin/overview/', AdminOverviewPageView.as_view(), name='admin-overview-page'),
    path('', EmployeeAppView.as_view(), name='employee-app'),
    path('admin/', admin.site.urls),
    path('api/', include('agile.urls')),
]
