from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Avg, Count, Q
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    Teacher,
    Pathway,
    Stream,
    Classroom,
    Student,
    StudentEnrollment,
    Subject,
    ClassSubjectAllocation,
    StudentSubjectSelection,
    AssessmentTask,
    LearnerAssessmentResult,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _performance_badge(level: str) -> str:
    """Returns a coloured HTML badge for a CBC performance level string."""
    colours = {
        "EE": ("#1a7a3e", "#d4edda"),   # green
        "ME": ("#0c5460", "#d1ecf1"),   # teal
        "AE": ("#856404", "#fff3cd"),   # amber
        "BE": ("#721c24", "#f8d7da"),   # red
    }
    code = level[-3:-1] if "(" in level else ""
    fg, bg = colours.get(code, ("#333", "#eee"))
    return format_html(
        '<span style="background:{};color:{};padding:2px 8px;border-radius:4px;'
        'font-size:0.8em;font-weight:600;">{}</span>',
        bg, fg, level,
    )


# ===========================================================================
# Inlines
# ===========================================================================

class ClassroomInline(admin.TabularInline):
    model = Classroom
    extra = 1
    fields = ("name",)
    verbose_name = "Classroom Section"
    verbose_name_plural = "Classroom Sections"


class StudentEnrollmentInline(admin.TabularInline):
    model = StudentEnrollment
    extra = 0
    fields = ("classroom", "academic_year", "term", "is_active", "enrolled_on")
    readonly_fields = ("enrolled_on",)
    show_change_link = True


class StudentSubjectSelectionInline(admin.StackedInline):
    model = StudentSubjectSelection
    extra = 0
    fields = ("pathway", "grade", "academic_year", "elective_subjects", "is_approved")
    filter_horizontal = ("elective_subjects",)
    show_change_link = True


class AssessmentTaskInline(admin.TabularInline):
    model = AssessmentTask
    extra = 0
    fields = ("title", "task_type", "max_points", "date_administered", "evaluating_teacher")
    show_change_link = True


class LearnerAssessmentResultInline(admin.TabularInline):
    model = LearnerAssessmentResult
    extra = 0
    fields = ("student", "score_achieved", "percentage_display", "performance_badge", "teacher_remarks")
    readonly_fields = ("percentage_display", "performance_badge")
    show_change_link = True

    @admin.display(description="Score %")
    def percentage_display(self, obj):
        return f"{obj.percentage}%"

    @admin.display(description="Performance Level")
    def performance_badge(self, obj):
        return mark_safe(_performance_badge(obj.cbc_performance_level))


class ClassSubjectAllocationInline(admin.TabularInline):
    model = ClassSubjectAllocation
    extra = 0
    fields = ("subject", "teacher", "term", "academic_year", "formative_weight")
    show_change_link = True


# ===========================================================================
# Teacher
# ===========================================================================

@admin.register(Teacher)
class TeacherAdmin(UserAdmin):
    list_display  = (
        "full_name", "username", "tsc_number", "employment_type_display",
        "is_hod", "is_active", "allocation_count",
    )
    list_filter   = ("is_hod", "is_active", "is_staff")
    search_fields = ("full_name", "username", "tsc_number", "email")
    ordering      = ("full_name",)
    
    # Optimize list view queries
    # Note: list_select_related is not directly available in UserAdmin, 
    # but we optimize in get_queryset instead

    fieldsets = (
        ("Identity", {
            "fields": ("username", "password"),
        }),
        ("Personal Info", {
            "fields": ("full_name", "email", "tsc_number"),
        }),
        ("Role & Status", {
            "fields": ("is_hod", "is_active", "is_staff", "is_superuser"),
        }),
        ("Groups & Permissions", {
            "classes": ("collapse",),
            "fields": ("groups", "user_permissions"),
        }),
        ("Important Dates", {
            "classes": ("collapse",),
            "fields": ("last_login", "date_joined"),
        }),
    )

    add_fieldsets = (
        ("Create Teacher", {
            "classes": ("wide",),
            "fields": ("username", "full_name", "tsc_number", "password1", "password2"),
        }),
    )

    readonly_fields = ("last_login", "date_joined")

    @admin.display(description="Employment Type")
    def employment_type_display(self, obj):
        return obj.employment_type

    @admin.display(description="Allocations")
    def allocation_count(self, obj):
        # Use cached annotation if available
        if hasattr(obj, '_alloc_count'):
            count = obj._alloc_count
        else:
            count = obj.allocations.count()
        url = (
            reverse("admin:school_classsubjectallocation_changelist")
            + f"?teacher__id__exact={obj.pk}"
        )
        return format_html('<a href="{}">{} subject(s)</a>', url, count)

    def get_queryset(self, request):
        # Annotate with allocation count to avoid N+1 queries in list view
        return super().get_queryset(request).annotate(
            _alloc_count=Count("allocations", distinct=True)
        )


