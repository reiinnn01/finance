from rest_framework import serializers

from .models import Client, Loan, LoanApplication, LoanType, Notification, Payment, Penalty, RepaymentSchedule, User


class ClientSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Client
        exclude = ['id_front', 'id_back']
        read_only_fields = ['registered_by', 'created_at']


class LoanTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanType
        fields = '__all__'


class LoanApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanApplication
        fields = '__all__'
        read_only_fields = ['status', 'processed_by', 'remarks', 'applied_at', 'decided_at']

    def validate(self, data):
        loan_type = data.get('loan_type', getattr(self.instance, 'loan_type', None))
        amount = data.get('amount_requested', getattr(self.instance, 'amount_requested', None))
        term = data.get('term_months', getattr(self.instance, 'term_months', None))
        if loan_type and amount and amount > loan_type.max_amount:
            raise serializers.ValidationError({'amount_requested': f'Maximum is {loan_type.max_amount}.'})
        if loan_type and term and term > loan_type.max_term_months:
            raise serializers.ValidationError({'term_months': f'Maximum is {loan_type.max_term_months} months.'})
        return data


class RepaymentScheduleSerializer(serializers.ModelSerializer):
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = RepaymentSchedule
        fields = '__all__'


class LoanSerializer(serializers.ModelSerializer):
    client = serializers.CharField(source='client.full_name', read_only=True)
    schedule = RepaymentScheduleSerializer(many=True, read_only=True)

    class Meta:
        model = Loan
        fields = '__all__'


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['schedule', 'received_by', 'receipt_no']


class PenaltySerializer(serializers.ModelSerializer):
    class Meta:
        model = Penalty
        fields = '__all__'
        read_only_fields = ['schedule', 'days_late', 'amount', 'date_applied']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['client', 'user', 'loan', 'type', 'message', 'sent_at']


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ['user_id', 'username', 'full_name', 'email', 'role', 'role_name', 'is_active', 'created_at']
