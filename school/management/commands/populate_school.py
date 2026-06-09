import random
from decimal import Decimal
from faker import Faker

from django.core.management.base import BaseCommand
from school.models import (
    Teacher, Stream, Classroom, Student, StudentEnrollment,
    Subject, ClassSubjectAllocation, AssessmentTask, LearnerAssessmentResult
)

fake = Faker()

# Seeding constants — change these to generate more or less data.
ACADEMIC_YEAR = 2026
TERM = 1
NUM_TEACHERS = 35
NUM_STUDENTS = 700


class Command(BaseCommand):
    help = "Seed the database with realistic CBC school data."

    def handle(self, *args, **options):
        self._clear()
        teachers = self._create_teachers()
        classrooms = self._create_streams_and_classrooms()
        students = self._create_students_and_enroll(classrooms)
        subjects = self._create_subjects()
        allocations = self._create_allocations(classrooms, subjects, teachers)
        tasks = self._create_tasks(allocations)
        self._create_results(allocations, tasks, students, classrooms)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created {NUM_TEACHERS} teachers, {NUM_STUDENTS} students, "
            f"{len(allocations)} allocations, {len(tasks)} tasks."
        ))

    # ------------------------------------------------------------------
    # Step 0 – Clear
    # ------------------------------------------------------------------

    def _clear(self):
        self.stdout.write("Clearing existing data...")
        # Delete in reverse dependency order to avoid FK constraint errors.
        LearnerAssessmentResult.objects.all().delete()
        AssessmentTask.objects.all().delete()
        ClassSubjectAllocation.objects.all().delete()
        StudentEnrollment.objects.all().delete()
        Student.objects.all().delete()
        Classroom.objects.all().delete()
        Stream.objects.all().delete()
        Subject.objects.all().delete()
        Teacher.objects.all().delete()

    # ------------------------------------------------------------------
    # Step 1 – Teachers
    # ------------------------------------------------------------------

    def _create_teachers(self):
        self.stdout.write(f"Generating {NUM_TEACHERS} teachers...")
        instances = []
        for i in range(1, NUM_TEACHERS + 1):
            is_hod = i <= 5
            is_tsc = random.choice([True, True, False])
            full_name = fake.name()
            username = f"{full_name.split()[0].lower()}{random.randint(10, 99)}"

            t = Teacher(
                username=username,
                full_name=full_name,
                tsc_number=f"TSC-{random.randint(100000, 999999)}" if is_tsc else None,
                is_hod=is_hod,
                is_staff=is_hod,
            )
            t.set_password("password123")
            instances.append(t)

        # bulk_create preserves the hashed passwords set by set_password()
        # above because it inserts the in-memory objects as-is.
        return Teacher.objects.bulk_create(instances)

    # ------------------------------------------------------------------
    # Step 2 – Streams & Classrooms
    # ------------------------------------------------------------------

    def _create_streams_and_classrooms(self):
        self.stdout.write("Generating streams and classrooms...")
        stream_stem = Stream.objects.create(name="Grade 10", pathway="STEM")
        stream_arts = Stream.objects.create(name="Grade 11", pathway="ARTS_SPORTS")

        classroom_data = [
            ("East", stream_stem),
            ("West", stream_stem),
            ("North", stream_stem),
            ("South", stream_stem),
            ("Alpha", stream_arts),
            ("Beta", stream_arts),
            ("Gamma", stream_arts),
        ]
        return Classroom.objects.bulk_create([
            Classroom(name=name, stream=stream)
            for name, stream in classroom_data
        ])

    # ------------------------------------------------------------------
    # Step 3 – Students + Enrollments
    # ------------------------------------------------------------------

    def _create_students_and_enroll(self, classrooms):
        """
        Creates Student rows first (no classroom FK — that was removed),
        then creates a StudentEnrollment for each student placing them in
        a classroom for the seeded academic year and term.
        """
        self.stdout.write(f"Generating {NUM_STUDENTS} students and enrolling them...")

        student_instances = [
            Student(
                name=fake.name(),
                admission_number=str(10001 + i),
            )
            for i in range(NUM_STUDENTS)
        ]
        students = Student.objects.bulk_create(student_instances)

        enrollment_instances = [
            StudentEnrollment(
                student=student,
                classroom=classrooms[i % len(classrooms)],
                academic_year=ACADEMIC_YEAR,
                term=TERM,
                is_active=True,
            )
            for i, student in enumerate(students)
        ]
        # bulk_create is fine here — StudentEnrollment.clean() has no
        # cross-model checks of its own; validation lives on LearnerAssessmentResult.
        StudentEnrollment.objects.bulk_create(enrollment_instances)

        return students

    # ------------------------------------------------------------------
    # Step 4 – Subjects
    # ------------------------------------------------------------------

    def _create_subjects(self):
        self.stdout.write("Generating subjects...")
        return Subject.objects.bulk_create([
            Subject(name="Mathematics",        department="MATH"),
            Subject(name="Chemistry",          department="SCIENCES"),
            Subject(name="English",            department="LANGUAGES"),
            Subject(name="History & Government", department="HUMANITIES"),
            Subject(name="Agriculture",        department="TECHNICALS"),
        ])

    # ------------------------------------------------------------------
    # Step 5 – Allocations
    # ------------------------------------------------------------------

    def _create_allocations(self, classrooms, subjects, teachers):
        """
        Allocations now carry academic_year and term (added in the model
        update). unique_together is (classroom, subject, academic_year, term)
        so we assign 3 random subjects per classroom for the seeded year/term.
        """
        self.stdout.write("Allocating subjects to classrooms...")
        instances = []
        for room in classrooms:
            for sub in random.sample(list(subjects), k=3):
                instances.append(
                    ClassSubjectAllocation(
                        classroom=room,
                        subject=sub,
                        teacher=random.choice(teachers),
                        academic_year=ACADEMIC_YEAR,
                        term=TERM,
                        # formative_weight defaults to 70.00 per the model
                    )
                )
        return ClassSubjectAllocation.objects.bulk_create(instances)

    # ------------------------------------------------------------------
    # Step 6 – Assessment Tasks
    # ------------------------------------------------------------------

    def _create_tasks(self, allocations):
        """
        AssessmentTask no longer carries term or academic_year — those live
        on the allocation it points to. We bind the assigned teacher from the
        allocation to populate the evaluating_teacher field required by the views.
        """
        self.stdout.write("Creating assessment tasks...")
        task_templates = [
            ("Mid-Term Practical SBA",       "FORMATIVE",  40),
            ("Topic Portfolio Task",          "FORMATIVE",  20),
            ("Main End of Term Examination",  "SUMMATIVE", 100),
        ]
        instances = []
        for alloc in allocations:
            for title, task_type, max_points in task_templates:
                instances.append(
                    AssessmentTask(
                        allocation=alloc,
                        title=title,
                        task_type=task_type,
                        max_points=max_points,
                        evaluating_teacher=alloc.teacher,
                    )
                )
        return AssessmentTask.objects.bulk_create(instances)

    # ------------------------------------------------------------------
    # Step 7 – Results
    # ------------------------------------------------------------------

    def _create_results(self, allocations, tasks, students, classrooms):
        """
        Records results only for students enrolled in the classroom that
        each allocation belongs to, correctly reflecting the enrollment model.

        NOTE: bulk_create bypasses save() and therefore skips full_clean().
        The score ceiling and enrollment cross-checks in LearnerAssessmentResult
        are enforced manually here to keep seed data valid. Do not copy this
        bulk_create pattern into production write paths — use .save() there.
        """
        self.stdout.write("Logging learner assessment results...")

        # Build a lookup: classroom_id → list of enrolled students
        # Use the StudentEnrollment table as the source of truth.
        enrollment_map: dict[int, list] = {}
        for enrollment in StudentEnrollment.objects.filter(
            academic_year=ACADEMIC_YEAR, term=TERM, is_active=True
        ).select_related("student"):
            enrollment_map.setdefault(enrollment.classroom_id, []).append(enrollment.student)

        # Build a lookup: allocation_id → list of tasks
        task_map: dict[int, list] = {}
        for task in tasks:
            task_map.setdefault(task.allocation_id, []).append(task)

        result_instances = []
        for alloc in allocations:
            enrolled_students = enrollment_map.get(alloc.classroom_id, [])
            alloc_tasks = task_map.get(alloc.id, [])

            for student in enrolled_students:
                perf_factor = random.choice([0.85, 0.70, 0.55, 0.40])

                for task in alloc_tasks:
                    raw_score = task.max_points * perf_factor * random.uniform(0.8, 1.1)
                    # Manually enforce the score ceiling (mirrors LearnerAssessmentResult.clean)
                    score = Decimal(str(round(min(raw_score, task.max_points), 2)))

                    result_instances.append(
                        LearnerAssessmentResult(
                            student=student,
                            assessment_task=task,
                            score_achieved=score,
                            teacher_remarks=(
                                "Competency assessed and recorded during scheduled evaluation."
                            ),
                        )
                    )

        LearnerAssessmentResult.objects.bulk_create(result_instances, batch_size=500)
        self.stdout.write(f"  → {len(result_instances)} result rows written.")