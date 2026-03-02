import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog, ChangeRequest, MonthlyPlan
from .permissions import IsAdminOrSuperAdmin
from .serializers import (
    ApprovalSerializer,
    ChangeRequestItemSerializer,
    ChangeRequestReviewSerializer,
    ChangeRequestSerializer,
    LoginSerializer,
    MonthlyPlanSerializer,
    UserSerializer,
)
logger = logging.getLogger(__name__)


def notify_plan_review(*, plan: MonthlyPlan, approved: bool) -> None:
    recipient = plan.user.email
    if not recipient:
        return

    month_label = f'{plan.month:02d}/{plan.year}'
    status_label = 'APPROVATO' if approved else 'RIFIUTATO'
    subject = f'Esito piano lavoro agile {month_label}: {status_label}'

    lines = [
        f'Ciao {plan.user.first_name or plan.user.username},',
        '',
        f'Il tuo piano di lavoro agile per {month_label} e stato {status_label.lower()}.',
    ]
    if approved:
        lines.append('Il piano e ora definitivo.')
    else:
        lines.append(f'Motivazione rifiuto: {plan.rejection_reason or "non specificata"}')
    lines.extend(
        [
            '',
            'Puoi accedere al portale per vedere il dettaglio.',
        ]
    )
    message = '\n'.join(lines)

    send_mail(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=[recipient],
        fail_silently=False,
    )


def notify_change_request_review(*, change_request: ChangeRequest, approved: bool) -> None:
    recipient = change_request.user.email
    if not recipient:
        return

    month_label = f'{change_request.plan.month:02d}/{change_request.plan.year}'
    status_label = 'APPROVATA' if approved else 'RIFIUTATA'
    subject = f'Esito richiesta variazione {month_label}: {status_label}'

    lines = [
        f'Ciao {change_request.user.first_name or change_request.user.username},',
        '',
        f'La tua richiesta variazione per {month_label} e stata {status_label.lower()}.',
        f'Motivazione richiesta: {change_request.reason or "non specificata"}',
    ]
    if approved:
        lines.append('La variazione e stata recepita nel piano.')
    else:
        lines.append(f'Motivazione rifiuto: {change_request.response_reason or "non specificata"}')
    lines.extend(
        [
            '',
            'Puoi accedere al portale per vedere il dettaglio.',
        ]
    )
    message = '\n'.join(lines)

    send_mail(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=[recipient],
        fail_silently=False,
    )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        AuditLog.track(actor=user, action='login', target_type='User', target_id=user.id)
        return Response({'token': token.key, 'user': UserSerializer(user).data})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ServerDateView(APIView):
    def get(self, request):
        today = timezone.localdate()
        return Response(
            {
                'today': today.isoformat(),
                'year': today.year,
                'month': today.month,
                'day': today.day,
            }
        )


class MonthHolidaysView(APIView):
    def get(self, request):
        year_raw = request.query_params.get('year')
        month_raw = request.query_params.get('month')
        try:
            year = int(year_raw)
            month = int(month_raw)
        except (TypeError, ValueError):
            return Response({'detail': 'Parametri year e month obbligatori'}, status=status.HTTP_400_BAD_REQUEST)

        if month < 1 or month > 12:
            return Response({'detail': 'Mese non valido'}, status=status.HTTP_400_BAD_REQUEST)

        holiday_labels = MonthlyPlan.holiday_labels_for_month(
            year=year,
            month=month,
            department=request.user.department,
        )
        holiday_days = sorted(holiday_labels.keys())
        items = [{'day': day.isoformat(), 'name': holiday_labels.get(day, 'Festivita')} for day in holiday_days]
        return Response(
            {
                'days': [day.isoformat() for day in holiday_days],
                'items': items,
                'count': len(holiday_days),
            }
        )


