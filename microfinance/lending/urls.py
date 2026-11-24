from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api, views

router = DefaultRouter()
router.register('clients', api.ClientViewSet, basename='api-client')
router.register('loan-types', api.LoanTypeViewSet, basename='api-loantype')
router.register('applications', api.ApplicationViewSet, basename='api-application')
router.register('loans', api.LoanViewSet, basename='api-loan')
router.register('schedules', api.ScheduleViewSet, basename='api-schedule')
router.register('payments', api.PaymentViewSet, basename='api-payment')
router.register('penalties', api.PenaltyViewSet, basename='api-penalty')
router.register('notifications', api.NotificationViewSet, basename='api-notification')
router.register('users', api.UserViewSet, basename='api-user')

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),

    path('signup/', views.SignupView.as_view(), name='signup'),
    path('portal/', views.PortalHome.as_view(), name='portal_home'),
    path('portal/apply/', views.PortalApply.as_view(), name='portal_apply'),

    path('clients/', views.ClientList.as_view(), name='client_list'),
    path('clients/new/', views.ClientCreate.as_view(), name='client_create'),
    path('clients/map/', views.ClientMap.as_view(), name='client_map'),
    path('clients/map/locate/', views.ClientGeocode.as_view(), name='client_geocode'),
    path('clients/<int:pk>/', views.ClientDetail.as_view(), name='client_detail'),
    path('clients/<int:pk>/edit/', views.ClientUpdate.as_view(), name='client_update'),
    path('clients/<int:pk>/delete/', views.ClientDelete.as_view(), name='client_delete'),
    path('clients/<int:pk>/id/<slug:side>/', views.ClientIdImage.as_view(), name='client_id_image'),

    path('applications/', views.ApplicationList.as_view(), name='application_list'),
    path('applications/new/', views.ApplicationCreate.as_view(), name='application_create'),
    path('applications/<int:pk>/', views.ApplicationDetail.as_view(), name='application_detail'),
    path('applications/<int:pk>/edit/', views.ApplicationUpdate.as_view(), name='application_update'),
    path('applications/<int:pk>/delete/', views.ApplicationDelete.as_view(), name='application_delete'),
    path('applications/<int:pk>/decide/', views.ApplicationDecide.as_view(), name='application_decide'),

    path('loans/', views.LoanList.as_view(), name='loan_list'),
    path('loans/<int:pk>/', views.LoanDetail.as_view(), name='loan_detail'),

    path('payments/', views.PaymentList.as_view(), name='payment_list'),
    path('payments/new/', views.PaymentCreate.as_view(), name='payment_create'),
    path('payments/<int:pk>/receipt/', views.PaymentReceipt.as_view(), name='payment_receipt'),

    path('penalties/', views.PenaltyList.as_view(), name='penalty_list'),
    path('penalties/<int:pk>/action/', views.PenaltyAction.as_view(), name='penalty_action'),
    path('loan-types/new/', views.LoanTypeCreate.as_view(), name='loantype_create'),
    path('loan-types/<int:pk>/edit/', views.LoanTypeUpdate.as_view(), name='loantype_update'),
    path('loan-types/<int:pk>/delete/', views.LoanTypeDelete.as_view(), name='loantype_delete'),

    path('reports/', views.ReportView.as_view(), name='report'),

    path('notifications/', views.NotificationList.as_view(), name='notification_list'),
    path('notifications/action/', views.NotificationAction.as_view(), name='notification_action'),

    path('users/', views.UserList.as_view(), name='user_list'),
    path('users/new/', views.UserCreate.as_view(), name='user_create'),
    path('users/<int:pk>/edit/', views.UserUpdate.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', views.UserDelete.as_view(), name='user_delete'),

    path('backup/', views.BackupView.as_view(), name='backup'),

    path('api/estimate/', api.estimate_view, name='api_estimate'),
    path('api/', include(router.urls)),
    path('backup/<int:pk>/download/', views.BackupDownload.as_view(), name='backup_download'),
]
