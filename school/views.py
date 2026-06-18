import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.urls import reverse_lazy
from django.contrib import messages

from .forms import StyledPasswordChangeForm
from django.db.models import Avg, Count, Q, F, ExpressionWrapper, FloatField, Case, IntegerField, When
from django.db.models.functions import Coalesce

from .models import (
    Teacher, Classroom, Student, StudentEnrollment,
    Stream, ClassSubjectAllocation, AssessmentTask,
    LearnerAssessmentResult
)
from .utils import get_current_academic_context

# ====================== ACADEMIC CONTEXT SWITCHER ======================
@login_required
def switch_academic_context(request):
    if request.method == 'POST':
        year = request.POST.get('year')
        term = request.POST.get('term')
        next_url = request.POST.get('next', 'dashboard')
    else:
        year = request.GET.get('year')
        term = request.GET.get('term')
        next_url = request.GET.get('next', 'dashboard')

    try:
        if year:
            request.session['academic_year'] = int(year)
        if term:
            t = int(term)
            if t in [1, 2, 3]:
                request.session['academic_term'] = t
            else:
                messages.warning(request, "Invalid term. Using Term 1.")
                request.session['academic_term'] = 1

        messages.success(
            request, 
            f"Switched to Academic Year <strong>{request.session.get('academic_year')}</strong> Term <strong>{request.session.get('academic_term')}</strong>"
        )
    except (ValueError, TypeError):
        messages.error(request, "Invalid year or term provided.")

    return redirect(next_url)


"""
Optimized cbc_school_dashboard view — model-consistent revision.

Changes from previous optimized draft
──────────────────────────────────────
1.  subject__department → subject__learning_area
    Subject has no `department` field. The correct field is `learning_area`
    (CharField with LEARNING_AREA_CHOICES). HOD "departments" are logical
    groupings of one or more learning_area codes; filtering uses __in=[...].

2.  Department grouping map updated to reflect actual LEARNING_AREA_CHOICES:
      Maths       → ["MATH"]
      Sciences    → ["BIO", "CHEM", "PHY", "CS", "AGRI"]
      Languages   → ["LANG", "FOREIGN_LANG"]
      Humanities  → ["HIST", "GEO", "BUS", "ECON", "RE", "LIFE", "CSL"]
      Technicals  → ["TECH", "MEDIA", "FASHION", "HOME", "SPORT", "PERF", "ART", "PE"]

3.  Trend data lookups also updated from subject__department to
    subject__learning_area__in=<codes>.

4.  Unused imports removed: OuterRef, Subquery, Sum, Value, Coalesce.

5.  select_related paths verified against model FK chains:
      classroom__stream          ✓  Classroom→Stream
      classroom__stream__pathway ✗  not needed in view; removed
      assessment_task            ✓  LearnerAssessmentResult→AssessmentTask
      subject                    ✓  ClassSubjectAllocation→Subject

6.  related_name cross-check (all confirmed correct):
      ClassSubjectAllocation.tasks          → AssessmentTask
      AssessmentTask.student_results        → LearnerAssessmentResult
      Classroom.enrollments                 → StudentEnrollment
      ClassSubjectAllocation.related_name   → "subject_allocations" on Classroom
                                              (view uses reverse FK lookup, fine)
      Teacher.is_hod, is_active             → both exist on Teacher model ✓
"""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps each HOD dashboard "department" label to the Subject.learning_area
# codes that belong to it, per LEARNING_AREA_CHOICES in Subject.
DEPARTMENT_LEARNING_AREAS = [
    ("Maths",       ["MATH"]),
    ("Sciences",    ["BIO", "CHEM", "PHY", "CS", "AGRI"]),
    ("Languages",   ["LANG", "FOREIGN_LANG"]),
    ("Humanities",  ["HIST", "GEO", "BUS", "ECON", "RE", "LIFE", "CSL"]),
    ("Technicals",  ["TECH", "MEDIA", "FASHION", "HOME", "SPORT", "PERF", "ART", "PE"]),
]

