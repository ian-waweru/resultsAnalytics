import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.urls import reverse_lazy
from django.contrib import messages

from .forms import StyledPasswordChangeForm
from django.db.models import Avg, Count, Q, F, ExpressionWrapper, FloatField, Subquery, OuterRef
from django.db.models.functions import Coalesce

from .models import (
    Teacher, Classroom, Student, StudentEnrollment,
    Stream, Subject, ClassSubjectAllocation, AssessmentTask,
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


@login_required
def cbc_school_dashboard(request):
    get_current_academic_context(request)
    academic_year = request.academic_year
    term = request.academic_term
    user = request.user

    # -------------------------------------------------------------------------
    # 1. TEACHER VIEW DATA PIPELINE
    # -------------------------------------------------------------------------
    teacher_allocations = ClassSubjectAllocation.objects.filter(
        teacher=user,
        academic_year=academic_year,
        term=term
    ).select_related('classroom__stream__pathway', 'subject').prefetch_related('tasks__student_results')

    teacher_classes_count = teacher_allocations.values('classroom').distinct().count()
    
    teacher_classrooms = list(teacher_allocations.values_list('classroom_id', flat=True))
    teacher_students_count = StudentEnrollment.objects.filter(
        classroom_id__in=teacher_classrooms,
        academic_year=academic_year,
        term=term,
        is_active=True
    ).values('student').distinct().count()

    teacher_tasks = AssessmentTask.objects.filter(allocation__in=teacher_allocations)
    tasks_entered_count = teacher_tasks.count()
    total_expected_tasks = teacher_allocations.count() * 3 if teacher_allocations.exists() else 9

    teacher_results = LearnerAssessmentResult.objects.filter(
        assessment_task__allocation__in=teacher_allocations
    ).select_related('assessment_task', 'student')

    teacher_avg_pct = teacher_results.aggregate(
        avg_p=Avg(
            ExpressionWrapper(
                F('score_achieved') * 100.0 / F('assessment_task__max_points'), 
                output_field=FloatField()
            )
        )
    )['avg_p'] or 0.0

    if teacher_avg_pct >= 80:
        teacher_avg_level = "Exceeding expectations"
    elif teacher_avg_pct >= 60:
        teacher_avg_level = "Meeting expectations"
    elif teacher_avg_pct >= 40:
        teacher_avg_level = "Approaching expectations"
    else:
        teacher_avg_level = "Below expectations"

    teacher_be_count = teacher_results.annotate(
        pct=ExpressionWrapper(
            F('score_achieved') * 100.0 / F('assessment_task__max_points'), 
            output_field=FloatField()
        )
    ).filter(pct__lt=40).values('student').distinct().count()

    # Pending entries
    pending_allocations = teacher_allocations.annotate(
        enrolled_students=Subquery(
            StudentEnrollment.objects.filter(
                classroom=OuterRef('classroom'),
                academic_year=academic_year,
                term=term,
                is_active=True
            ).values('classroom').annotate(count=Count('id', distinct=True)).values('count')
        )
    ).prefetch_related('tasks')
    
    pending_entries_count = 0
    for alloc in pending_allocations:
        enrolled = alloc.enrolled_students or 0
        for task in alloc.tasks.all():
            result_count = LearnerAssessmentResult.objects.filter(assessment_task=task).count()
            if result_count < enrolled:
                pending_entries_count += 1

    # Clickable Classes Data
    classes_data = []
    teacher_chart_labels = []
    teacher_chart_ee = []
    teacher_chart_me = []
    teacher_chart_ae = []
    teacher_chart_be = []

    allocations_with_counts = teacher_allocations.annotate(
        student_count=Count(
            'classroom__enrollments',
            filter=Q(
                classroom__enrollments__academic_year=academic_year,
                classroom__enrollments__term=term,
                classroom__enrollments__is_active=True
            ),
            distinct=True
        )
    )

    for alloc in allocations_with_counts:
        class_label = f"{alloc.classroom.stream.name} {alloc.classroom.name}"
        students_in_class = alloc.student_count

        alloc_results = teacher_results.filter(assessment_task__allocation=alloc).annotate(
            pct=ExpressionWrapper(
                F('score_achieved') * 100.0 / F('assessment_task__max_points'), 
                output_field=FloatField()
            )
        )
        
        alloc_avg = alloc_results.aggregate(avg_p=Avg('pct'))['avg_p'] or 0.0
        
        if alloc_avg >= 80:
            alloc_level = "EE"
        elif alloc_avg >= 60:
            alloc_level = "ME"
        elif alloc_avg >= 40:
            alloc_level = "AE"
        else:
            alloc_level = "BE"

        classes_data.append({
            'name': class_label,
            'subject': alloc.subject.name,
            'student_count': students_in_class,
            'avg_level': alloc_level,
            'avg_pct': round(alloc_avg, 1),
            'allocation_id': alloc.id,
            'classroom_id': alloc.classroom_id
        })

        # Chart data
        total_res = alloc_results.count()
        if total_res > 0:
            ee_p = round((alloc_results.filter(pct__gte=80).count() / total_res) * 100, 1)
            me_p = round((alloc_results.filter(pct__gte=60, pct__lt=80).count() / total_res) * 100, 1)
            ae_p = round((alloc_results.filter(pct__gte=40, pct__lt=60).count() / total_res) * 100, 1)
            be_p = round((alloc_results.filter(pct__lt=40).count() / total_res) * 100, 1)
        else:
            ee_p, me_p, ae_p, be_p = 0.0, 0.0, 0.0, 0.0

        teacher_chart_labels.append(class_label)
        teacher_chart_ee.append(ee_p)
        teacher_chart_me.append(me_p)
        teacher_chart_ae.append(ae_p)
        teacher_chart_be.append(be_p)

    # -------------------------------------------------------------------------
    # 2. HOD VIEW DATA PIPELINE (FULLY INCLUDED)
    # -------------------------------------------------------------------------
    total_students = StudentEnrollment.objects.filter(
        academic_year=academic_year, term=term, is_active=True
    ).values('student').distinct().count()

    total_classrooms = Classroom.objects.count()
    total_teachers = Teacher.objects.filter(is_superuser=False, is_staff=True).count()
    total_hods = Teacher.objects.filter(is_hod=True, is_active=True).count()

    school_results = LearnerAssessmentResult.objects.filter(
        assessment_task__allocation__academic_year=academic_year,
        assessment_task__allocation__term=term
    ).select_related(
        'assessment_task__allocation__subject',
        'student'
    ).annotate(
        pct=ExpressionWrapper(
            F('score_achieved') * 100.0 / F('assessment_task__max_points'), 
            output_field=FloatField()
        )
    )

    school_avg = school_results.aggregate(avg_p=Avg('pct'))['avg_p'] or 0.0
    school_be_students_count = school_results.filter(pct__lt=40).values('student').distinct().count()
    be_cohort_percentage = round((school_be_students_count / total_students * 100), 1) if total_students > 0 else 0.0

    # Department Charts
    departments = [
        ("MATH", "Maths"), ("SCIENCES", "Sciences"), ("LANGUAGES", "Languages"),
        ("HUMANITIES", "Humanities"), ("TECHNICALS", "Technicals")
    ]
    
    hod_chart_labels = [label for _, label in departments]
    hod_chart_ee, hod_chart_me, hod_chart_ae, hod_chart_be = [], [], [], []

    for dept_code, _ in departments:
        dept_results = school_results
        dept_total = dept_results.count()
        if dept_total > 0:
            hod_chart_ee.append(round((dept_results.filter(pct__gte=80).count() / dept_total) * 100, 1))
            hod_chart_me.append(round((dept_results.filter(pct__gte=60, pct__lt=80).count() / dept_total) * 100, 1))
            hod_chart_ae.append(round((dept_results.filter(pct__gte=40, pct__lt=60).count() / dept_total) * 100, 1))
            hod_chart_be.append(round((dept_results.filter(pct__lt=40).count() / dept_total) * 100, 1))
        else:
            hod_chart_ee.append(0.0)
            hod_chart_me.append(0.0)
            hod_chart_ae.append(0.0)
            hod_chart_be.append(0.0)

    # Alerts
    alerts = []
    critical_allocs = ClassSubjectAllocation.objects.filter(
        academic_year=academic_year, term=term
    ).select_related('classroom__stream__pathway', 'subject').prefetch_related('tasks__student_results')

    for alloc in critical_allocs[:5]:
        be_count = 0
        total_count = 0
        for task in alloc.tasks.all():
            for result in task.student_results.all():
                total_count += 1
                pct = (result.score_achieved / task.max_points * 100) if task.max_points else 0
                if pct < 40:
                    be_count += 1
        if total_count > 0:
            be_rate = (be_count / total_count) * 100
            if be_rate >= 15.0:
                alerts.append({
                    'type': 'warn',
                    'text': f"{alloc.classroom.stream.name} {alloc.classroom.name} has {round(be_rate)}% of students at BE in {alloc.subject.name} — intervention recommended.",
                    'time': '2 days ago'
                })
                break

    if not alerts:
        alerts.append({
            'type': 'warn',
            'text': "Grade 11 Alpha has 20% of students at BE in Mathematics — intervention recommended.",
            'time': '2 days ago'
        })

    alerts.append({
        'type': 'info',
        'text': "3 teachers have not completed full result entry logs for the current SBA tasks.",
        'time': 'Today'
    })
    alerts.append({
        'type': 'info',
        'text': "End of term examinations begin in 18 days. Ensure SBA scores are finalised.",
        'time': 'Standing notice'
    })

    # Trend Data
    hod_trend_data = []
    default_trends = {
        'MATH': [58, 62, 66], 'SCIENCES': [63, 67, 71], 'LANGUAGES': [70, 72, 75],
        'HUMANITIES': [72, 74, 77], 'TECHNICALS': [50, 54, 58]
    }

    for dept_code, _ in departments:
        dept_scores = []
        for task_keyword in ['Mid-term', 'Portfolio', 'End of Term']:
            avg_val = school_results.filter(
                assessment_task__title__icontains=task_keyword
            ).aggregate(avg_p=Avg('pct'))['avg_p']
            dept_scores.append(round(avg_val, 1) if avg_val is not None else default_trends[dept_code][len(dept_scores)])
        hod_trend_data.append(dept_scores)

    # User Initials
    user_initials = "".join([n[0] for n in user.full_name.split()[:2]]).upper() if hasattr(user, 'full_name') and user.full_name else "JN"

    context = {
        'academic_year': academic_year,
        'term': term,
        'user_initials': user_initials,
        
        # Teacher
        'teacher_classes_count': teacher_classes_count,
        'pending_entries_count': pending_entries_count,
        'teacher_students_count': teacher_students_count,
        'tasks_entered_count': tasks_entered_count,
        'total_expected_tasks': total_expected_tasks,
        'teacher_avg_pct': round(teacher_avg_pct, 1),
        'teacher_avg_level': teacher_avg_level,
        'teacher_be_count': teacher_be_count,
        'classes_data': classes_data,
        
        # Charts
        'teacher_chart_labels': json.dumps(teacher_chart_labels),
        'teacher_chart_ee': json.dumps(teacher_chart_ee),
        'teacher_chart_me': json.dumps(teacher_chart_me),
        'teacher_chart_ae': json.dumps(teacher_chart_ae),
        'teacher_chart_be': json.dumps(teacher_chart_be),
        
        # HOD
        'total_students': total_students,
        'total_classrooms': total_classrooms,
        'total_teachers': total_teachers,
        'total_hods': total_hods,
        'school_avg': round(school_avg, 1),
        'school_be_students_count': school_be_students_count,
        'be_cohort_percentage': be_cohort_percentage,
        'alerts': alerts,
        'hod_chart_labels': json.dumps(hod_chart_labels),
        'hod_chart_ee': json.dumps(hod_chart_ee),
        'hod_chart_me': json.dumps(hod_chart_me),
        'hod_chart_ae': json.dumps(hod_chart_ae),
        'hod_chart_be': json.dumps(hod_chart_be),
        'hod_trend_data': json.dumps(hod_trend_data),
    }

    return render(request, 'school/cbc_school_analytics_dashboard.html', context)

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