# ===========================================================================
# Pathway
# ===========================================================================

@admin.register(Pathway)
class PathwayAdmin(admin.ModelAdmin):
    list_display  = ("code", "name", "stream_count", "subject_count", "student_count")
    search_fields = ("code", "name")
    ordering      = ("code",)

    @admin.display(description="Streams")
    def stream_count(self, obj):
        # Use cached annotation if available
        if hasattr(obj, '_stream_count'):
            return obj._stream_count
        return obj.streams.count()

    @admin.display(description="Subjects")
    def subject_count(self, obj):
        # Use cached annotation if available
        if hasattr(obj, '_subject_count'):
            return obj._subject_count
        return obj.subjects.count()

    @admin.display(description="Students Enrolled")
    def student_count(self, obj):
        if hasattr(obj, '_student_count'):
            return obj._student_count
        return StudentSubjectSelection.objects.filter(pathway=obj).count()

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "streams", "subjects"
        ).annotate(
            _stream_count=Count("streams", distinct=True),
            _subject_count=Count("subjects", distinct=True),
            _student_count=Count("student_selections", distinct=True),
        )


# ===========================================================================
# Stream
# ===========================================================================

@admin.register(Stream)
class StreamAdmin(admin.ModelAdmin):
    list_display   = ("__str__", "name", "pathway", "classroom_count")
    list_filter    = ("pathway", "name")
    search_fields  = ("name", "pathway__name", "pathway__code")
    ordering       = ("name", "pathway__code")
    inlines        = [ClassroomInline]

    @admin.display(description="Classrooms")
    def classroom_count(self, obj):
        count = obj.classrooms.count()
        url = (
            reverse("admin:school_classroom_changelist")
            + f"?stream__id__exact={obj.pk}"
        )
        return format_html('<a href="{}">{}</a>', url, count)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("pathway").annotate(
            _classroom_count=Count("classrooms")
        )


# ===========================================================================
# Classroom
# ===========================================================================

@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display   = ("__str__", "stream", "pathway_display", "enrollment_count", "allocation_count")
    list_filter    = ("stream__pathway", "stream__name")
    search_fields  = ("name", "stream__name", "stream__pathway__name")
    ordering       = ("stream__name", "name")
    inlines        = [ClassSubjectAllocationInline]

    @admin.display(description="Pathway")
    def pathway_display(self, obj):
        if hasattr(obj, '_pathway_code'):
            return obj._pathway_code
        return obj.stream.pathway.get_code_display() if obj.stream.pathway else "—"

    @admin.display(description="Enrolled Students")
    def enrollment_count(self, obj):
        if hasattr(obj, '_enrollment_count'):
            count = obj._enrollment_count
        else:
            count = obj.enrollments.filter(is_active=True).count()
        url = (
            reverse("admin:school_studentenrollment_changelist")
            + f"?classroom__id__exact={obj.pk}&is_active__exact=1"
        )
        return format_html('<a href="{}">{}</a>', url, count)

    @admin.display(description="Subject Allocations")
    def allocation_count(self, obj):
        if hasattr(obj, '_allocation_count'):
            return obj._allocation_count
        return obj.subject_allocations.count()

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "stream__pathway"
        ).annotate(
            _enrollment_count=Count("enrollments", filter=Q(enrollments__is_active=True), distinct=True),
            _allocation_count=Count("subject_allocations", distinct=True),
            _pathway_code=F("stream__pathway__code"),
        )


# ===========================================================================
# Student
# ===========================================================================

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display   = (
        "admission_number", "name", "date_of_birth",
        "current_classroom_display", "pathway_display", "result_count",
    )
    search_fields  = ("name", "admission_number")
    ordering       = ("name",)
    inlines        = [StudentEnrollmentInline, StudentSubjectSelectionInline]

    @admin.display(description="Current Classroom")
    def current_classroom_display(self, obj):
        # Check if we have prefetched enrollments
        if hasattr(obj, '_prefetched_objects_cache'):
            enrollments = [e for e in obj.enrollments.all() if e.is_active]
            enrollment = enrollments[-1] if enrollments else None
        else:
            enrollment = obj.current_enrollment()
        
        if enrollment:
            return str(enrollment.classroom)
        return mark_safe('<span style="color:#999;">Not enrolled</span>')

    @admin.display(description="Pathway")
    def pathway_display(self, obj):
        if hasattr(obj, '_pathway_code'):
            return obj._pathway_code
        selection = obj.subject_selections.order_by("-academic_year").first()
        if selection:
            return selection.pathway.get_code_display()
        return "—"

    @admin.display(description="Results")
    def result_count(self, obj):
        if hasattr(obj, '_result_count'):
            count = obj._result_count
        else:
            count = obj.results.count()
        url = (
            reverse("admin:school_learnerassessmentresult_changelist")
            + f"?student__id__exact={obj.pk}"
        )
        return format_html('<a href="{}">{}</a>', url, count)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "enrollments__classroom__stream__pathway",
            "subject_selections__pathway",
        ).annotate(
            _result_count=Count("results", distinct=True),
            _pathway_code=F("subject_selections__pathway__code"),
        )