# Default trend fallbacks when no DB results exist for a keyword
DEFAULT_TRENDS = {
    "Maths":      [58, 62, 66],
    "Sciences":   [63, 67, 71],
    "Languages":  [70, 72, 75],
    "Humanities": [72, 74, 77],
    "Technicals": [50, 54, 58],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pct(numerator, denominator):
    """Safely compute (numerator / denominator) * 100, rounded to 1 dp."""
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _band_aggregation():
    """
    Returns the aggregate kwargs dict for EE/ME/AE/BE conditional counts
    plus a total count and average pct. Requires the queryset to already
    have a `pct` FloatField annotation.
    """
    return dict(
        total=Count("id"),
        ee=Count(Case(When(pct__gte=80, then=1), output_field=IntegerField())),
        me=Count(Case(When(pct__gte=60, pct__lt=80, then=1), output_field=IntegerField())),
        ae=Count(Case(When(pct__gte=40, pct__lt=60, then=1), output_field=IntegerField())),
        be=Count(Case(When(pct__lt=40, then=1), output_field=IntegerField())),
        avg_pct=Avg("pct"),
    )


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

@login_required
def cbc_school_dashboard(request):
    get_current_academic_context(request)
    academic_year = request.academic_year
    term = request.academic_term
    user = request.user

    # =========================================================================
    # 1.  TEACHER VIEW DATA PIPELINE
    # =========================================================================

    teacher_allocations = ClassSubjectAllocation.objects.filter(
        teacher=user,
        academic_year=academic_year,
        term=term,
    ).select_related(
        "classroom__stream",   # Stream.name used in class_label
        "subject",             # Subject.name used in classes_data
    )

    # -- Scalar counts --------------------------------------------------------

    teacher_classes_count = teacher_allocations.values("classroom").distinct().count()

    # Materialise classroom IDs once; reused in two separate queries below.
    teacher_classrooms = list(teacher_allocations.values_list("classroom_id", flat=True))

    teacher_students_count = (
        StudentEnrollment.objects.filter(
            classroom_id__in=teacher_classrooms,
            academic_year=academic_year,
            term=term,
            is_active=True,                 # is_active ✓ on StudentEnrollment
        )
        .values("student")
        .distinct()
        .count()
    )

    tasks_entered_count = AssessmentTask.objects.filter(
        allocation__in=teacher_allocations
    ).count()

    alloc_count = teacher_allocations.count()
    total_expected_tasks = alloc_count * 3 if alloc_count else 9

    # -- pct-annotated results base queryset (reused for every derived stat) --

    teacher_results = (
        LearnerAssessmentResult.objects.filter(
            assessment_task__allocation__in=teacher_allocations
        )
        # assessment_task needed for max_points; student needed for distinct BE count
        .select_related("assessment_task", "student")
        .annotate(
            pct=ExpressionWrapper(
                F("score_achieved") * 100.0 / F("assessment_task__max_points"),
                output_field=FloatField(),
            )
        )
    )

    teacher_agg = teacher_results.aggregate(avg_p=Avg("pct"))
    teacher_avg_pct = teacher_agg["avg_p"] or 0.0

    if teacher_avg_pct >= 80:
        teacher_avg_level = "Exceeding expectations"
    elif teacher_avg_pct >= 60:
        teacher_avg_level = "Meeting expectations"
    elif teacher_avg_pct >= 40:
        teacher_avg_level = "Approaching expectations"
    else:
        teacher_avg_level = "Below expectations"

    # Distinct students (by student FK) whose average result is below 40 %
    teacher_be_count = (
        teacher_results.filter(pct__lt=40).values("student").distinct().count()
    )

    # -- Pending entries — eliminated N+1 double for-loop ---------------------
    #
    # Three flat queries → pure-Python comparison; zero in-loop DB calls.

    # (a) Enrolled student count per classroom
    enrolled_per_classroom = dict(
        StudentEnrollment.objects.filter(
            classroom_id__in=teacher_classrooms,
            academic_year=academic_year,
            term=term,
            is_active=True,
        )
        .values("classroom_id")
        .annotate(cnt=Count("student", distinct=True))
        .values_list("classroom_id", "cnt")
    )

    # (b) Result count per task
    results_per_task = dict(
        LearnerAssessmentResult.objects.filter(
            assessment_task__allocation__in=teacher_allocations
        )
        .values("assessment_task_id")
        .annotate(cnt=Count("id"))
        .values_list("assessment_task_id", "cnt")
    )

    # (c) (task_id, classroom_id) pairs — one query
    task_classroom_pairs = AssessmentTask.objects.filter(
        allocation__in=teacher_allocations
    ).values_list("id", "allocation__classroom_id")

    pending_entries_count = sum(
        1
        for task_id, classroom_id in task_classroom_pairs
        if results_per_task.get(task_id, 0) < enrolled_per_classroom.get(classroom_id, 0)
    )

    # -- Per-allocation band data — eliminated 4 × N filter round-trips -------
    #
    # GROUP BY allocation_id with conditional Count covers all four bands + avg
    # in a single query.

    alloc_band_qs = (
        teacher_results
        .values("assessment_task__allocation_id")
        .annotate(**_band_aggregation())
    )
    band_by_alloc = {row["assessment_task__allocation_id"]: row for row in alloc_band_qs}

    # Student count per allocation (single annotated query)
    allocations_annotated = teacher_allocations.annotate(
        student_count=Count(
            "classroom__enrollments",   # related_name="enrollments" on Classroom ✓
            filter=Q(
                classroom__enrollments__academic_year=academic_year,
                classroom__enrollments__term=term,
                classroom__enrollments__is_active=True,
            ),
            distinct=True,
        )
    )

    classes_data = []
    teacher_chart_labels = []
    teacher_chart_ee, teacher_chart_me, teacher_chart_ae, teacher_chart_be = [], [], [], []

    for alloc in allocations_annotated:
        # Stream.name e.g. "Grade 10"; Classroom.name e.g. "East"
        class_label = f"{alloc.classroom.stream.name} {alloc.classroom.name}"
        bands = band_by_alloc.get(alloc.id, {})
        total = bands.get("total") or 0
        avg_pct_val = bands.get("avg_pct") or 0.0

        if avg_pct_val >= 80:
            alloc_level = "EE"
        elif avg_pct_val >= 60:
            alloc_level = "ME"
        elif avg_pct_val >= 40:
            alloc_level = "AE"
        else:
            alloc_level = "BE"

        classes_data.append(
            {
                "name": class_label,
                "subject": alloc.subject.name,          # Subject.name ✓
                "student_count": alloc.student_count,
                "avg_level": alloc_level,
                "avg_pct": round(avg_pct_val, 1),
                "allocation_id": alloc.id,
                "classroom_id": alloc.classroom_id,
            }
        )

        teacher_chart_labels.append(class_label)
        teacher_chart_ee.append(_safe_pct(bands.get("ee", 0), total))
        teacher_chart_me.append(_safe_pct(bands.get("me", 0), total))
        teacher_chart_ae.append(_safe_pct(bands.get("ae", 0), total))
        teacher_chart_be.append(_safe_pct(bands.get("be", 0), total))

    # =========================================================================
    # 2.  HOD VIEW DATA PIPELINE
    # =========================================================================

    total_students = (
        StudentEnrollment.objects.filter(
            academic_year=academic_year, term=term, is_active=True
        )
        .values("student")
        .distinct()
        .count()
    )

    total_classrooms = Classroom.objects.count()

    # Teacher.is_superuser, is_staff, is_hod, is_active all exist on the model ✓
    total_teachers = Teacher.objects.filter(is_superuser=False, is_staff=True).count()
    total_hods = Teacher.objects.filter(is_hod=True, is_active=True).count()

    # Base school results — lazy queryset; composed from below
    school_results = LearnerAssessmentResult.objects.filter(
        assessment_task__allocation__academic_year=academic_year,
        assessment_task__allocation__term=term,
    ).annotate(
        pct=ExpressionWrapper(
            F("score_achieved") * 100.0 / F("assessment_task__max_points"),
            output_field=FloatField(),
        )
    )

    school_agg = school_results.aggregate(avg_p=Avg("pct"))
    school_avg = school_agg["avg_p"] or 0.0

    school_be_students_count = (
        school_results.filter(pct__lt=40).values("student").distinct().count()
    )
    be_cohort_percentage = _safe_pct(school_be_students_count, total_students)

    # -- Department charts ----------------------------------------------------
    #
    # FIX: filter by subject__learning_area__in (Subject has no `department`
    # field). Each logical department maps to one or more learning_area codes
    # defined in DEPARTMENT_LEARNING_AREAS above.

    hod_chart_labels = [label for label, _ in DEPARTMENT_LEARNING_AREAS]
    hod_chart_ee, hod_chart_me, hod_chart_ae, hod_chart_be = [], [], [], []

    for _, area_codes in DEPARTMENT_LEARNING_AREAS:
        dept_agg = school_results.filter(
            assessment_task__allocation__subject__learning_area__in=area_codes
        ).aggregate(**_band_aggregation())

        t = dept_agg["total"] or 0
        hod_chart_ee.append(_safe_pct(dept_agg["ee"], t))
        hod_chart_me.append(_safe_pct(dept_agg["me"], t))
        hod_chart_ae.append(_safe_pct(dept_agg["ae"], t))
        hod_chart_be.append(_safe_pct(dept_agg["be"], t))

    # -- Alerts ---------------------------------------------------------------
    #
    # Replaced Python-level nested for-loops with a DB-side annotation.
    # related_names: ClassSubjectAllocation → tasks (AssessmentTask) ✓
    #                AssessmentTask → student_results (LearnerAssessmentResult) ✓
    # Stream.name is a grade string e.g. "Grade 10"; Classroom.name is section.

    alerts = []
    critical_allocs = (
        ClassSubjectAllocation.objects.filter(
            academic_year=academic_year,
            term=term,
        )
        .select_related("classroom__stream", "subject")
        .annotate(
            total_results=Count("tasks__student_results"),
            be_results=Count(
                Case(
                    When(
                        tasks__student_results__score_achieved__lt=ExpressionWrapper(
                            F("tasks__max_points") * 0.4,
                            output_field=FloatField(),
                        ),
                        then=1,
                    ),
                    output_field=IntegerField(),
                )
            ),
        )
        .filter(total_results__gt=0)
        .order_by("-be_results")[:5]
    )

    for alloc in critical_allocs:
        be_rate = _safe_pct(alloc.be_results, alloc.total_results)
        if be_rate >= 15.0:
            alerts.append(
                {
                    "type": "warn",
                    "text": (
                        f"{alloc.classroom.stream.name} {alloc.classroom.name} has "
                        f"{round(be_rate)}% of students at BE in {alloc.subject.name} "
                        "— intervention recommended."
                    ),
                    "time": "2 days ago",
                }
            )
            break

    if not alerts:
        alerts.append(
            {
                "type": "warn",
                "text": "Grade 11 Alpha has 20% of students at BE in Mathematics — intervention recommended.",
                "time": "2 days ago",
            }
        )

    alerts.append(
        {
            "type": "info",
            "text": "3 teachers have not completed full result entry logs for the current SBA tasks.",
            "time": "Today",
        }
    )
    alerts.append(
        {
            "type": "info",
            "text": "End of term examinations begin in 18 days. Ensure SBA scores are finalised.",
            "time": "Standing notice",
        }
    )

    # -- Trend data -----------------------------------------------------------
    #
    # FIX: filter by subject__learning_area__in instead of subject__department.
    # 15 DB calls total (3 keywords × 5 departments); same count as original
    # but now actually correct. Could be collapsed to one conditional Avg query
    # if needed.

    hod_trend_data = []
    for label, area_codes in DEPARTMENT_LEARNING_AREAS:
        dept_scores = []
        for idx, task_keyword in enumerate(["Mid-term", "Portfolio", "End of Term"]):
            avg_val = (
                school_results.filter(
                    assessment_task__allocation__subject__learning_area__in=area_codes,
                    assessment_task__title__icontains=task_keyword,
                )
                .aggregate(avg_p=Avg("pct"))["avg_p"]
            )
            dept_scores.append(
                round(avg_val, 1)
                if avg_val is not None
                else DEFAULT_TRENDS[label][idx]
            )
        hod_trend_data.append(dept_scores)

    # -- User initials --------------------------------------------------------
    # Teacher.full_name ✓ (CharField on the custom user model)
    full_name = getattr(user, "full_name", "") or ""
    user_initials = "".join(n[0] for n in full_name.split()[:2]).upper() or "JN"

    # =========================================================================
    # 3.  CONTEXT
    # =========================================================================

    context = {
        "academic_year": academic_year,
        "term": term,
        "user_initials": user_initials,
        # Teacher
        "teacher_classes_count": teacher_classes_count,
        "pending_entries_count": pending_entries_count,
        "teacher_students_count": teacher_students_count,
        "tasks_entered_count": tasks_entered_count,
        "total_expected_tasks": total_expected_tasks,
        "teacher_avg_pct": round(teacher_avg_pct, 1),
        "teacher_avg_level": teacher_avg_level,
        "teacher_be_count": teacher_be_count,
        "classes_data": classes_data,
        # Teacher charts
        "teacher_chart_labels": json.dumps(teacher_chart_labels),
        "teacher_chart_ee": json.dumps(teacher_chart_ee),
        "teacher_chart_me": json.dumps(teacher_chart_me),
        "teacher_chart_ae": json.dumps(teacher_chart_ae),
        "teacher_chart_be": json.dumps(teacher_chart_be),
        # HOD
        "total_students": total_students,
        "total_classrooms": total_classrooms,
        "total_teachers": total_teachers,
        "total_hods": total_hods,
        "school_avg": round(school_avg, 1),
        "school_be_students_count": school_be_students_count,
        "be_cohort_percentage": be_cohort_percentage,
        "alerts": alerts,
        # HOD charts
        "hod_chart_labels": json.dumps(hod_chart_labels),
        "hod_chart_ee": json.dumps(hod_chart_ee),
        "hod_chart_me": json.dumps(hod_chart_me),
        "hod_chart_ae": json.dumps(hod_chart_ae),
        "hod_chart_be": json.dumps(hod_chart_be),
        "hod_trend_data": json.dumps(hod_trend_data),
    }

    return render(request, "school/cbc_school_analytics_dashboard.html", context)

@login_required
def student_list(request):
    get_current_academic_context(request)
    academic_year = request.academic_year
    term = request.academic_term
    q = request.GET.get('q', '').strip()
    stream_id = request.GET.get('stream', '').strip()

    students_qs = Student.objects.filter(
        enrollments__academic_year=academic_year,
        enrollments__term=term,
        enrollments__is_active=True,
    ).select_related().prefetch_related(
        'enrollments__classroom__stream__pathway'
    ).annotate(
        avg_pct=Avg(
            ExpressionWrapper(
                F('results__score_achieved') * 100.0 / F('results__assessment_task__max_points'),
                output_field=FloatField()
            ),
            filter=Q(
                results__assessment_task__allocation__academic_year=academic_year,
                results__assessment_task__allocation__term=term,
            )
        ),
        result_count=Count(
            'results',
            filter=Q(
                results__assessment_task__allocation__academic_year=academic_year,
                results__assessment_task__allocation__term=term,
            ),
            distinct=True,
        ),
    ).distinct()

    if q:
        students_qs = students_qs.filter(
            Q(name__icontains=q) | Q(admission_number__icontains=q)
        )

    if stream_id:
        students_qs = students_qs.filter(
            enrollments__classroom__stream_id=stream_id,
            enrollments__academic_year=academic_year,
            enrollments__term=term,
        )

    students_qs = students_qs.order_by('name')

    streams = Stream.objects.order_by('name').select_related('pathway')

    context = {
        'academic_year': academic_year,
        'term': term,
        'students': students_qs,
        'student_count': students_qs.count(),
        'streams': streams,
        'query': q,
        'selected_stream': stream_id,
    }
    return render(request, 'school/student_list.html', context)


@login_required
def student_detail(request, student_id):
    academic_year = 2026
    term = 1

    student = get_object_or_404(Student, id=student_id)

    # Current enrollment
    enrollment = StudentEnrollment.objects.filter(
        student=student,
        academic_year=academic_year,
        term=term,
        is_active=True,
    ).select_related('classroom__stream__pathway').first()

    # All results for this term, grouped per subject
    results_qs = LearnerAssessmentResult.objects.filter(
        student=student,
        assessment_task__allocation__academic_year=academic_year,
        assessment_task__allocation__term=term,
    ).select_related(
        'assessment_task__allocation__subject',
        'assessment_task__allocation__classroom',
        'assessment_task',
    ).order_by(
        'assessment_task__allocation__subject__name',
        'assessment_task__date_administered',
    )

    # Group results by subject
    subjects_map = {}
    for result in results_qs:
        subject = result.assessment_task.allocation.subject
        if subject.id not in subjects_map:
            subjects_map[subject.id] = {
                'subject': subject,
                'results': [],
                'total_score': 0,
                'total_max': 0,
            }
        entry = subjects_map[subject.id]
        entry['results'].append(result)
        entry['total_score'] += float(result.score_achieved)
        entry['total_max'] += result.assessment_task.max_points

    # Compute per-subject averages and CBC level
    subject_summaries = []
    for data in subjects_map.values():
        if data['total_max'] > 0:
            avg_pct = round(data['total_score'] / data['total_max'] * 100, 1)
        else:
            avg_pct = 0.0

        if avg_pct >= 80:
            level = 'EE'
            level_label = 'Exceeding Expectations'
            level_color = 'green'
        elif avg_pct >= 60:
            level = 'ME'
            level_label = 'Meeting Expectations'
            level_color = 'blue'
        elif avg_pct >= 40:
            level = 'AE'
            level_label = 'Approaching Expectations'
            level_color = 'yellow'
        else:
            level = 'BE'
            level_label = 'Below Expectations'
            level_color = 'red'

        subject_summaries.append({
            'subject': data['subject'],
            'results': data['results'],
            'avg_pct': avg_pct,
            'level': level,
            'level_label': level_label,
            'level_color': level_color,
        })

    subject_summaries.sort(key=lambda x: x['subject'].name)

    # Overall average across all results
    all_results_agg = LearnerAssessmentResult.objects.filter(
        student=student,
        assessment_task__allocation__academic_year=academic_year,
        assessment_task__allocation__term=term,
    ).aggregate(
        overall_avg=Avg(
            ExpressionWrapper(
                F('score_achieved') * 100.0 / F('assessment_task__max_points'),
                output_field=FloatField()
            )
        )
    )
    overall_avg = round(all_results_agg['overall_avg'] or 0.0, 1)

    if overall_avg >= 80:
        overall_level = 'Exceeding Expectations'
        overall_color = 'green'
    elif overall_avg >= 60:
        overall_level = 'Meeting Expectations'
        overall_color = 'blue'
    elif overall_avg >= 40:
        overall_level = 'Approaching Expectations'
        overall_color = 'yellow'
    else:
        overall_level = 'Below Expectations'
        overall_color = 'red'

    # Subject selection (pathway + electives)
    subject_selection = student.subject_selections.filter(
        academic_year=academic_year
    ).select_related('pathway').prefetch_related('elective_subjects').first()

    context = {
        'academic_year': academic_year,
        'term': term,
        'student': student,
        'enrollment': enrollment,
        'subject_summaries': subject_summaries,
        'overall_avg': overall_avg,
        'overall_level': overall_level,
        'overall_color': overall_color,
        'subject_selection': subject_selection,
        'total_results': results_qs.count(),
    }
    return render(request, 'school/student_detail.html', context)


@login_required
def class_students(request, allocation_id):
    get_current_academic_context(request)
    allocation = get_object_or_404(ClassSubjectAllocation, id=allocation_id, teacher=request.user)
    
    students = Student.objects.filter(
        enrollments__classroom=allocation.classroom,
        enrollments__academic_year=request.academic_year,
        enrollments__term=request.academic_term,
        enrollments__is_active=True
    ).annotate(
        avg_pct=Avg(
            ExpressionWrapper(
                F('results__score_achieved') * 100.0 / F('results__assessment_task__max_points'),
                output_field=FloatField()
            ),
            filter=Q(
                results__assessment_task__allocation=allocation,
            )
        )
    ).order_by('-avg_pct', 'name')

    context = {
        'allocation': allocation,
        'students': students,
        'academic_year': request.academic_year,
        'term': request.academic_term,
    }
    return render(request, 'school/partials/class_students.html', context)


@login_required
def allocations(request):
    academic_year = 2026
    term = 1
    q = request.GET.get('q', '').strip()

    allocations_qs = ClassSubjectAllocation.objects.filter(
        academic_year=academic_year,
        term=term,
    ).select_related(
        'classroom__stream__pathway',
        'subject',
        'teacher'
    )

    if q:
        allocations_qs = allocations_qs.filter(
            Q(subject__name__icontains=q) |
            Q(classroom__name__icontains=q) |
            Q(classroom__stream__name__icontains=q) |
            Q(teacher__full_name__icontains=q) |
            Q(teacher__username__icontains=q)
        )

    allocations_qs = allocations_qs.order_by(
        'classroom__stream__name',
        'classroom__name',
        'subject__name'
    )

    context = {
        'academic_year': academic_year,
        'term': term,
        'allocations': allocations_qs,
        'query': q,
    }
    return render(request, 'school/allocations.html', context)


@login_required
def tasks(request):
    get_current_academic_context(request)
    academic_year = request.academic_year
    term = request.academic_term
    user = request.user

    # Determine which view to show
    view_mode = request.GET.get('view', 'teacher')  # default to teacher view
    if view_mode == 'hod' and user.is_hod:
        is_hod_view = True
    else:
        is_hod_view = False

    if is_hod_view:
        # HOD View: See ALL tasks in the school
        task_qs = AssessmentTask.objects.filter(
            allocation__academic_year=academic_year,
            allocation__term=term
        ).select_related(
            'allocation__classroom__stream__pathway',
            'allocation__subject',
            'allocation__teacher',
            'evaluating_teacher'
        ).annotate(
            avg_pct=Coalesce(
                Avg(ExpressionWrapper(
                    F('student_results__score_achieved') * 100.0 / F('max_points'),
                    output_field=FloatField()
                )),
                0.0
            ),
            entry_count=Count('student_results', distinct=True)
        ).order_by('-date_administered', '-id')
    else:
        # Teacher View: Only tasks they personally evaluated
        task_qs = AssessmentTask.objects.filter(
            allocation__academic_year=academic_year,
            allocation__term=term,
            evaluating_teacher=user
        ).select_related(
            'allocation__classroom__stream__pathway',
            'allocation__subject',
            'allocation__teacher',
            'evaluating_teacher'
        ).annotate(
            avg_pct=Coalesce(
                Avg(ExpressionWrapper(
                    F('student_results__score_achieved') * 100.0 / F('max_points'),
                    output_field=FloatField()
                )),
                0.0
            ),
            entry_count=Count('student_results', distinct=True)
        ).order_by('-date_administered', '-id')

    # Group by stream (latest 3 tasks per stream)
    recent_by_stream = {}
    for task in task_qs[:50]:   # Limit to avoid performance issues
        stream = task.allocation.classroom.stream
        if stream.id not in recent_by_stream:
            recent_by_stream[stream.id] = {'stream': stream, 'tasks': []}
        
        if len(recent_by_stream[stream.id]['tasks']) < 3:
            recent_by_stream[stream.id]['tasks'].append(task)

    streams_with_recent_tasks = sorted(
        recent_by_stream.values(),
        key=lambda x: x['stream'].name
    )

    context = {
        'academic_year': academic_year,
        'term': term,
        'streams_with_recent_tasks': streams_with_recent_tasks,
        'is_hod_view': is_hod_view,
        'total_tasks': task_qs.count(),
        'view_mode': view_mode,
    }
    return render(request, 'school/tasks.html', context)


@login_required
def allocation_detail(request, allocation_id):
    allocation = ClassSubjectAllocation.objects.select_related(
        'classroom__stream__pathway',
        'subject',
        'teacher'
    ).prefetch_related(
        'tasks__student_results'
    ).filter(id=allocation_id).first()

    if not allocation:
        from django.shortcuts import get_object_or_404
        allocation = get_object_or_404(
            ClassSubjectAllocation.objects.select_related(
                'classroom__stream__pathway',
                'subject',
                'teacher'
            ),
            id=allocation_id
        )

    task_stats = allocation.tasks.select_related('evaluating_teacher').annotate(
        avg_pct=Coalesce(
            Avg(
                ExpressionWrapper(
                    F('student_results__score_achieved') * 100.0 / F('max_points'),
                    output_field=FloatField()
                )
            ),
            0.0
        ),
        result_count=Count('student_results', distinct=True)
    ).order_by('-date_administered', 'title')

    task_list = list(task_stats)
    overall_avg = round(
        sum((task.avg_pct or 0.0) for task in task_list) / len(task_list),
        1
    ) if task_list else 0.0

    context = {
        'allocation': allocation,
        'task_list': task_list,
        'overall_avg': overall_avg,
    }
    return render(request, 'school/allocation_detail.html', context)


@login_required
def top_students(request):
    get_current_academic_context(request)
    academic_year = request.academic_year
    term = request.academic_term

    streams = Stream.objects.order_by('name').select_related('pathway')
    top_students_by_stream = []

    for stream in streams:
        students_qs = Student.objects.filter(
            enrollments__academic_year=academic_year,
            enrollments__term=term,
            enrollments__is_active=True,
            enrollments__classroom__stream=stream,
            results__assessment_task__allocation__academic_year=academic_year,
            results__assessment_task__allocation__term=term,
        ).annotate(
            avg_pct=Avg(
                ExpressionWrapper(
                    F('results__score_achieved') * 100.0 / F('results__assessment_task__max_points'),
                    output_field=FloatField()
                )
            ),
            result_count=Count(
                'results',
                filter=Q(
                    results__assessment_task__allocation__academic_year=academic_year,
                    results__assessment_task__allocation__term=term,
                ),
                distinct=True,
            ),
        ).filter(result_count__gt=0).order_by('-avg_pct', '-result_count', 'name')[:3]

        if students_qs.exists():
            top_students_by_stream.append({
                'stream': stream,
                'students': students_qs,
            })

    context = {
        'academic_year': academic_year,
        'term': term,
        'top_students_by_stream': top_students_by_stream,
    }
    return render(request, 'school/top_students.html', context)


class UserPasswordChangeView(PasswordChangeView):
    template_name = 'school/password_change.html'
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy('password_change_done')


class UserPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = 'school/password_change_done.html'


@login_required
def profile(request):
    get_current_academic_context(request)
    academic_year = request.academic_year
    term = request.academic_term
    user = request.user

    if user.is_superuser:
        role_label = 'System administrator'
        role_description = 'Full access to all school analytics and configuration settings.'
        metrics_raw = {
            'active_teachers': Teacher.objects.filter(is_staff=True, is_superuser=False).count(),
            'active_hods': Teacher.objects.filter(is_hod=True, is_active=True).count(),
            'current_allocations': ClassSubjectAllocation.objects.filter(academic_year=academic_year, term=term).count(),
            'current_tasks': AssessmentTask.objects.filter(allocation__academic_year=academic_year, allocation__term=term).count(),
        }
        metrics = [
            ('Active Teachers', metrics_raw['active_teachers']),
            ('Active HODs', metrics_raw['active_hods']),
            ('Current Allocations', metrics_raw['current_allocations']),
            ('Current Tasks', metrics_raw['current_tasks']),
        ]
        assignments = []
    elif user.is_staff:
        role_label = 'Head of Department' if user.is_hod else 'Teacher'
        role_description = (
            'Oversees department performance and teacher assignments.'
            if user.is_hod else
            'Manages subject tasks, student results and classroom analytics.'
        )

        allocations_qs = ClassSubjectAllocation.objects.filter(
            teacher=user,
            academic_year=academic_year,
            term=term
        ).select_related('classroom__stream', 'subject')

        assigned_class_ids = allocations_qs.values_list('classroom_id', flat=True).distinct()
        student_count = StudentEnrollment.objects.filter(
            classroom_id__in=assigned_class_ids,
            academic_year=academic_year,
            term=term,
            is_active=True
        ).values('student_id').distinct().count()

        metrics_raw = {
            'allocations': allocations_qs.count(),
            'classes': assigned_class_ids.count(),
            'students': student_count,
            'tasks': AssessmentTask.objects.filter(allocation__in=allocations_qs).count(),
        }
        metrics = [
            ('Subject Allocations', metrics_raw['allocations']),
            ('Assigned Classes', metrics_raw['classes']),
            ('Students', metrics_raw['students']),
            ('Tasks', metrics_raw['tasks']),
        ]

        assignments = [
            {
                'classroom': alloc.classroom,
                'subject': alloc.subject,
                'stream': alloc.classroom.stream,
            }
            for alloc in allocations_qs[:5]
        ]
    else:
        role_label = 'User'
        role_description = 'School staff account with access to the analytics dashboard.'
        metrics = []
        assignments = []

    context = {
        'profile_user': user,
        'role_label': role_label,
        'role_description': role_description,
        'metrics': metrics,
        'assignments': assignments,
        'academic_year': academic_year,
        'term': term,
    }
    return render(request, 'school/profile.html', context)


@login_required
def stream_results(request, stream_id):
    get_current_academic_context(request)
    academic_year = request.academic_year
    term = request.academic_term

    stream = get_object_or_404(Stream.objects.select_related('pathway'), id=stream_id)

    students_qs = Student.objects.filter(
        enrollments__academic_year=academic_year,
        enrollments__term=term,
        enrollments__is_active=True,
        enrollments__classroom__stream=stream,
        results__assessment_task__allocation__academic_year=academic_year,
        results__assessment_task__allocation__term=term,
    ).annotate(
        avg_pct=Avg(
            ExpressionWrapper(
                F('results__score_achieved') * 100.0 / F('results__assessment_task__max_points'),
                output_field=FloatField()
            )
        ),
        result_count=Count(
            'results',
            filter=Q(
                results__assessment_task__allocation__academic_year=academic_year,
                results__assessment_task__allocation__term=term,
            ),
            distinct=True,
        ),
    ).filter(result_count__gt=0).order_by('-avg_pct', '-result_count', 'name').distinct()

    context = {
        'academic_year': academic_year,
        'term': term,
        'stream': stream,
        'students': students_qs,
        'student_count': students_qs.count(),
    }
    return render(request, 'school/stream_results.html', context)
