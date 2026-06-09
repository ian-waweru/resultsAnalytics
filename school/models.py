from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from .managers import TeacherManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_year():
    return timezone.now().year


def _validate_academic_year(value):
    current = _current_year()
    if not (2000 <= value <= current + 2):
        raise ValidationError(
            f"Academic year must be between 2000 and {current + 2}. Got {value}."
        )


# ---------------------------------------------------------------------------
# Teacher (custom user)
# ---------------------------------------------------------------------------

class Teacher(AbstractUser):
    """
    Custom User model representing a teacher.
    Inherits all built-in Django auth fields (username, password, groups, etc.)

    NOTE: We keep `full_name` as the canonical display name instead of
    splitting across first_name / last_name, which is common in Kenyan school
    systems where names don't map cleanly to a Western first/last split.
    AbstractUser's first_name and last_name are left available but not used
    as the primary display field.
    """
    full_name = models.CharField(
        max_length=150,
        help_text="e.g., Jane Ngoiri",
    )
    tsc_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text=(
            "Teachers Service Commission number. "
            "Leave blank for Board of Management (BOM) employees."
        ),
    )
    is_hod = models.BooleanField(
        default=False,
        verbose_name="Head of Department Status",
        help_text="Designates whether this teacher has HOD-level permissions.",
    )

    objects = TeacherManager()

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Teacher"
        verbose_name_plural = "Teachers"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def employment_type(self) -> str:
        """Returns the hiring entity for reporting or profile views."""
        return "TSC (Government)" if self.tsc_number else "BOM (Board of Management)"

    def __str__(self) -> str:
        role = "HOD" if self.is_hod else "Teacher"
        return f"{self.full_name} ({role} – {self.employment_type})"


# ---------------------------------------------------------------------------
# Pathway
# ---------------------------------------------------------------------------

class Pathway(models.Model):
    """
    Represents one of the three KICD Senior Secondary School pathways,
    or a general base for junior/lower levels.
    """
    PATHWAY_CHOICES = [
        ("STEM", "Science, Technology, Engineering & Mathematics"),
        ("SS", "Social Sciences"),
        ("ASS", "Arts & Sports Science"),
        ("GENERAL", "Junior Secondary / Lower Level Base"),
    ]

    code = models.CharField(
        max_length=10,
        choices=PATHWAY_CHOICES,
        unique=True,
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Pathway"
        verbose_name_plural = "Pathways"

    def __str__(self):
        return self.get_code_display()


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------

class Stream(models.Model):
    """
    Represents a grade-level pathway combination.
    E.g., Grade 10 – STEM, Grade 11 – Social Sciences.

    FIX: `pathway` is now a FK to the Pathway model instead of a standalone
    CharField with its own hardcoded choices. This eliminates the previous
    code mismatch between Stream ("SOCIAL_SCIENCES", "ARTS_SPORTS") and
    Pathway ("SS", "ASS") and ensures a single source of truth.
    """
    name = models.CharField(
        max_length=50,
        help_text="Grade level, e.g. 'Grade 10', 'Grade 11'",
    )
    pathway = models.ForeignKey(
        Pathway,
        on_delete=models.PROTECT,
        null=True,
        blank=True,  # blank for GENERAL / junior streams
        related_name="streams",
        help_text=(
            "The KICD pathway this stream belongs to. "
            "Leave blank for junior/lower secondary streams."
        ),
    )

    class Meta:
        ordering = ["name", "pathway__code"]
        verbose_name = "Stream"
        verbose_name_plural = "Streams"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "pathway"],
                name="unique_stream_combination"
            )
        ]

    def __str__(self) -> str:
        pathway_label = self.pathway.get_code_display() if self.pathway else "General"
        return f"{self.name} – {pathway_label}"


# ---------------------------------------------------------------------------
# Classroom
# ---------------------------------------------------------------------------

class Classroom(models.Model):
    """
    A physical classroom section within a stream.
    E.g., Stream: Grade 10 STEM + Name: 'East'  →  Grade 10 East (STEM).
    """
    name = models.CharField(
        max_length=50,
        help_text="Section identifier, e.g. 'East', 'West', 'A', 'B'",
    )
    stream = models.ForeignKey(
        Stream,
        on_delete=models.CASCADE,
        related_name="classrooms",
    )

    class Meta:
        ordering = ["stream__name", "name"]
        verbose_name = "Classroom"
        verbose_name_plural = "Classrooms"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "stream"],
                name="unique_classroom_section_per_stream"
            )
        ]

    def __str__(self) -> str:
        return f"{self.stream.name} {self.name}"


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------