# ===========================================================================
# StudentEnrollment
# ===========================================================================

@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display  = (
        "student", "classroom", "academic_year", "term",
        "is_active", "enrolled_on",
    )
    list_filter   = ("academic_year", "term", "is_active", "classroom__stream__pathway")
    search_fields = ("student__name", "student__admission_number", "classroom__name")
    ordering      = ("-academic_year", "term", "student__name")
    date_hierarchy = "enrolled_on"
    list_editable  = ("is_active",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "student", "classroom__stream__pathway"
        )


# ===========================================================================
# Subject
# ===========================================================================

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display   = ("name", "code", "category_badge", "learning_area_display", "pathways_display")
    list_filter    = ("category", "learning_area", "pathways")
    search_fields  = ("name", "code")
    ordering       = ("category", "name")
    filter_horizontal = ("pathways",)

    @admin.display(description="Category")
    def category_badge(self, obj):
        if obj.category == "CORE":
            return mark_safe(
                '<span style="background:#cce5ff;color:#004085;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:600;">CORE</span>'
            )
        return mark_safe(
            '<span style="background:#e2e3e5;color:#383d41;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:600;">ELECTIVE</span>'
        )

    @admin.display(description="Learning Area")
    def learning_area_display(self, obj):
        return obj.get_learning_area_display()

    @admin.display(description="Pathways")
    def pathways_display(self, obj):
        if obj.category == "CORE":
            return mark_safe('<em style="color:#999;">All pathways</em>')
        return ", ".join(p.code for p in obj.pathways.all()) or "—"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("pathways")


# ===========================================================================
# ClassSubjectAllocation
# ===========================================================================

@admin.register(ClassSubjectAllocation)
class ClassSubjectAllocationAdmin(admin.ModelAdmin):
    list_display  = (
        "__str__", "classroom", "subject", "teacher",
        "academic_year", "term", "formative_weight", "summative_weight_display",
        "task_count",
    )
    list_filter   = (
        "academic_year", "term",
        "classroom__stream__pathway",
        "classroom__stream__name",
        "subject__category",
    )
    search_fields = (
        "classroom__name", "subject__name", "subject__code",
        "teacher__full_name",
    )
    ordering      = ("-academic_year", "term", "classroom__stream__name", "subject__name")
    inlines       = [AssessmentTaskInline]
    autocomplete_fields = ("teacher", "subject", "classroom")

    @admin.display(description="Summative Weight %")
    def summative_weight_display(self, obj):
        return f"{obj.summative_weight}%"

    @admin.display(description="Tasks")
    def task_count(self, obj):
        if hasattr(obj, '_task_count'):
            count = obj._task_count
        else:
            count = obj.tasks.count()
        url = (
            reverse("admin:school_assessmenttask_changelist")
            + f"?allocation__id__exact={obj.pk}"
        )
        return format_html('<a href="{}">{}</a>', url, count)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "classroom__stream__pathway", "subject", "teacher"
        ).annotate(
            _task_count=Count("tasks", distinct=True)
        )


# ===========================================================================
# StudentSubjectSelection
# ===========================================================================

@admin.register(StudentSubjectSelection)
class StudentSubjectSelectionAdmin(admin.ModelAdmin):
    list_display      = (
        "student", "pathway", "grade", "academic_year",
        "elective_count", "is_approved",
    )
    list_filter       = ("pathway", "grade", "academic_year", "is_approved")
    search_fields     = ("student__name", "student__admission_number")
    ordering          = ("-academic_year", "grade", "student__name")
    list_editable     = ("is_approved",)
    filter_horizontal = ("elective_subjects",)
    autocomplete_fields = ("student",)

    @admin.display(description="Electives Selected")
    def elective_count(self, obj):
        count = obj.elective_subjects.count()
        colour = "#1a7a3e" if 3 <= count <= 4 else "#721c24"
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>', colour, count
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "student", "pathway"
        ).prefetch_related("elective_subjects").annotate(
            _elective_count=Count("elective_subjects")
        )


# ===========================================================================
# AssessmentTask
# ===========================================================================