class MonthlyPlanViewSet(viewsets.ModelViewSet):
    serializer_class = MonthlyPlanSerializer

    @staticmethod
    def _current_year_month() -> tuple[int, int]:
        today = timezone.localdate()
        return today.year, today.month

    @classmethod
    def _next_year_month(cls) -> tuple[int, int]:
        year, month = cls._current_year_month()
        if month == 12:
            return year + 1, 1
        return year, month + 1

    @staticmethod
    def _is_superadmin_user(user) -> bool:
        return bool(user.is_superuser or user.role == 'SUPERADMIN')

    @classmethod
    def _is_admin_user(cls, user) -> bool:
        return bool(cls._is_superadmin_user(user) or user.is_staff or user.role == 'ADMIN')

    @staticmethod
    def _has_aila_subscription(user) -> bool:
        return bool(getattr(user, 'aila_subscribed', False))

    def _assert_programming_enabled(self, *, plan_owner_id: int | None = None) -> None:
        if plan_owner_id is not None and plan_owner_id != self.request.user.id:
            return
        if self._has_aila_subscription(self.request.user):
            return
        raise ValidationError('Programmazione non disponibile: Sottoscrizione AILA impostata su No')

    def _assert_employee_can_edit(self, *, year: int, month: int) -> None:
        next_year, next_month = self._next_year_month()
        current_year, current_month = self._current_year_month()
        if (year, month) == (next_year, next_month):
            return
        if (year, month) == (current_year, current_month):
            return
        raise ValidationError('Puoi modificare solo il mese successivo')

    def get_queryset(self):
        user = self.request.user
        base = MonthlyPlan.objects.select_related('user', 'approved_by').prefetch_related('days')
        if self._is_superadmin_user(user):
            return base
        if self._is_admin_user(user):
            return base.filter(Q(user=user) | Q(user__manager=user))
        return base.filter(user=user)

    def perform_create(self, serializer):
        self._assert_programming_enabled()
        self._assert_employee_can_edit(year=serializer.validated_data['year'], month=serializer.validated_data['month'])
        plan = serializer.save(user=self.request.user)
        AuditLog.track(
            actor=self.request.user,
            action='plan_created',
            target_type='MonthlyPlan',
            target_id=plan.id,
            metadata={'year': plan.year, 'month': plan.month},
        )

    def perform_update(self, serializer):
        plan = self.get_object()
        self._assert_programming_enabled(plan_owner_id=plan.user_id)
        original_status = plan.status
        if (
            serializer.validated_data.get('year', plan.year) != plan.year
            or serializer.validated_data.get('month', plan.month) != plan.month
        ):
            raise ValidationError('Anno e mese del piano non possono essere modificati')
        self._assert_employee_can_edit(year=plan.year, month=plan.month)
        current_year, current_month = self._current_year_month()
        is_current_month = (plan.year, plan.month) == (current_year, current_month)
        updated = serializer.save()
        # Mese successivo: dopo una modifica, un piano gia inviato/approvato torna in bozza per nuova approvazione.
        if (
            not is_current_month
            and original_status in {MonthlyPlan.Status.SUBMITTED, MonthlyPlan.Status.APPROVED}
        ):
            updated.status = MonthlyPlan.Status.DRAFT
            updated.submitted_at = None
            updated.approved_by = None
            updated.approved_at = None
            updated.rejection_reason = ''
            updated.save(
                update_fields=[
                    'status',
                    'submitted_at',
                    'approved_by',
                    'approved_at',
                    'rejection_reason',
                    'updated_at',
                ]
            )
        # Nel mese corrente un piano gia approvato non deve retrocedere a bozza durante l'edit.
        if (
            is_current_month
            and original_status == MonthlyPlan.Status.APPROVED
            and updated.status != MonthlyPlan.Status.APPROVED
        ):
            updated.status = MonthlyPlan.Status.APPROVED
            updated.save(update_fields=['status', 'updated_at'])
        AuditLog.track(
            actor=self.request.user,
            action='plan_updated',
            target_type='MonthlyPlan',
            target_id=updated.id,
        )

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        plan = self.get_object()
        if plan.user_id != request.user.id:
            return Response({'detail': 'Puoi inviare solo i tuoi piani'}, status=status.HTTP_403_FORBIDDEN)
        try:
            self._assert_programming_enabled(plan_owner_id=plan.user_id)
        except ValidationError as exc:
            return Response({'detail': exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        if (plan.year, plan.month) == self._current_year_month():
            return Response({'detail': 'Per il mese corrente usa la richiesta variazione'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            self._assert_employee_can_edit(year=plan.year, month=plan.month)
        except ValidationError as exc:
            return Response({'detail': exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        try:
            plan.validate_existing_days()
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        if request.user.auto_approve:
            plan.status = MonthlyPlan.Status.APPROVED
            plan.submitted_at = now
            plan.approved_by = request.user
            plan.approved_at = now
            plan.rejection_reason = ''
            plan.save(
                update_fields=[
                    'status',
                    'submitted_at',
                    'approved_by',
                    'approved_at',
                    'rejection_reason',
                    'updated_at',
                ]
            )
            plan.capture_approved_snapshot()
            AuditLog.track(
                actor=request.user,
                action='plan_auto_approved',
                target_type='MonthlyPlan',
                target_id=plan.id,
            )
        else:
            plan.status = MonthlyPlan.Status.SUBMITTED
            plan.submitted_at = now
            plan.rejection_reason = ''
            plan.save(update_fields=['status', 'submitted_at', 'rejection_reason', 'updated_at'])
            AuditLog.track(actor=request.user, action='plan_submitted', target_type='MonthlyPlan', target_id=plan.id)
        return Response(self.get_serializer(plan).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrSuperAdmin])
    def review(self, request, pk=None):
        plan = self.get_object()
        serializer = ApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if plan.status != MonthlyPlan.Status.SUBMITTED:
            return Response({'detail': 'Solo i piani inviati possono essere revisionati'}, status=status.HTTP_400_BAD_REQUEST)

        if serializer.validated_data['approve']:
            plan.status = MonthlyPlan.Status.APPROVED
            plan.approved_by = request.user
            plan.approved_at = timezone.now()
            plan.rejection_reason = ''
            action_name = 'plan_approved'
        else:
            plan.status = MonthlyPlan.Status.REJECTED
            plan.approved_by = request.user
            plan.approved_at = timezone.now()
            plan.rejection_reason = serializer.validated_data.get('reason', '')
            action_name = 'plan_rejected'

        plan.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
        if serializer.validated_data['approve']:
            plan.capture_approved_snapshot()
        AuditLog.track(
            actor=request.user,
            action=action_name,
            target_type='MonthlyPlan',
            target_id=plan.id,
            metadata={'reason': plan.rejection_reason},
        )
        try:
            notify_plan_review(plan=plan, approved=serializer.validated_data['approve'])
            AuditLog.track(
                actor=request.user,
                action='plan_review_email_sent',
                target_type='MonthlyPlan',
                target_id=plan.id,
                metadata={'recipient': plan.user.email},
            )
        except Exception as exc:
            logger.exception('Errore invio email esito review per piano %s', plan.id)
            AuditLog.track(
                actor=request.user,
                action='plan_review_email_failed',
                target_type='MonthlyPlan',
                target_id=plan.id,
                metadata={'recipient': plan.user.email, 'error': str(exc)},
            )
        return Response(self.get_serializer(plan).data)

    @action(detail=True, methods=['post'])
    def restore_approved(self, request, pk=None):
        plan = self.get_object()
        if plan.user_id != request.user.id:
            return Response({'detail': 'Puoi ripristinare solo i tuoi piani'}, status=status.HTTP_403_FORBIDDEN)
        try:
            self._assert_programming_enabled(plan_owner_id=plan.user_id)
        except ValidationError as exc:
            return Response({'detail': exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        current_year, current_month = self._current_year_month()
        next_year, next_month = self._next_year_month()
        if (plan.year, plan.month) not in {(current_year, current_month), (next_year, next_month)}:
            return Response(
                {'detail': 'Il ripristino e consentito solo per mese corrente o mese successivo'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not plan.approved_days_snapshot:
            return Response({'detail': 'Nessun piano approvato disponibile da ripristinare'}, status=status.HTTP_400_BAD_REQUEST)

        if plan.change_requests.filter(status=ChangeRequest.Status.PENDING).exists():
            return Response({'detail': 'Non puoi ripristinare con una richiesta variazione in attesa'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                plan.restore_from_approved_snapshot()
                plan.status = MonthlyPlan.Status.APPROVED
                plan.rejection_reason = ''
                plan.save(update_fields=['status', 'rejection_reason', 'updated_at'])
                ChangeRequest.objects.create(
                    plan=plan,
                    user=plan.user,
                    reason='Ripristino all ultimo piano approvato',
                    response_reason='Ripristino eseguito',
                    status=ChangeRequest.Status.APPROVED,
                    processed_by=request.user,
                    processed_at=timezone.now(),
                )
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        AuditLog.track(
            actor=request.user,
            action='plan_restored_from_approved_snapshot',
            target_type='MonthlyPlan',
            target_id=plan.id,
        )
        return Response(self.get_serializer(plan).data)

    @action(detail=True, methods=['post'])
    def request_change(self, request, pk=None):
        plan = self.get_object()
        if plan.user_id != request.user.id:
            return Response({'detail': 'Puoi richiedere variazioni solo per i tuoi piani'}, status=status.HTTP_403_FORBIDDEN)
        try:
            self._assert_programming_enabled(plan_owner_id=plan.user_id)
        except ValidationError as exc:
            return Response({'detail': exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        current_year, current_month = self._current_year_month()
        if (plan.year, plan.month) != (current_year, current_month):
            return Response({'detail': 'La richiesta variazione e consentita solo per il mese corrente'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if plan.change_requests.filter(status=ChangeRequest.Status.PENDING).exists():
            return Response({'detail': 'Esiste gia una richiesta variazione in attesa'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        with transaction.atomic():
            if request.user.auto_approve:
                change_request = ChangeRequest.objects.create(
                    plan=plan,
                    user=request.user,
                    reason=serializer.validated_data['reason'],
                    status=ChangeRequest.Status.APPROVED,
                    response_reason='Approvazione automatica',
                    processed_by=request.user,
                    processed_at=now,
                )
                plan.status = MonthlyPlan.Status.APPROVED
                plan.approved_by = request.user
                plan.approved_at = now
                plan.rejection_reason = ''
                plan.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
                plan.capture_approved_snapshot()
                AuditLog.track(
                    actor=request.user,
                    action='plan_change_auto_approved',
                    target_type='ChangeRequest',
                    target_id=change_request.id,
                    metadata={'plan_id': plan.id},
                )
                return Response(
                    {'detail': 'Richiesta variazione approvata automaticamente', 'auto_approved': True},
                    status=status.HTTP_201_CREATED,
                )

            change_request = ChangeRequest.objects.create(
                plan=plan,
                user=request.user,
                reason=serializer.validated_data['reason'],
            )
            AuditLog.track(
                actor=request.user,
                action='plan_change_requested',
                target_type='ChangeRequest',
                target_id=change_request.id,
                metadata={'plan_id': plan.id},
            )
        return Response({'detail': 'Richiesta variazione inviata', 'auto_approved': False}, status=status.HTTP_201_CREATED)


class ChangeRequestViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminOrSuperAdmin]
    serializer_class = ChangeRequestItemSerializer

    def get_queryset(self):
        base = ChangeRequest.objects.select_related('user', 'plan', 'plan__user', 'processed_by').order_by('-created_at')
        user = self.request.user
        if MonthlyPlanViewSet._is_superadmin_user(user):
            return base
        return base.filter(Q(plan__user=user) | Q(plan__user__manager=user))

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        change_request = self.get_object()
        serializer = ChangeRequestReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if change_request.status != ChangeRequest.Status.PENDING:
            return Response({'detail': 'Solo le richieste in attesa possono essere revisionate'}, status=status.HTTP_400_BAD_REQUEST)

        approved = serializer.validated_data['approve']
        with transaction.atomic():
            change_request.status = ChangeRequest.Status.APPROVED if approved else ChangeRequest.Status.REJECTED
            change_request.response_reason = '' if approved else serializer.validated_data.get('reason', '')
            change_request.processed_by = request.user
            change_request.processed_at = timezone.now()
            change_request.save(update_fields=['status', 'response_reason', 'processed_by', 'processed_at'])

            if approved:
                plan = change_request.plan
                plan.status = MonthlyPlan.Status.APPROVED
                plan.approved_by = request.user
                plan.approved_at = timezone.now()
                plan.rejection_reason = ''
                plan.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
                plan.capture_approved_snapshot()
        AuditLog.track(
            actor=request.user,
            action='change_request_approved' if approved else 'change_request_rejected',
            target_type='ChangeRequest',
            target_id=change_request.id,
            metadata={'plan_id': change_request.plan_id, 'reason': change_request.response_reason},
        )
        try:
            notify_change_request_review(change_request=change_request, approved=approved)
            AuditLog.track(
                actor=request.user,
                action='change_request_review_email_sent',
                target_type='ChangeRequest',
                target_id=change_request.id,
                metadata={'recipient': change_request.user.email},
            )
        except Exception as exc:
            logger.exception('Errore invio email esito richiesta variazione %s', change_request.id)
            AuditLog.track(
                actor=request.user,
                action='change_request_review_email_failed',
                target_type='ChangeRequest',
                target_id=change_request.id,
                metadata={'recipient': change_request.user.email, 'error': str(exc)},
            )
        return Response(self.get_serializer(change_request).data)

    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        change_request = self.get_object()
        if change_request.status != ChangeRequest.Status.PENDING:
            return Response({'detail': 'Solo le richieste in attesa possono essere revisionate'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            change_request.status = ChangeRequest.Status.APPROVED
            change_request.response_reason = ''
            change_request.processed_by = request.user
            change_request.processed_at = timezone.now()
            change_request.save(update_fields=['status', 'response_reason', 'processed_by', 'processed_at'])

            plan = change_request.plan
            plan.status = MonthlyPlan.Status.APPROVED
            plan.approved_by = request.user
            plan.approved_at = timezone.now()
            plan.rejection_reason = ''
            plan.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
            plan.capture_approved_snapshot()
        AuditLog.track(
            actor=request.user,
            action='change_request_approved',
            target_type='ChangeRequest',
            target_id=change_request.id,
            metadata={'plan_id': change_request.plan_id},
        )
        try:
            notify_change_request_review(change_request=change_request, approved=True)
            AuditLog.track(
                actor=request.user,
                action='change_request_review_email_sent',
                target_type='ChangeRequest',
                target_id=change_request.id,
                metadata={'recipient': change_request.user.email},
            )
        except Exception as exc:
            logger.exception('Errore invio email esito richiesta variazione %s', change_request.id)
            AuditLog.track(
                actor=request.user,
                action='change_request_review_email_failed',
                target_type='ChangeRequest',
                target_id=change_request.id,
                metadata={'recipient': change_request.user.email, 'error': str(exc)},
            )
        return Response(self.get_serializer(change_request).data)
