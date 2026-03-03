from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from .models import ChangeRequest, MonthlyPlan, PlanDay, User


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)

    @staticmethod
    def _normalize_login_username(raw_username: str) -> str:
        username = (raw_username or '').strip()
        if '@' in username:
            local_part = username.split('@', 1)[0].strip()
            if local_part:
                return local_part
        return username

    def validate(self, attrs):
        normalized_username = self._normalize_login_username(attrs.get('username', ''))
        user = authenticate(username=normalized_username, password=attrs['password'])
        if not user:
            if normalized_username:
                user_model = get_user_model()
                candidate = user_model.objects.filter(username=normalized_username).only('id', 'is_active').first()
                if candidate and not candidate.is_active:
                    raise serializers.ValidationError('Utente non attivo, contattare amministratore')
            raise serializers.ValidationError('Credenziali non valide')
        attrs['username'] = normalized_username
        attrs['user'] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    manager_id = serializers.IntegerField(source='manager.id', read_only=True, allow_null=True)
    manager_name = serializers.SerializerMethodField()

    def get_manager_name(self, obj):
        manager = obj.manager
        if not manager:
            return ''
        full_name = f'{manager.first_name} {manager.last_name}'.strip()
        return full_name or manager.username

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'department',
            'manager_id',
            'manager_name',
            'role',
            'aila_subscribed',
            'auto_approve',
            'is_staff',
            'is_superuser',
        )


class PlanDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanDay
        fields = ('id', 'day', 'work_type', 'notes')


class MonthlyPlanSerializer(serializers.ModelSerializer):
    days = PlanDaySerializer(many=True)
    user = UserSerializer(read_only=True)
    approved_days_snapshot = serializers.JSONField(read_only=True)
    has_pending_change_request = serializers.SerializerMethodField()
    has_approved_snapshot = serializers.SerializerMethodField()
    latest_change_request_status = serializers.SerializerMethodField()
    latest_change_request_response_reason = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyPlan
        fields = (
            'id',
            'user',
            'year',
            'month',
            'status',
            'submitted_at',
            'approved_by',
            'approved_at',
            'rejection_reason',
            'approved_days_snapshot',
            'has_pending_change_request',
            'has_approved_snapshot',
            'latest_change_request_status',
            'latest_change_request_response_reason',
            'days',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('status', 'submitted_at', 'approved_by', 'approved_at', 'created_at', 'updated_at')

    def get_has_pending_change_request(self, obj):
        return obj.change_requests.filter(status=ChangeRequest.Status.PENDING).exists()

    def _get_latest_change_request(self, obj):
        return obj.change_requests.order_by('-created_at').first()

    def get_has_approved_snapshot(self, obj):
        return bool(obj.approved_days_snapshot)

    def get_latest_change_request_status(self, obj):
        latest = self._get_latest_change_request(obj)
        return latest.status if latest else None

    def get_latest_change_request_response_reason(self, obj):
        latest = self._get_latest_change_request(obj)
        if not latest or latest.status != ChangeRequest.Status.REJECTED:
            return ''
        return latest.response_reason or ''

    def validate(self, attrs):
        month = attrs.get('month', getattr(self.instance, 'month', None))
        year = attrs.get('year', getattr(self.instance, 'year', None))
        if month and (month < 1 or month > 12):
            raise serializers.ValidationError('Mese non valido')
        if year and year < 2000:
            raise serializers.ValidationError('Anno non valido')
        if 'days' in attrs and month:
            user = getattr(self.instance, 'user', None) or self.context['request'].user
            try:
                MonthlyPlan.validate_day_payloads(
                    year=year,
                    month=month,
                    department=user.department,
                    day_payloads=attrs['days'],
                )
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages)
        return attrs

    def create(self, validated_data):
        days = validated_data.pop('days', [])
        plan = MonthlyPlan.objects.create(**validated_data)
        for day in days:
            PlanDay.objects.create(plan=plan, **day)
        return plan

    def update(self, instance, validated_data):
        validated_data.pop('status', None)
        days = validated_data.pop('days', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()

        if days is not None:
            instance.days.all().delete()
            for day in days:
                PlanDay.objects.create(plan=instance, **day)

        return instance


class ApprovalSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs['approve'] and not attrs.get('reason'):
            raise serializers.ValidationError('La motivazione e obbligatoria in caso di rifiuto')
        return attrs


class ChangeRequestSerializer(serializers.Serializer):
    reason = serializers.CharField()

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError('La motivazione e obbligatoria')
        return value.strip()


class ChangeRequestItemSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    plan_month = serializers.IntegerField(source='plan.month', read_only=True)
    plan_year = serializers.IntegerField(source='plan.year', read_only=True)
    plan_status = serializers.CharField(source='plan.status', read_only=True)
    plan_user_username = serializers.CharField(source='plan.user.username', read_only=True)
    processed_by_username = serializers.CharField(source='processed_by.username', read_only=True, allow_null=True)

    class Meta:
        model = ChangeRequest
        fields = (
            'id',
            'user',
            'plan',
            'plan_month',
            'plan_year',
            'plan_status',
            'plan_user_username',
            'reason',
            'response_reason',
            'status',
            'processed_by',
            'processed_by_username',
            'processed_at',
            'created_at',
        )


class ChangeRequestReviewSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs['approve'] and not attrs.get('reason'):
            raise serializers.ValidationError('La motivazione e obbligatoria in caso di rifiuto')
        return attrs