@admin.register(AssessmentTask)
class AssessmentTaskAdmin(admin.ModelAdmin):
    list_display  = (
        "title", "allocation_display", "task_type_badge",
        "max_points", "date_administered", "evaluating_teacher",
        "result_count", "class_average",
    )
    list_filter   = (
        "task_type",
        "allocation__academic_year",
        "allocation__term",
        "allocation__classroom__stream__pathway",
    )
    search_fields = (
        "title",
        "allocation__subject__name",
        "allocation__classroom__name",
        "evaluating_teacher__full_name",
    )
    ordering      = (
        "-allocation__academic_year",
        "allocation__term",
        "allocation__classroom__stream__name",
        "title",
    )
    date_hierarchy = "date_administered"
    inlines        = [LearnerAssessmentResultInline]
    autocomplete_fields = ("allocation", "evaluating_teacher")

    @admin.display(description="Allocation")
    def allocation_display(self, obj):
        alloc = obj.allocation
        return f"{alloc.classroom} – {alloc.subject.name} [{alloc.academic_year} T{alloc.term}]"

    @admin.display(description="Type")
    def task_type_badge(self, obj):
        if obj.task_type == "FORMATIVE":
            return mark_safe(
                '<span style="background:#d4edda;color:#1a7a3e;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:600;">FORMATIVE</span>'
            )
        return mark_safe(
            '<span style="background:#cce5ff;color:#004085;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:600;">SUMMATIVE</span>'
        )

    @admin.display(description="Results")
    def result_count(self, obj):
        if hasattr(obj, '_result_count'):
            count = obj._result_count
        else:
            count = obj.student_results.count()
        url = (
            reverse("admin:school_learnerassessmentresult_changelist")
            + f"?assessment_task__id__exact={obj.pk}"
        )
        return format_html('<a href="{}">{}</a>', url, count)

    @admin.display(description="Class Average %")
    def class_average(self, obj):
        avg = obj.student_results.aggregate(
            avg=Avg("score_achieved")
        )["avg"]
        if avg is None:
            return "—"
        pct = round(float(avg) / obj.max_points * 100, 1)
        colour = (
            "#1a7a3e" if pct >= 80
            else "#0c5460" if pct >= 60
            else "#856404" if pct >= 40
            else "#721c24"
        )
        return format_html(
            '<span style="color:{};font-weight:600;">{}%</span>', colour, pct
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "allocation__classroom__stream__pathway",
            "allocation__subject",
            "evaluating_teacher",
        ).annotate(
            _result_count=Count("student_results", distinct=True)
        )


# ===========================================================================
# LearnerAssessmentResult
# ===========================================================================

@admin.register(LearnerAssessmentResult)
class LearnerAssessmentResultAdmin(admin.ModelAdmin):
    list_display  = (
        "student", "task_display", "subject_display",
        "score_display", "percentage_display", "performance_badge_display",
        "recorded_at",
    )
    list_filter   = (
        "assessment_task__task_type",
        "assessment_task__allocation__academic_year",
        "assessment_task__allocation__term",
        "assessment_task__allocation__classroom__stream__pathway",
        "assessment_task__allocation__classroom__stream__name",
    )
    search_fields = (
        "student__name",
        "student__admission_number",
        "assessment_task__title",
        "assessment_task__allocation__subject__name",
    )
    ordering      = ("-assessment_task__allocation__academic_year", "student__name")
    readonly_fields = (
        "percentage_display", "performance_badge_display",
        "recorded_at", "last_modified_at",
    )
    date_hierarchy = "recorded_at"
    autocomplete_fields = ("student", "assessment_task")

    fieldsets = (
        ("Learner & Task", {
            "fields": ("student", "assessment_task"),
        }),
        ("Score", {
            "fields": (
                "score_achieved",
                "percentage_display",
                "performance_badge_display",
            ),
        }),
        ("Feedback", {
            "fields": ("teacher_remarks",),
        }),
        ("Audit", {
            "classes": ("collapse",),
            "fields": ("recorded_at", "last_modified_at"),
        }),
    )

    @admin.display(description="Task")
    def task_display(self, obj):
        return obj.assessment_task.title

    @admin.display(description="Subject")
    def subject_display(self, obj):
        return obj.assessment_task.allocation.subject.name

    @admin.display(description="Score")
    def score_display(self, obj):
        return f"{obj.score_achieved} / {obj.assessment_task.max_points}"

    @admin.display(description="Score %")
    def percentage_display(self, obj):
        return f"{obj.percentage}%"

    @admin.display(description="Performance Level")
    def performance_badge_display(self, obj):
        return mark_safe(_performance_badge(obj.cbc_performance_level))

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "student",
            "assessment_task__allocation__subject",
            "assessment_task__allocation__classroom__stream__pathway",
        )


# ===========================================================================
# Admin site branding
# ===========================================================================

admin.site.site_header  = "CBC Senior Secondary School — Results Management"
admin.site.site_title   = "SSS Results Admin"
admin.site.index_title  = "Dashboard"