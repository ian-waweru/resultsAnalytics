"""
school/management/commands/seed_db.py

Seeds the database with realistic Kenyan CBC Senior Secondary School data.

Usage
-----
    # Seed everything from scratch (default: current year, all 3 terms)
    python manage.py seed_db

    # Seed a specific year and terms only
    python manage.py seed_db --year 2025 --terms 2,3

    # Wipe existing data first, then seed
    python manage.py seed_db --flush

    # Full reset: flush + seed all three terms for 2025 and 2026
    python manage.py seed_db --flush --year 2025 --terms 1,2,3
    python manage.py seed_db --year 2026 --terms 1,2,3

Dependencies
------------
    pip install faker

Place this file at:
    <your_app>/management/commands/seed_db.py

Ensure the management package structure exists:
    <your_app>/management/__init__.py
    <your_app>/management/commands/__init__.py
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from faker import Faker

from school.models import (
    AssessmentTask,
    ClassSubjectAllocation,
    Classroom,
    LearnerAssessmentResult,
    Pathway,
    Stream,
    Student,
    StudentEnrollment,
    StudentSubjectSelection,
    Subject,
    Teacher,
)

fake = Faker("en_GB")   # British English gives realistic but non-US names/dates
fake_ke = Faker()        # fallback for anything not locale-specific
random.seed(42)


# ---------------------------------------------------------------------------
# Static reference data — mirrors the KICD curriculum structure
# ---------------------------------------------------------------------------

PATHWAYS = [
    {
        "code": "STEM",
        "name": "Science, Technology, Engineering & Mathematics",
        "description": "Focuses on sciences and technical subjects.",
    },
    {
        "code": "SS",
        "name": "Social Sciences",
        "description": "Focuses on humanities, business, and social studies.",
    },
    {
        "code": "ASS",
        "name": "Arts & Sports Science",
        "description": "Focuses on creative arts, performing arts, and sports.",
    },
    {
        "code": "GENERAL",
        "name": "Junior Secondary / Lower Level Base",
        "description": "General base for junior and lower secondary levels.",
    },
]

# (grade_name, pathway_code, sections)
STREAMS_CONFIG = [
    ("Grade 10", "STEM",    ["East", "West", "North"]),
    ("Grade 10", "SS",      ["East", "West"]),
    ("Grade 10", "ASS",     ["East"]),
    ("Grade 11", "STEM",    ["East", "West"]),
    ("Grade 11", "SS",      ["East", "West"]),
    ("Grade 11", "ASS",     ["East"]),
    ("Grade 12", "STEM",    ["East", "West"]),
    ("Grade 12", "SS",      ["East"]),
    ("Grade 12", "ASS",     ["East"]),
]

# (name, code, learning_area, category, [pathway_codes])
SUBJECTS = [
    # Core — all pathways
    ("English",                  "ENG",    "LANG",         "CORE",     []),
    ("Kiswahili",                "KSW",    "LANG",         "CORE",     []),
    ("Community Service Learning","CSL",   "CSL",          "CORE",     []),
    ("Physical Education",       "PE",     "PE",           "CORE",     []),
    ("Life Skills Education",    "LIFE",   "LIFE",         "CORE",     []),
    ("Religious Education",      "RE",     "RE",           "CORE",     []),
    # STEM electives
    ("Mathematics",              "MATH",   "MATH",         "ELECTIVE", ["STEM"]),
    ("Biology",                  "BIO",    "BIO",          "ELECTIVE", ["STEM"]),
    ("Chemistry",                "CHEM",   "CHEM",         "ELECTIVE", ["STEM"]),
    ("Physics",                  "PHY",    "PHY",          "ELECTIVE", ["STEM"]),
    ("Computer Science",         "CS",     "CS",           "ELECTIVE", ["STEM"]),
    ("Agriculture & Nutrition",  "AGRI",   "AGRI",         "ELECTIVE", ["STEM"]),
    ("Technical & Engineering",  "TECH",   "TECH",         "ELECTIVE", ["STEM"]),
    # Social Sciences electives
    ("History & Citizenship",    "HIST",   "HIST",         "ELECTIVE", ["SS"]),
    ("Geography",                "GEO",    "GEO",          "ELECTIVE", ["SS"]),
    ("Business Studies",         "BUS",    "BUS",          "ELECTIVE", ["SS"]),
    ("Economics",                "ECON",   "ECON",         "ELECTIVE", ["SS"]),
    ("French",                   "FRE",    "FOREIGN_LANG", "ELECTIVE", ["SS"]),
    ("German",                   "GER",    "FOREIGN_LANG", "ELECTIVE", ["SS"]),
    # Arts & Sports Science electives
    ("Fine Art & Design",        "ART",    "ART",          "ELECTIVE", ["ASS"]),
    ("Performing Arts",          "PERF",   "PERF",         "ELECTIVE", ["ASS"]),
    ("Sports Science",           "SPORT",  "SPORT",        "ELECTIVE", ["ASS"]),
    ("Home Science",             "HOME",   "HOME",         "ELECTIVE", ["ASS"]),
    ("Media & Film Technology",  "MEDIA",  "MEDIA",        "ELECTIVE", ["ASS"]),
    ("Fashion & Design",         "FASH",   "FASHION",      "ELECTIVE", ["ASS"]),
]

# Electives offered per pathway (students pick 3–4)
PATHWAY_ELECTIVES = {
    "STEM": ["MATH", "BIO", "CHEM", "PHY", "CS", "AGRI", "TECH"],
    "SS":   ["HIST", "GEO", "BUS",  "ECON", "FRE", "GER"],
    "ASS":  ["ART",  "PERF","SPORT","HOME", "MEDIA", "FASH"],
}

# Core subject codes taught in every classroom
CORE_CODES = ["ENG", "KSW", "CSL", "PE", "LIFE", "RE"]

# Realistic Kenyan teacher surnames / first names
KE_FIRST_NAMES = [
    "Joyce", "Amina", "Wanjiru", "Achieng", "Fatuma", "Njeri", "Adhiambo",
    "Zawadi", "Mwanaidi", "Rehema", "James", "Peter", "Samuel", "David",
    "John", "Joseph", "Daniel", "Michael", "Charles", "Patrick",
    "Kevin", "Brian", "Dennis", "George", "Simon", "Robert", "Paul",
]
KE_LAST_NAMES = [
    "Otieno", "Kamau", "Odhiambo", "Mwangi", "Kipchoge", "Waweru",
    "Njoroge", "Ochieng", "Muriithi", "Auma", "Chebet", "Rono",
    "Mutua", "Kibet", "Koech", "Ngoiri", "Adhiambo", "Wangari",
    "Omari", "Kariuki", "Gitau", "Mugo", "Ndung'u", "Kimani", "Mbeki",
]
KE_STUDENT_SURNAMES = KE_LAST_NAMES + [
    "Lumumba", "Odinga", "Kenyatta", "Muliro", "Oginga", "Gacheru",
    "Nyambura", "Wafula", "Simiyu", "Barasa", "Namwamba", "Wesonga",
]

# Task title templates per term
TASK_TITLES = {
    1: {
        "FORMATIVE": [
            "Opening Diagnostic",
            "SBA Task 1 – Written Report",
            "SBA Task 2 – Practical Work",
            "SBA Task 3 – Group Project",
            "Mid-Strand Assessment",
            "Competency Check",
        ],
        "SUMMATIVE": [
            "Term 1 End-of-Term Exam",
            "Cumulative Paper 1",
        ],
    },
    2: {
        "FORMATIVE": [
            "SBA Task 1 – Essay Writing",
            "SBA Task 2 – Practical Work",
            "SBA Task 3 – Group Project",
            "SBA Task 4 – Oral Presentation",
            "Mid-Strand Assessment",
            "Reflective Journal Review",
        ],
        "SUMMATIVE": [
            "Term 2 End-of-Term Exam",
            "Cumulative Paper 2",
        ],
    },
    3: {
        "FORMATIVE": [
            "SBA Task 1 – Research Portfolio",
            "SBA Task 2 – Field Assignment",
            "SBA Task 3 – Case Study Analysis",
            "SBA Task 4 – Lab Work",
            "End-of-Strand Assessment",
            "Competency Verification",
        ],
        "SUMMATIVE": [
            "Term 3 End-of-Term Exam",
            "End-of-Strand Examination",
        ],
    },
}

TEACHER_REMARKS = [
    "Good effort shown.",
    "Shows strong competency.",
    "Excellent application of concepts.",
    "Needs improvement in key areas.",
    "Demonstrates satisfactory understanding.",
    "Outstanding performance.",
    "Progressing well.",
    "Requires more practice.",
    "Meets expectations for this level.",
    "",
]

# Term calendar windows (month, day)
TERM_WINDOWS = {
    1: {"start": (1, 6),  "end": (3, 31)},
    2: {"start": (5, 5),  "end": (7, 31)},
    3: {"start": (9, 8),  "end": (11, 28)},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ke_full_name() -> str:
    return f"{random.choice(KE_FIRST_NAMES)} {random.choice(KE_LAST_NAMES)}"


def _ke_student_name() -> str:
    return f"{random.choice(KE_FIRST_NAMES)} {random.choice(KE_STUDENT_SURNAMES)}"


def _term_date(year: int, term: int, offset_days: int = 0) -> date:
    """Returns the term start date + offset, capped at term end."""
    w = TERM_WINDOWS[term]
    start = date(year, *w["start"]) + timedelta(days=offset_days)
    end = date(year, *w["end"])
    return min(start, end)


def _random_date_in_term(year: int, term: int) -> date:
    w = TERM_WINDOWS[term]
    start = date(year, *w["start"])
    end = date(year, *w["end"])
    return start + timedelta(days=random.randint(0, (end - start).days))


def _gen_score(max_points: int) -> Decimal:
    """Normally distributed score, biased toward passing (mean ~62%)."""
    pct = max(0.0, min(100.0, random.gauss(62, 18)))
    return Decimal(str(round(pct / 100 * max_points, 2)))


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Seed the database with realistic CBC school data using Faker. "
        "Safe to run multiple times — skips records that already exist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=date.today().year,
            help="Academic year to seed (default: current year).",
        )
        parser.add_argument(
            "--terms",
            type=str,
            default="1,2,3",
            help="Comma-separated list of terms to seed, e.g. '2,3' (default: 1,2,3).",
        )
        parser.add_argument(
            "--students",
            type=int,
            default=693,
            help="Total number of students to create (default: 693).",
        )
        parser.add_argument(
            "--teachers",
            type=int,
            default=30,
            help="Number of teachers to create (default: 30).",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing school data before seeding.",
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        year: int = options["year"]
        terms: list[int] = [int(t.strip()) for t in options["terms"].split(",")]
        n_students: int = options["students"]
        n_teachers: int = options["teachers"]

        for t in terms:
            if t not in (1, 2, 3):
                raise CommandError(f"Invalid term '{t}'. Must be 1, 2, or 3.")

        if options["flush"]:
            self._flush()

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nSeeding {year} — Term(s): {terms} | "
                f"Students: {n_students} | Teachers: {n_teachers}\n"
            )
        )

        with transaction.atomic():
            pathways   = self._seed_pathways()
            subjects   = self._seed_subjects(pathways)
            streams    = self._seed_streams(pathways)
            classrooms = self._seed_classrooms(streams)
            teachers   = self._seed_teachers(n_teachers)
            students   = self._seed_students(n_students)

            for term in terms:
                self.stdout.write(f"\n  → Term {term} …")
                enrollments = self._seed_enrollments(students, classrooms, year, term)
                allocs      = self._seed_allocations(classrooms, subjects, teachers, year, term)
                self._seed_subject_selections(students, pathways, subjects, year, streams)
                self._seed_tasks_and_results(allocs, enrollments, teachers, year, term)

        self.stdout.write(self.style.SUCCESS("\n✓ Seeding complete.\n"))

    # ------------------------------------------------------------------
    # Flush
    # ------------------------------------------------------------------

    def _flush(self):
        self.stdout.write(self.style.WARNING("  Flushing existing school data …"))
        LearnerAssessmentResult.objects.all().delete()
        AssessmentTask.objects.all().delete()
        ClassSubjectAllocation.objects.all().delete()
        StudentSubjectSelection.objects.all().delete()
        StudentEnrollment.objects.all().delete()
        Student.objects.all().delete()
        Teacher.objects.all().delete()
        Classroom.objects.all().delete()
        Stream.objects.all().delete()
        Subject.objects.all().delete()
        Pathway.objects.all().delete()
        self.stdout.write(self.style.WARNING("  Done.\n"))

    # ------------------------------------------------------------------
    # Pathways
    # ------------------------------------------------------------------

    def _seed_pathways(self) -> dict[str, Pathway]:
        self.stdout.write("  Pathways …", ending=" ")
        objs = {}
        for p in PATHWAYS:
            obj, created = Pathway.objects.get_or_create(
                code=p["code"],
                defaults={"name": p["name"], "description": p["description"]},
            )
            objs[p["code"]] = obj
        self.stdout.write(self.style.SUCCESS(f"{len(objs)} pathways ready."))
        return objs

    # ------------------------------------------------------------------
    # Subjects
    # ------------------------------------------------------------------

    def _seed_subjects(self, pathways: dict) -> dict[str, Subject]:
        self.stdout.write("  Subjects …", ending=" ")
        objs = {}
        for name, code, area, category, pw_codes in SUBJECTS:
            obj, _ = Subject.objects.get_or_create(
                name=name,
                learning_area=area,
                defaults={
                    "code": code,
                    "category": category,
                },
            )
            # Set M2M pathways (idempotent — set() replaces)
            if pw_codes:
                obj.pathways.set([pathways[c] for c in pw_codes])
            objs[code] = obj
        self.stdout.write(self.style.SUCCESS(f"{len(objs)} subjects ready."))
        return objs

    # ------------------------------------------------------------------
    # Streams & Classrooms
    # ------------------------------------------------------------------

    def _seed_streams(self, pathways: dict) -> list[Stream]:
        self.stdout.write("  Streams …", ending=" ")
        objs = []
        for grade, pw_code, _ in STREAMS_CONFIG:
            obj, _ = Stream.objects.get_or_create(
                name=grade,
                pathway=pathways[pw_code],
            )
            objs.append(obj)
        self.stdout.write(self.style.SUCCESS(f"{len(objs)} streams ready."))
        return objs

    def _seed_classrooms(self, streams: list[Stream]) -> list[Classroom]:
        self.stdout.write("  Classrooms …", ending=" ")
        objs = []
        for stream, (_, _, sections) in zip(streams, STREAMS_CONFIG):
            for section in sections:
                obj, _ = Classroom.objects.get_or_create(
                    name=section,
                    stream=stream,
                )
                objs.append(obj)
        self.stdout.write(self.style.SUCCESS(f"{len(objs)} classrooms ready."))
        return objs

    # ------------------------------------------------------------------
    # Teachers
    # ------------------------------------------------------------------

    def _seed_teachers(self, n: int) -> list[Teacher]:
        self.stdout.write("  Teachers …", ending=" ")
        existing = list(Teacher.objects.all())
        if len(existing) >= n:
            self.stdout.write(self.style.SUCCESS(f"{len(existing)} already exist."))
            return existing

        to_create = n - len(existing)
        hashed_pw = make_password("school@2025!")

        bulk = []
        for i in range(len(existing) + 1, len(existing) + to_create + 1):
            full_name = _ke_full_name()
            username = f"teacher{i:03d}"
            is_hod = (i % 10 == 1)
            tsc = f"TSC{random.randint(100000, 999999)}" if random.random() > 0.15 else None
            bulk.append(
                Teacher(
                    username=username,
                    password=hashed_pw,
                    email=f"{username}@school.ac.ke",
                    full_name=full_name,
                    tsc_number=tsc,
                    is_hod=is_hod,
                    is_staff=False,
                    is_active=True,
                    is_superuser=False,
                    date_joined=fake.date_time_between(
                        start_date="-6y", end_date="-1y"
                    ),
                )
            )
        Teacher.objects.bulk_create(bulk, ignore_conflicts=True)
        all_teachers = list(Teacher.objects.all())
        self.stdout.write(self.style.SUCCESS(f"{len(all_teachers)} teachers ready."))
        return all_teachers

    # ------------------------------------------------------------------
    # Students
    # ------------------------------------------------------------------

    def _seed_students(self, n: int) -> list[Student]:
        self.stdout.write("  Students …", ending=" ")
        existing = list(Student.objects.all())
        if len(existing) >= n:
            self.stdout.write(self.style.SUCCESS(f"{len(existing)} already exist."))
            return existing

        to_create = n - len(existing)
        existing_adm = set(Student.objects.values_list("admission_number", flat=True))

        bulk = []
        while len(bulk) < to_create:
            adm = f"ADM{random.randint(10000, 99999)}"
            if adm in existing_adm:
                continue
            existing_adm.add(adm)
            dob = fake.date_of_birth(minimum_age=14, maximum_age=19)
            bulk.append(
                Student(
                    name=_ke_student_name(),
                    admission_number=adm,
                    date_of_birth=dob,
                )
            )

        Student.objects.bulk_create(bulk, ignore_conflicts=True)
        all_students = list(Student.objects.all())
        self.stdout.write(self.style.SUCCESS(f"{len(all_students)} students ready."))
        return all_students

    # ------------------------------------------------------------------
    # Enrollments
    # ------------------------------------------------------------------

    def _seed_enrollments(
        self,
        students: list[Student],
        classrooms: list[Classroom],
        year: int,
        term: int,
    ) -> dict[int, list[int]]:
        """
        Distribute students evenly across classrooms for the given year/term.
        Returns {classroom_id: [student_id, ...]} for downstream use.
        """
        # Check what already exists for this year/term
        existing = set(
            StudentEnrollment.objects.filter(academic_year=year, term=term)
            .values_list("student_id", "classroom_id")
        )
        if existing:
            # Rebuild map from existing records
            classroom_students: dict[int, list[int]] = {}
            for se in StudentEnrollment.objects.filter(academic_year=year, term=term):
                classroom_students.setdefault(se.classroom_id, []).append(se.student_id)
            self.stdout.write(
                f"    Enrollments {year} T{term}: "
                + self.style.SUCCESS(f"{len(existing)} already exist — skipping.")
            )
            return classroom_students

        enroll_date = _term_date(year, term)
        n = len(classrooms)
        chunks = [students[i::n] for i in range(n)]  # round-robin distribution

        classroom_students: dict[int, list[int]] = {}
        bulk = []
        for classroom, chunk in zip(classrooms, chunks):
            classroom_students[classroom.pk] = [s.pk for s in chunk]
            for student in chunk:
                bulk.append(
                    StudentEnrollment(
                        student=student,
                        classroom=classroom,
                        academic_year=year,
                        term=term,
                        is_active=True,
                        enrolled_on=enroll_date,
                    )
                )

        StudentEnrollment.objects.bulk_create(bulk, ignore_conflicts=True)
        self.stdout.write(
            f"    Enrollments {year} T{term}: "
            + self.style.SUCCESS(f"{len(bulk)} created.")
        )
        return classroom_students

    # ------------------------------------------------------------------
    # Subject selections
    # ------------------------------------------------------------------

    def _seed_subject_selections(
        self,
        students: list[Student],
        pathways: dict[str, Pathway],
        subjects: dict[str, Subject],
        year: int,
        streams: list[Stream],
    ):
        """Each student gets one pathway selection per year with 3–4 electives."""
        grade_map = {"Grade 10": 10, "Grade 11": 11, "Grade 12": 12}

        existing_keys = set(
            StudentSubjectSelection.objects.filter(academic_year=year)
            .values_list("student_id", "grade")
        )
        if len(existing_keys) >= len(students):
            return  # already seeded

        pathway_codes = ["STEM", "SS", "ASS"]
        bulk_selections = []
        m2m_data = []  # (selection_obj, elective_codes)

        for student in students:
            # Assign a grade based on admission number (deterministic spread)
            grade = random.choice([10, 11, 12])
            if (student.pk, grade) in existing_keys:
                continue
            pw_code = random.choice(pathway_codes)
            pathway = pathways[pw_code]
            elective_codes = random.sample(PATHWAY_ELECTIVES[pw_code], k=random.choice([3, 4]))

            sel = StudentSubjectSelection(
                student=student,
                pathway=pathway,
                academic_year=year,
                grade=grade,
                is_approved=True,
            )
            bulk_selections.append(sel)
            m2m_data.append((sel, elective_codes))

        # bulk_create doesn't return PKs reliably with M2M, so save individually
        created = 0
        for sel, elective_codes in m2m_data:
            try:
                sel.save()
                sel.elective_subjects.set(
                    [subjects[c] for c in elective_codes if c in subjects]
                )
                created += 1
            except Exception:
                pass  # duplicate — skip

    # ------------------------------------------------------------------
    # Class–Subject Allocations
    # ------------------------------------------------------------------

    def _seed_allocations(
        self,
        classrooms: list[Classroom],
        subjects: dict[str, Subject],
        teachers: list[Teacher],
        year: int,
        term: int,
    ) -> list[ClassSubjectAllocation]:
        """
        Assign core + pathway-appropriate electives to each classroom,
        each with a designated teacher.
        """
        existing = list(
            ClassSubjectAllocation.objects.filter(academic_year=year, term=term)
            .select_related("classroom", "subject", "teacher")
        )
        if existing:
            self.stdout.write(
                f"    Allocations {year} T{term}: "
                + self.style.SUCCESS(f"{len(existing)} already exist — skipping.")
            )
            return existing

        teacher_cycle = teachers.copy()
        random.shuffle(teacher_cycle)
        teacher_idx = 0

        def next_teacher() -> Teacher:
            nonlocal teacher_idx
            t = teacher_cycle[teacher_idx % len(teacher_cycle)]
            teacher_idx += 1
            return t

        bulk = []
        for classroom in classrooms:
            pathway = classroom.stream.pathway
            pw_code = pathway.code if pathway else "GENERAL"

            # Core subjects for everyone
            subject_codes = list(CORE_CODES)
            # Add pathway electives
            if pw_code in PATHWAY_ELECTIVES:
                subject_codes += PATHWAY_ELECTIVES[pw_code]

            for code in subject_codes:
                if code not in subjects:
                    continue
                bulk.append(
                    ClassSubjectAllocation(
                        classroom=classroom,
                        subject=subjects[code],
                        teacher=next_teacher(),
                        academic_year=year,
                        term=term,
                        formative_weight=Decimal("70.00"),
                    )
                )

        ClassSubjectAllocation.objects.bulk_create(bulk, ignore_conflicts=True)
        allocs = list(
            ClassSubjectAllocation.objects.filter(academic_year=year, term=term)
        )
        self.stdout.write(
            f"    Allocations {year} T{term}: "
            + self.style.SUCCESS(f"{len(allocs)} created.")
        )
        return allocs

    # ------------------------------------------------------------------
    # Assessment Tasks + Results
    # ------------------------------------------------------------------

    def _seed_tasks_and_results(
        self,
        allocs: list[ClassSubjectAllocation],
        classroom_students: dict[int, list[int]],
        teachers: list[Teacher],
        year: int,
        term: int,
    ):
        """
        For each allocation: create 1–2 formative tasks + 1 summative task,
        then record a LearnerAssessmentResult for every enrolled student.
        """
        existing_task_alloc_ids = set(
            AssessmentTask.objects.filter(
                allocation__academic_year=year, allocation__term=term
            ).values_list("allocation_id", flat=True)
        )

        task_bulk = []
        result_bulk = []
        max_points_choices = [30, 40, 50, 60, 100]

        for alloc in allocs:
            if alloc.pk in existing_task_alloc_ids:
                continue

            students_in_class = classroom_students.get(alloc.classroom_id, [])
            if not students_in_class:
                continue

            # Build task list: 1–2 formative + 1 summative
            num_formative = random.choice([1, 1, 2])
            f_titles = random.sample(TASK_TITLES[term]["FORMATIVE"], k=num_formative)
            s_title  = random.choice(TASK_TITLES[term]["SUMMATIVE"])

            tasks_spec = [(t, "FORMATIVE") for t in f_titles] + [(s_title, "SUMMATIVE")]

            for title, task_type in tasks_spec:
                max_pts = random.choice(max_points_choices)
                task_date = _random_date_in_term(year, term)

                task = AssessmentTask(
                    allocation=alloc,
                    title=title,
                    task_type=task_type,
                    max_points=max_pts,
                    date_administered=task_date,
                    evaluating_teacher=alloc.teacher,
                )
                task_bulk.append(task)

        # Bulk-create tasks to get PKs, then create results
        created_tasks = AssessmentTask.objects.bulk_create(task_bulk)

        # For each task, generate results for all enrolled students
        # Re-fetch with allocation info to access classroom_id
        task_ids = [t.pk for t in created_tasks if t.pk]
        tasks_with_alloc = AssessmentTask.objects.filter(
            pk__in=task_ids
        ).select_related("allocation")

        for task in tasks_with_alloc:
            students_in_class = classroom_students.get(task.allocation.classroom_id, [])
            for student_id in students_in_class:
                score = _gen_score(task.max_points)
                record_date = _random_date_in_term(year, term).isoformat()
                result_bulk.append(
                    LearnerAssessmentResult(
                        student_id=student_id,
                        assessment_task=task,
                        score_achieved=score,
                        teacher_remarks=random.choice(TEACHER_REMARKS),
                        recorded_at=f"{record_date}T10:00:00Z",
                        last_modified_at=f"{record_date}T10:00:00Z",
                    )
                )

        # bulk_create in chunks to avoid hitting SQLite/Postgres param limits
        chunk_size = 2000
        for i in range(0, len(result_bulk), chunk_size):
            LearnerAssessmentResult.objects.bulk_create(
                result_bulk[i : i + chunk_size], ignore_conflicts=True
            )

        self.stdout.write(
            f"    Tasks {year} T{term}:   "
            + self.style.SUCCESS(f"{len(task_bulk)} created.")
        )
        self.stdout.write(
            f"    Results {year} T{term}: "
            + self.style.SUCCESS(f"{len(result_bulk)} created.")
        )