class Student(models.Model):
    """
    Represents an individual learner enrolled in the school.

    `admission_number` is school-wide unique and acts as the stable identifier
    across academic years. Current classroom placement is derived from the
    student's active StudentEnrollment record, not stored directly here.
    """
    name = models.CharField(max_length=150)
    admission_number = models.CharField(max_length=50, unique=True)
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Used for age-grade validation and reporting.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Student"
        verbose_name_plural = "Students"

    def __str__(self) -> str:
        return f"{self.admission_number} – {self.name}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def current_enrollment(self, academic_year: int = None):
        """
        Returns the active StudentEnrollment for the given (or current) year,
        or None if the student is not enrolled that year.
        """
        year = academic_year or _current_year()
        return self.enrollments.filter(academic_year=year, is_active=True).first()


# ---------------------------------------------------------------------------
# StudentEnrollment
# ---------------------------------------------------------------------------

class StudentEnrollment(models.Model):
    """
    Records which classroom a student belongs to in a given academic year
    and term.
    """
    TERM_CHOICES = [
        (1, "Term 1"),
        (2, "Term 2"),
        (3, "Term 3"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    academic_year = models.PositiveIntegerField(
        validators=[_validate_academic_year],
        default=_current_year,
        help_text="e.g., 2026",
    )
    term = models.PositiveIntegerField(
        choices=TERM_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
        help_text="Term in which this placement is effective.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Set to False when a student transfers out mid-term "
            "rather than deleting the historical record."
        ),
    )
    enrolled_on = models.DateField(
        default=timezone.now,
        help_text="Date the enrollment became effective.",
    )

    class Meta:
        ordering = ["academic_year", "term", "student__name"]
        verbose_name = "Student Enrollment"
        verbose_name_plural = "Student Enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year", "term"],
                name="unique_student_enrollment_per_term"
            )
        ]

    def __str__(self) -> str:
        status = "Active" if self.is_active else "Inactive"
        return (
            f"{self.student.name} → {self.classroom} "
            f"[{self.academic_year} T{self.term}] ({status})"
        )


# ---------------------------------------------------------------------------
# Subject
# ---------------------------------------------------------------------------

class Subject(models.Model):
    """
    A subject aligned to the KICD SSS national syllabus.
    Core subjects apply to all pathways; electives are pathway-specific.
    """
    CATEGORY_CHOICES = [
        ("CORE", "Core Subject"),         # Compulsory for all pathways
        ("ELECTIVE", "Elective Subject"),  # Pathway-specific
    ]

    LEARNING_AREA_CHOICES = [
        # Core learning areas (all pathways)
        ("LANG", "Languages & Literature"),
        ("CSL", "Community Service Learning"),
        ("PE", "Physical Education"),
        ("LIFE", "Life Skills Education"),
        ("RE", "Religious Education"),
        # STEM
        ("MATH", "Mathematics"),
        ("BIO", "Biology"),
        ("CHEM", "Chemistry"),
        ("PHY", "Physics"),
        ("CS", "Computer Science"),
        ("AGRI", "Agriculture & Nutrition"),
        ("TECH", "Technical & Engineering"),
        # Social Sciences
        ("HIST", "History & Citizenship"),
        ("GEO", "Geography"),
        ("BUS", "Business Studies"),
        ("ECON", "Economics"),
        ("FOREIGN_LANG", "Foreign Languages"),
        # Arts & Sports Science
        ("ART", "Fine Art & Design"),
        ("PERF", "Performing Arts"),
        ("SPORT", "Sports Science"),
        ("HOME", "Home Science"),
        ("MEDIA", "Media & Film Technology"),
        ("FASHION", "Fashion & Design"),
    ]

    name = models.CharField(max_length=100)
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Short code e.g. ENG, CHEM, HIST",
    )
    learning_area = models.CharField(
        max_length=20,
        choices=LEARNING_AREA_CHOICES,
    )
    category = models.CharField(
        max_length=10,
        choices=CATEGORY_CHOICES,
        help_text="Core = all students; Elective = pathway-specific",
    )
    pathways = models.ManyToManyField(
        Pathway,
        blank=True,
        related_name="subjects",
        help_text="Leave blank for core subjects (apply to all pathways)",
    )

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "learning_area"],
                name="unique_subject_per_learning_area"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


# ---------------------------------------------------------------------------
# ClassSubjectAllocation
# ---------------------------------------------------------------------------

