"""Durée des quiz chronométrés (examens et corrections) et collecte admin (examens)."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from .models import ExamQuizAttempt, MonthlyExam

SESSION_PREFIX_EXAM = "exam"
SESSION_PREFIX_CORRECTION = "correction"


def _session_key(prefix: str, pk: int) -> str:
    return f"{prefix}_quiz_started_{pk}"


def get_quiz_started_at(request, prefix: str, pk: int) -> datetime | None:
    raw = request.session.get(_session_key(prefix, pk))
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def ensure_quiz_started(request, prefix: str, pk: int) -> datetime:
    started = get_quiz_started_at(request, prefix, pk)
    if started is None:
        started = timezone.now()
        request.session[_session_key(prefix, pk)] = started.isoformat()
        request.session.modified = True
    return started


def clear_quiz_started(request, prefix: str, pk: int) -> None:
    key = _session_key(prefix, pk)
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def quiz_time_remaining_seconds(
    request, prefix: str, pk: int, duration_minutes: int
) -> int:
    started = get_quiz_started_at(request, prefix, pk)
    if started is None:
        return duration_minutes * 60
    deadline = started + timedelta(minutes=duration_minutes)
    remaining = (deadline - timezone.now()).total_seconds()
    return max(0, int(remaining))


def is_quiz_time_expired(
    request, prefix: str, pk: int, duration_minutes: int
) -> bool:
    return quiz_time_remaining_seconds(request, prefix, pk, duration_minutes) <= 0


def get_exam_started_at(request, exam: MonthlyExam) -> datetime | None:
    return get_quiz_started_at(request, SESSION_PREFIX_EXAM, exam.pk)


def ensure_exam_started(request, exam: MonthlyExam) -> datetime:
    return ensure_quiz_started(request, SESSION_PREFIX_EXAM, exam.pk)


def clear_exam_started(request, exam: MonthlyExam) -> None:
    clear_quiz_started(request, SESSION_PREFIX_EXAM, exam.pk)


def exam_time_remaining_seconds(request, exam: MonthlyExam) -> int:
    return quiz_time_remaining_seconds(
        request, SESSION_PREFIX_EXAM, exam.pk, exam.duration_minutes
    )


def is_exam_time_expired(request, exam: MonthlyExam) -> bool:
    return is_quiz_time_expired(
        request, SESSION_PREFIX_EXAM, exam.pk, exam.duration_minutes
    )


def ensure_correction_quiz_started(request, correction) -> datetime:
    return ensure_quiz_started(request, SESSION_PREFIX_CORRECTION, correction.pk)


def correction_quiz_time_remaining_seconds(request, correction) -> int:
    return quiz_time_remaining_seconds(
        request,
        SESSION_PREFIX_CORRECTION,
        correction.pk,
        correction.duration_minutes,
    )


def is_correction_quiz_time_expired(request, correction) -> bool:
    return is_quiz_time_expired(
        request,
        SESSION_PREFIX_CORRECTION,
        correction.pk,
        correction.duration_minutes,
    )


def clear_correction_quiz_started(request, correction) -> None:
    clear_quiz_started(request, SESSION_PREFIX_CORRECTION, correction.pk)


def user_has_admin_result(exam: MonthlyExam, user) -> bool:
    return ExamQuizAttempt.objects.filter(
        exam=exam, user=user, sent_to_admin=True
    ).exists()


def should_send_result_to_admin(exam: MonthlyExam, user) -> bool:
    """Première composition uniquement, dans le délai de collecte."""
    if user_has_admin_result(exam, user):
        return False
    return exam.is_within_results_collection_period()


def record_exam_attempt(
    request,
    exam: MonthlyExam,
    user,
    score_points: int,
    score_percent: float,
) -> ExamQuizAttempt:
    sent = should_send_result_to_admin(exam, user)
    attempt = ExamQuizAttempt.objects.create(
        user=user,
        exam=exam,
        score_points=score_points,
        score_percent=score_percent,
        sent_to_admin=sent,
    )
    clear_exam_started(request, exam)
    return attempt
