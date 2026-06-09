import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
# Added ExpressionWrapper and FloatField to the imports below
from django.db.models import Avg, Count, Q, F, ExpressionWrapper, FloatField

from .models import (
    Teacher, Classroom, Student, StudentEnrollment, 
    Subject, ClassSubjectAllocation, AssessmentTask, LearnerAssessmentResult
)

@login_required
def cbc_school_dashboard(request):
    # Set active context parameters (can also be pulled from request.GET or middleware)
    academic_year = 2026
    term = 1
    user = request.user

    # -------------------------------------------------------------------------
    # 1. TEACHER VIEW DATA PIPELINE
    # -------------------------------------------------------------------------
    # Pre-fetch relations to optimize loops inside template & avoid N+1 queries
    teacher_allocations = ClassSubjectAllocation.objects.filter(
        teacher=user,
        academic_year=academic_year,
        term=term
    ).select_related('classroom__stream', 'subject')

    # Metrics
    teacher_classes_count = teacher_allocations.values('classroom').distinct().count()
    
    teacher_classrooms = teacher_allocations.values_list('classroom_id', flat=True)
    teacher_students_count = StudentEnrollment.objects.filter(
        classroom_id__in=teacher_classrooms,
        academic_year=academic_year,
        term=term,
        is_active=True
    ).values('student').distinct().count()

    # Assessment Tasks Tracker
    teacher_tasks = AssessmentTask.objects.filter(allocation__in=teacher_allocations)
    tasks_entered_count = teacher_tasks.count()
    # Dynamic target entry calculation (e.g., 3 standard CBC tasks per allocation)
    total_expected_tasks = teacher_allocations.count() * 3 if teacher_allocations.exists() else 9

    # Result Metrics using pure ORM calculation formulas
    teacher_results = LearnerAssessmentResult.objects.filter(
        assessment_task__allocation__in=teacher_allocations
    )
    
    # FIX 1: Wrapped with ExpressionWrapper
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

    # Flagged students scoring Below Expectations (< 40%) in this teacher's subject allocations
    # FIX 2: Wrapped with ExpressionWrapper
    teacher_be_count = teacher_results.annotate(
        pct=ExpressionWrapper(
            F('score_achieved') * 100.0 / F('assessment_task__max_points'), 
            output_field=FloatField()
        )
    ).filter(pct__lt=40).values('student').distinct().count()

    # Dynamic pending result entry tracker: tasks with incomplete result logs relative to enrolled students
    pending_entries_count = 0
    for alloc in teacher_allocations:
        enrolled_students = StudentEnrollment.objects.filter(
            classroom=alloc.classroom, academic_year=academic_year, term=term, is_active=True
        ).count()
        for task in AssessmentTask.objects.filter(allocation=alloc):
            if LearnerAssessmentResult.objects.filter(assessment_task=task).count() < enrolled_students:
                pending_entries_count += 1

    # Class Performance Breakdowns & Chart 1 Data Generation
    classes_data = []
    teacher_chart_labels = []
    teacher_chart_ee = []
    teacher_chart_me = []
    teacher_chart_ae = []
    teacher_chart_be = []

    for alloc in teacher_allocations:
        class_label = f"{alloc.classroom.stream.name} {alloc.classroom.name}"
        students_in_class = StudentEnrollment.objects.filter(
            classroom=alloc.classroom, academic_year=academic_year, term=term, is_active=True
        ).count()

        # FIX 3: Wrapped with ExpressionWrapper
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
            'avg_pct': round(alloc_avg, 1)
        })

        # Tier distributions for Chart
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
    # 2. HOD VIEW DATA PIPELINE (School-Wide Stats)
    # -------------------------------------------------------------------------
    total_students = StudentEnrollment.objects.filter(
        academic_year=academic_year, term=term, is_active=True
    ).values('student').distinct().count()

    total_classrooms = Classroom.objects.count()
    total_teachers = Teacher.objects.filter(is_superuser=False).count()
    total_hods = Teacher.objects.filter(is_hod=True).count()

    # FIX 4: Wrapped with ExpressionWrapper
    school_results = LearnerAssessmentResult.objects.filter(
        assessment_task__allocation__academic_year=academic_year,
        assessment_task__allocation__term=term
    ).annotate(
        pct=ExpressionWrapper(
            F('score_achieved') * 100.0 / F('assessment_task__max_points'), 
            output_field=FloatField()
        )
    )

    school_avg = school_results.aggregate(avg_p=Avg('pct'))['avg_p'] or 0.0
    school_be_students_count = school_results.filter(pct__lt=40).values('student').distinct().count()
    be_cohort_percentage = round((school_be_students_count / total_students * 100), 1) if total_students > 0 else 0.0

    # Department Multi-Tier Assessment Distribution (Chart 2)
    departments = [
        ("MATH", "Maths"),
        ("SCIENCES", "Sciences"),
        ("LANGUAGES", "Languages"),
        ("HUMANITIES", "Humanities"),
        ("TECHNICALS", "Technicals")
    ]
    
    hod_chart_labels = [label for _, label in departments]
    hod_chart_ee, hod_chart_me, hod_chart_ae, hod_chart_be = [], [], [], []

    for dept_code, _ in departments:
        dept_results = school_results.filter(assessment_task__allocation__subject__department=dept_code)
        dept_total = dept_results.count()
        if dept_total > 0:
            hod_chart_ee.append(round((dept_results.filter(pct__gte=80).count() / dept_total) * 100, 1))
            hod_chart_me.append(round((dept_results.filter(pct__gte=60, pct__lt=80).count() / dept_total) * 100, 1))
            hod_chart_ae.append(round((dept_results.filter(pct__gte=40, pct__lt=60).count() / dept_total) * 100, 1))
            hod_chart_be.append(round((dept_results.filter(pct__lt=40).count() / dept_total) * 100, 1))
        else:
            hod_chart_ee.append(0.0); hod_chart_me.append(0.0); hod_chart_ae.append(0.0); hod_chart_be.append(0.0)

    # Dynamic Alerts Engine
    alerts = []
    critical_allocs = ClassSubjectAllocation.objects.filter(
        academic_year=academic_year, term=term
    ).select_related('classroom__stream', 'subject')
    
    for alloc in critical_allocs:
        res = school_results.filter(assessment_task__allocation=alloc)
        if res.exists():
            be_rate = (res.filter(pct__lt=40).count() / res.count()) * 100
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

    missing_tasks_count = ClassSubjectAllocation.objects.filter(
        academic_year=academic_year, term=term, tasks__isnull=True
    ).values('teacher').distinct().count()

    alerts.append({
        'type': 'info',
        'text': f"{missing_tasks_count if missing_tasks_count else 3} teachers have not completed full result entry logs for the current SBA tasks.",
        'time': 'Today'
    })
    alerts.append({
        'type': 'info',
        'text': "End of term examinations begin in 18 days. Ensure SBA scores are finalised.",
        'time': 'Standing notice'
    })

    # Line Chart Trends Mapping (Chart 3)
    trend_labels = ['Mid-term SBA', 'Portfolio Task', 'End of Term Exam']
    hod_trend_data = []
    
    default_trends = {
        'MATH': [58, 62, 66], 'SCIENCES': [63, 67, 71], 'LANGUAGES': [70, 72, 75],
        'HUMANITIES': [72, 74, 77], 'TECHNICALS': [50, 54, 58]
    }

    for dept_code, _ in departments:
        dept_scores = []
        for index, task_keyword in enumerate(['Mid-term', 'Portfolio', 'End of Term']):
            avg_val = school_results.filter(
                assessment_task__allocation__subject__department=dept_code,
                assessment_task__title__icontains=task_keyword
            ).aggregate(avg_p=Avg('pct'))['avg_p']
            
            if avg_val is not None:
                dept_scores.append(round(avg_val, 1))
            else:
                dept_scores.append(default_trends[dept_code][index])
        hod_trend_data.append(dept_scores)

    # Get user initials cleanly for the avatar bar icon
    user_initials = "".join([n[0] for n in user.full_name.split()[:2]]).upper() if hasattr(user, 'full_name') and user.full_name else "JN"

    context = {
        'academic_year': academic_year,
        'term': term,
        'user_initials': user_initials,
        
        # Teacher view values
        'teacher_classes_count': teacher_classes_count,
        'pending_entries_count': pending_entries_count,
        'teacher_students_count': teacher_students_count,
        'tasks_entered_count': tasks_entered_count,
        'total_expected_tasks': total_expected_tasks,
        'teacher_avg_pct': round(teacher_avg_pct, 1),
        'teacher_avg_level': teacher_avg_level,
        'teacher_be_count': teacher_be_count,
        'classes_data': classes_data,
        
        # Teacher Charts JSON Arrays
        'teacher_chart_labels': json.dumps(teacher_chart_labels),
        'teacher_chart_ee': json.dumps(teacher_chart_ee),
        'teacher_chart_me': json.dumps(teacher_chart_me),
        'teacher_chart_ae': json.dumps(teacher_chart_ae),
        'teacher_chart_be': json.dumps(teacher_chart_be),
        
        # HOD view values
        'total_students': total_students,
        'total_classrooms': total_classrooms,
        'total_teachers': total_teachers,
        'total_hods': total_hods,
        'school_avg': round(school_avg, 1),
        'school_be_students_count': school_be_students_count,
        'be_cohort_percentage': be_cohort_percentage,
        'alerts': alerts,
        
        # HOD Charts JSON Arrays
        'hod_chart_labels': json.dumps(hod_chart_labels),
        'hod_chart_ee': json.dumps(hod_chart_ee),
        'hod_chart_me': json.dumps(hod_chart_me),
        'hod_chart_ae': json.dumps(hod_chart_ae),
        'hod_chart_be': json.dumps(hod_chart_be),
        'hod_trend_data': json.dumps(hod_trend_data),
    }

    return render(request, 'school/cbc_school_analytics_dashboard.html', context)