class ClassSubjectAllocation(models.Model):
    """
    Assigns a subject in a specific classroom to a designated teacher
    for a particular academic year and term.
    """
    TERM_CHOICES = [
        (1, "Term 1"),
        (2, "Term 2"),
        (3, "Term 3"),
    ]

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="subject_allocations",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="class_allocations",
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="allocations",
    )
    academic_year = models.PositiveIntegerField(
        validators=[_validate_academic_year],
        default=_current_year,
        help_text="Academic year this allocation applies to, e.g. 2026.",
    )
    term = models.PositiveIntegerField(
        choices=TERM_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
        help_text="Term this allocation applies to.",
    )
    formative_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=70.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=(
            "Percentage weight of formative (SBA) scores in the final grade. "
            "Summative weight is derived as 100 minus this value. "
            "KICD default: 70."
        ),
    )

    class Meta:
        ordering = ["academic_year", "term", "classroom", "subject__name"]
        verbose_name = "Class–Subject Allocation"
        verbose_name_plural = "Class–Subject Allocations"
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "subject", "academic_year", "term"],
                name="unique_allocation_per_term"
            )
        ]

    @property
    def summative_weight(self) -> float:
        """Derived summative (exam) weight — always sums to 100 with formative."""
        return round(100 - float(self.formative_weight), 2)

    def __str__(self) -> str:
        teacher_label = self.teacher.full_name if self.teacher_id else "Unassigned"
        return (
            f"[{self.academic_year} T{self.term}] "
            f"{self.classroom} | {self.subject.name} → {teacher_label}"
        )


# ---------------------------------------------------------------------------
# StudentSubjectSelection
# ---------------------------------------------------------------------------

class StudentSubjectSelection(models.Model):
    """
    Records a student's chosen pathway and elected subjects for a grade/year.
    Enforces KICD SSS selection rules:
      - Exactly 1 pathway per student per year
      - All core subjects are auto-included (not stored here)
      - 3–4 electives must be from the chosen pathway
    """
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="subject_selections",
    )
    pathway = models.ForeignKey(
        Pathway,
        on_delete=models.PROTECT,
        related_name="student_selections",
    )
    elective_subjects = models.ManyToManyField(
        Subject,
        limit_choices_to={"category": "ELECTIVE"},
        related_name="student_selections",
        help_text="3–4 elective subjects from the chosen pathway",
    )
    academic_year = models.PositiveIntegerField(
        validators=[_validate_academic_year],
        default=_current_year,
    )
    grade = models.PositiveIntegerField(
        choices=[(10, "Grade 10"), (11, "Grade 11"), (12, "Grade 12")],
        help_text="SSS grade level for this selection",
    )
    is_approved = models.BooleanField(
        default=False,
        help_text="Approved by the class teacher / administration",
    )

    class Meta:
        ordering = ["academic_year", "grade", "student__name"]
        verbose_name = "Student Subject Selection"
        verbose_name_plural = "Student Subject Selections"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year", "grade"],
                name="unique_selection_per_student_per_year"
            )
        ]

    def clean(self):
        errors = {}

        if self.pk:
            # Validate elective count — must be between 3 and 4
            elective_count = self.elective_subjects.count()
            if not (3 <= elective_count <= 4):
                errors["elective_subjects"] = (
                    f"A student must select between 3 and 4 elective subjects. "
                    f"Currently selected: {elective_count}."
                )

            # FIX: cast to list so truthiness check works correctly.
            # A bare QuerySet is always truthy even when it contains no rows.
            invalid = list(
                self.elective_subjects.exclude(
                    pathways=self.pathway
                ).values_list("name", flat=True)
            )
            if invalid:
                errors["elective_subjects"] = (
                    f"These subjects don't belong to the {self.pathway} pathway: "
                    f"{', '.join(invalid)}"
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.student.name} | {self.pathway} | "
            f"Grade {self.grade} ({self.academic_year})"
        )


# ---------------------------------------------------------------------------
# AssessmentTask
# ---------------------------------------------------------------------------

class AssessmentTask(models.Model):
    """
    A graded event (SBA task or end-of-term exam) within a class-subject
    allocation.
    """
    TASK_TYPE_CHOICES = [
        ("FORMATIVE", "School-Based Assessment – Formative"),
        ("SUMMATIVE", "End-of-Term Examination – Summative"),
    ]

    allocation = models.ForeignKey(
        ClassSubjectAllocation,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    title = models.CharField(
        max_length=150,
        help_text="e.g., 'Volumetric Analysis Practical', 'Mid-Term SBA'",
    )
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES)
    max_points = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
        help_text="Total maximum marks for this task (1–1000)",
    )
    date_administered = models.DateField(
        null=True,
        blank=True,
        help_text="Date the assessment was sat or submitted.",
    )

    # Audit trail: preserves the historical record of which human teacher
    # assessed the task, even if the parent allocation's structural relationship
    # changes or gets unassigned later.
    evaluating_teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluated_tasks",
        help_text="The teacher who administered and evaluated this task for compliance history.",
    )

    class Meta:
        ordering = ["allocation__academic_year", "allocation__term", "allocation", "title"]
        verbose_name = "Assessment Task"
        verbose_name_plural = "Assessment Tasks"
        constraints = [
            models.UniqueConstraint(
                fields=["allocation", "title"],
                name="unique_task_title_per_allocation"
            )
        ]

    def __str__(self) -> str:
        alloc = self.allocation
        return (
            f"[{alloc.academic_year} T{alloc.term}] "
            f"{alloc.classroom} – {alloc.subject.name}: "
            f"{self.title}"
        )


