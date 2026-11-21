from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from . import services
from .context import ADMIN, CASHIER, OFFICER
from .models import Client, Loan, LoanApplication, LoanType, Notification, Payment, Penalty, RepaymentSchedule, User
from .serializers import (ClientSerializer, LoanApplicationSerializer, LoanSerializer, LoanTypeSerializer,
                          NotificationSerializer, PaymentSerializer, PenaltySerializer,
                          RepaymentScheduleSerializer, UserSerializer)


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    write_roles = (OFFICER,)

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get('search')
        if q:
            qs = qs.filter(last_name__icontains=q) | qs.filter(first_name__icontains=q)
        return qs

    def perform_create(self, serializer):
        client = serializer.save(registered_by=self.request.user)
        point = services.geocode_address(client.address)
        if point:
            client.latitude, client.longitude = point
            client.save(update_fields=['latitude', 'longitude'])


class LoanTypeViewSet(viewsets.ModelViewSet):
    queryset = LoanType.objects.all()
    serializer_class = LoanTypeSerializer
    write_roles = ()


class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = LoanApplication.objects.select_related('client', 'loan_type')
    serializer_class = LoanApplicationSerializer
    write_roles = (OFFICER,)
    read_roles = (OFFICER,)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        application = self.get_object()
        try:
            loan = services.approve_application(application, request.user)
        except ValueError as error:
            raise ValidationError(str(error))
        return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        application = self.get_object()
        try:
            services.reject_application(application, request.user, request.data.get('remarks', ''))
        except ValueError as error:
            raise ValidationError(str(error))
        return Response(self.get_serializer(LoanApplication.objects.get(pk=application.pk)).data)


class LoanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Loan.objects.select_related('application__client').prefetch_related('schedule')
    serializer_class = LoanSerializer


class ScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RepaymentSchedule.objects.all()
    serializer_class = RepaymentScheduleSerializer


class PaymentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    write_roles = (CASHIER,)
    read_roles = (CASHIER, OFFICER)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            payment = services.record_payment(data['loan'], data['amount'], data['method'], request.user, data['payment_date'])
        except ValueError as error:
            raise ValidationError(str(error))
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)


class PenaltyViewSet(viewsets.ModelViewSet):
    queryset = Penalty.objects.all()
    serializer_class = PenaltySerializer
    http_method_names = ['get', 'patch', 'head', 'options']
    write_roles = (OFFICER,)
    read_roles = (OFFICER,)


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']
    write_roles = (OFFICER, CASHIER)

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        return qs if user.is_admin_role else qs.filter(user=user)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.select_related('role')
    serializer_class = UserSerializer
    read_roles = ()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def estimate_view(request):
    if not request.user.is_authenticated:
        return Response({'detail': 'Sign in first.'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        loan_type = get_object_or_404(LoanType, pk=int(request.query_params.get('loan_type')))
        amount = float(request.query_params.get('amount'))
        term = int(request.query_params.get('term'))
        if amount <= 0 or term < 1:
            raise ValueError
    except (TypeError, ValueError):
        return Response({'detail': 'Provide loan_type, amount and term.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(services.estimate(amount, term, loan_type))
