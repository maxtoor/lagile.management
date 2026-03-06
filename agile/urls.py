from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminOverviewView,
    AdminUserAutoApproveView,
    ChangeRequestViewSet,
    LoginView,
    MeView,
    MonthHolidaysView,
    MonthlyPlanViewSet,
    ServerDateView,
)

router = DefaultRouter()
router.register(r'plans', MonthlyPlanViewSet, basename='plans')
router.register(r'change-requests', ChangeRequestViewSet, basename='change-requests')

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/me/', MeView.as_view(), name='me'),
    path('auth/server-date/', ServerDateView.as_view(), name='server-date'),
    path('admin/overview/', AdminOverviewView.as_view(), name='admin-overview'),
    path('admin/users/<int:user_id>/auto-approve/', AdminUserAutoApproveView.as_view(), name='admin-user-auto-approve'),
    path('holidays/month/', MonthHolidaysView.as_view(), name='month-holidays'),
    path('', include(router.urls)),
]