# ---------------------------------------------------------------------------
# LearnerAssessmentResult
# ---------------------------------------------------------------------------

class LearnerAssessmentResult(models.Model):
    """
    Records a student's score on a specific assessment task.
    """
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="results",
    )
    assessment_task = models.ForeignKey(
        AssessmentTask,
        on_delete=models.CASCADE,
        related_name="student_results",
    )
    score_achieved = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Raw numerical score (0 – task's max_points)",
    )
    teacher_remarks = models.TextField(
        blank=True,
        default="",
        help_text="Qualitative feedback mapping specific competencies",
    )
    recorded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp of when the result was first entered.",
    )
    last_modified_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of the most recent edit — useful for audit trails.",
    )

    class Meta:
        ordering = ["assessment_task", "student__name"]
        verbose_name = "Learner Assessment Result"
        verbose_name_plural = "Learner Assessment Results"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "assessment_task"],
                name="unique_student_result_per_task"
            )
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        """
        Optimized validation using select_related to prevent N+1 DB bottlenecks.
        Validates maximum allowed limits and cross-references active enrollment history.
        """
        errors = {}

        if self.score_achieved is not None and self.assessment_task_id:
            try:
                task_with_alloc = AssessmentTask.objects.select_related(
                    "allocation__classroom"
                ).get(id=self.assessment_task_id)
                alloc = task_with_alloc.allocation
                max_pts = task_with_alloc.max_points

                if self.score_achieved > max_pts:
                    errors["score_achieved"] = (
                        f"Score {self.score_achieved} exceeds the maximum "
                        f"allowed marks ({max_pts}) for this task."
                    )

                if self.student_id:
                    enrolled = StudentEnrollment.objects.filter(
                        student_id=self.student_id,
                        classroom=alloc.classroom,
                        academic_year=alloc.academic_year,
                        term=alloc.term,
                        is_active=True,
                    ).exists()

                    if not enrolled:
                        errors["student"] = (
                            f"Student ID {self.student_id} does not have an active enrollment "
                            f"in {alloc.classroom} for {alloc.academic_year} T{alloc.term}."
                        )
            except AssessmentTask.DoesNotExist:
                errors["assessment_task"] = "The selected assessment task does not exist."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------

    @property
    def percentage(self) -> float:
        """Percentage score rounded to two decimal places."""
        if self.assessment_task.max_points:
            return round(
                float(self.score_achieved) / self.assessment_task.max_points * 100, 2
            )
        return 0.0

    @property
    def cbc_performance_level(self) -> str:
        """
        Maps percentage to Kenya's CBC four-tier performance descriptor.
        Thresholds per KICD guidelines:
            Exceeding Expectations   ≥ 80%
            Meeting Expectations     60 – 79%
            Approaching Expectations 40 – 59%
            Below Expectations       < 40%
        """
        pct = self.percentage
        if pct >= 80:
            return "Exceeding Expectations (EE)"
        elif pct >= 60:
            return "Meeting Expectations (ME)"
        elif pct >= 40:
            return "Approaching Expectations (AE)"
        else:
            return "Below Expectations (BE)"

    @property
    def dynamic_weighted_score(self) -> float:
        """
        Returns the score scaled down by dividing the weight across the number
        of assigned bucket-specific tasks.

        NOTE: Relying on this property inside loop/list views triggers a
        performance-heavy count query per row. For scalable reporting datasets
        (like report cards), it is highly recommended to perform this calculation
        via an aggregate `annotate()` or clean group-by on the QuerySet level instead.
        """
        task = self.assessment_task
        alloc = task.allocation

        task_count = AssessmentTask.objects.filter(
            allocation=alloc,
            task_type=task.task_type,
        ).count() or 1

        if task.task_type == "FORMATIVE":
            bucket_weight = (float(alloc.formative_weight) / 100) / task_count
        else:
            bucket_weight = (float(alloc.summative_weight) / 100) / task_count

        return round(self.percentage * bucket_weight, 2)

    def __str__(self) -> str:
        return (
            f"{self.student.name} → {self.assessment_task.title}: "
            f"{self.score_achieved}/{self.assessment_task.max_points} "
            f"({self.percentage}% – {self.cbc_performance_level})"
        )