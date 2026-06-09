# Generated migration for database performance optimization
# Adds composite and single-column indexes on frequently queried and filtered fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0001_initial'),
    ]

    operations = [
        # ========================================================================
        # StudentEnrollment indexes
        # ========================================================================
        # High-traffic composite index: most StudentEnrollment queries filter by these
        migrations.AddIndex(
            model_name='studentenrollment',
            index=models.Index(
                fields=['academic_year', 'term', 'is_active'],
                name='idx_studentenrollment_year_term_active',
            ),
        ),
        # Single column index for filtering by classroom
        migrations.AddIndex(
            model_name='studentenrollment',
            index=models.Index(
                fields=['classroom'],
                name='idx_studentenrollment_classroom',
            ),
        ),
        # Single column index for filtering by student
        migrations.AddIndex(
            model_name='studentenrollment',
            index=models.Index(
                fields=['student'],
                name='idx_studentenrollment_student',
            ),
        ),

        # ========================================================================
        # ClassSubjectAllocation indexes
        # ========================================================================
        # High-traffic composite index: allocations are frequently queried by teacher, year, and term
        migrations.AddIndex(
            model_name='classsubjectallocation',
            index=models.Index(
                fields=['teacher', 'academic_year', 'term'],
                name='idx_allocation_teacher_year_term',
            ),
        ),
        # Composite index for classroom-based queries
        migrations.AddIndex(
            model_name='classsubjectallocation',
            index=models.Index(
                fields=['classroom', 'academic_year', 'term'],
                name='idx_allocation_classroom_year_term',
            ),
        ),
        # Single column index for subject queries
        migrations.AddIndex(
            model_name='classsubjectallocation',
            index=models.Index(
                fields=['subject'],
                name='idx_allocation_subject',
            ),
        ),

        # ========================================================================
        # AssessmentTask indexes
        # ========================================================================
        # Composite index for allocation-based task queries
        migrations.AddIndex(
            model_name='assessmenttask',
            index=models.Index(
                fields=['allocation', 'task_type'],
                name='idx_task_allocation_type',
            ),
        ),
        # Index for date-based queries
        migrations.AddIndex(
            model_name='assessmenttask',
            index=models.Index(
                fields=['date_administered'],
                name='idx_task_date_administered',
            ),
        ),

        # ========================================================================
        # LearnerAssessmentResult indexes
        # ========================================================================
        # Critical composite index: results are heavily queried by student and task
        migrations.AddIndex(
            model_name='learnerassessmentresult',
            index=models.Index(
                fields=['student', 'assessment_task'],
                name='idx_result_student_task',
            ),
        ),
        # Index for date-range queries on audit trail
        migrations.AddIndex(
            model_name='learnerassessmentresult',
            index=models.Index(
                fields=['recorded_at'],
                name='idx_result_recorded_at',
            ),
        ),
        # Index for score range queries and filtering
        migrations.AddIndex(
            model_name='learnerassessmentresult',
            index=models.Index(
                fields=['assessment_task'],
                name='idx_result_assessment_task',
            ),
        ),

        # ========================================================================
        # StudentSubjectSelection indexes
        # ========================================================================
        # Composite index for selection lookups by student, year, and grade
        migrations.AddIndex(
            model_name='studentsubjectselection',
            index=models.Index(
                fields=['student', 'academic_year', 'grade'],
                name='idx_selection_student_year_grade',
            ),
        ),
        # Index for pathway-based filtering
        migrations.AddIndex(
            model_name='studentsubjectselection',
            index=models.Index(
                fields=['pathway'],
                name='idx_selection_pathway',
            ),
        ),
        # Index for approval status filtering
        migrations.AddIndex(
            model_name='studentsubjectselection',
            index=models.Index(
                fields=['is_approved'],
                name='idx_selection_is_approved',
            ),
        ),

        # ========================================================================
        # Stream and Classroom indexes
        # ========================================================================
        # Index for pathway-based stream queries
        migrations.AddIndex(
            model_name='stream',
            index=models.Index(
                fields=['pathway'],
                name='idx_stream_pathway',
            ),
        ),
        # Index for stream-based classroom queries
        migrations.AddIndex(
            model_name='classroom',
            index=models.Index(
                fields=['stream'],
                name='idx_classroom_stream',
            ),
        ),

        # ========================================================================
        # Teacher indexes
        # ========================================================================
        # Indexes for HOD and active status filtering
        migrations.AddIndex(
            model_name='teacher',
            index=models.Index(
                fields=['is_hod', 'is_active'],
                name='idx_teacher_hod_active',
            ),
        ),
        # Index for TSC number lookups
        migrations.AddIndex(
            model_name='teacher',
            index=models.Index(
                fields=['tsc_number'],
                name='idx_teacher_tsc_number',
            ),
        ),

        # ========================================================================
        # Subject indexes
        # ========================================================================
        # Index for category filtering (core vs elective)
        migrations.AddIndex(
            model_name='subject',
            index=models.Index(
                fields=['category'],
                name='idx_subject_category',
            ),
        ),
        # Index for learning area filtering
        migrations.AddIndex(
            model_name='subject',
            index=models.Index(
                fields=['learning_area'],
                name='idx_subject_learning_area',
            ),
        ),
    ]
