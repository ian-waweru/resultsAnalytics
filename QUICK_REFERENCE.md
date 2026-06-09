# Database Optimization Quick Reference

## When Writing Queries

### ❌ DON'T Do This (N+1 Problems)

```python
# Problem: Query inside loop
results = LearnerAssessmentResult.objects.all()
for result in results:
    print(result.assessment_task.allocation.subject.name)  # Query per result!

# Problem: Counting in loop
for alloc in allocations:
    count = alloc.tasks.count()  # Query per allocation!

# Problem: Template filters
{% for student in students %}
    {{ student.results.count }}  <!-- Query per student! -->
{% endfor %}
```

### ✅ DO This (Optimized)

```python
# Solution: Use select_related for FK chains
results = LearnerAssessmentResult.objects.select_related(
    'assessment_task__allocation__subject'
)
for result in results:
    print(result.assessment_task.allocation.subject.name)  # No extra queries!

# Solution: Use annotate() for counts
allocations = ClassSubjectAllocation.objects.annotate(
    _task_count=Count('tasks', distinct=True)
)
for alloc in allocations:
    print(alloc._task_count)  # From annotation, no extra query!

# Solution: Annotate in view, not template
students = Student.objects.annotate(_result_count=Count('results'))
```

---

## Common Patterns

### Pattern 1: Foreign Key Chain Access
```python
# Get all allocations with full hierarchy
allocations = ClassSubjectAllocation.objects.select_related(
    'classroom__stream__pathway',  # FK chain
    'subject',
    'teacher'
)
```

### Pattern 2: Reverse Relation Access
```python
# Get students with their enrollments
students = Student.objects.prefetch_related(
    'enrollments__classroom__stream__pathway'
)
```

### Pattern 3: Counting Related Objects
```python
# Count tasks per allocation
allocations = ClassSubjectAllocation.objects.annotate(
    task_count=Count('tasks', distinct=True)
)
```

### Pattern 4: Filtering with Aggregation
```python
# Get allocations with at least 5 tasks
allocations = ClassSubjectAllocation.objects.annotate(
    task_count=Count('tasks', distinct=True)
).filter(task_count__gte=5)
```

### Pattern 5: Average Percentage Calculation
```python
from django.db.models import Avg, F, ExpressionWrapper, FloatField

results = LearnerAssessmentResult.objects.annotate(
    pct=ExpressionWrapper(
        F('score_achieved') * 100.0 / F('assessment_task__max_points'),
        output_field=FloatField()
    )
)
avg = results.aggregate(Avg('pct'))['pct']
```

---

## Index Naming Convention

All indexes follow the pattern: `idx_tablename_fields`

**Examples:**
- `idx_studentenrollment_year_term_active` - Composite index
- `idx_allocation_subject` - Single column index
- `idx_result_student_task` - Composite index for uniqueness

---

## Admin Class Template

```python
@admin.register(MyModel)
class MyModelAdmin(admin.ModelAdmin):
    list_display = ('field1', 'field2', 'custom_count')
    search_fields = ('field1',)
    
    @admin.display(description="Count")
    def custom_count(self, obj):
        # Use cached annotation if available
        if hasattr(obj, '_custom_count'):
            return obj._custom_count
        return obj.related.count()
    
    def get_queryset(self, request):
        # Always optimize here!
        qs = super().get_queryset(request)
        return qs.select_related(
            'related1',
            'related2'
        ).prefetch_related(
            'many_related'
        ).annotate(
            _custom_count=Count('related', distinct=True)
        )
```

---

## View Query Optimization Checklist

- [ ] Use `select_related()` for FK chains
- [ ] Use `prefetch_related()` for reverse relations
- [ ] Use `annotate()` for counts and aggregates
- [ ] Use `values()` for specific columns only
- [ ] Use `distinct=True` in Count() for joined tables
- [ ] Avoid querying inside loops
- [ ] Cache querysets in variables
- [ ] Test with Django Debug Toolbar

---

## Performance Testing

### Using Django Debug Toolbar
```bash
pip install django-debug-toolbar
```

Add to INSTALLED_APPS and MIDDLEWARE, then visit `/admin/` to see query count.

### Quick Query Count Check
```python
from django.db import connection
from django.test.utils import override_settings

@override_settings(DEBUG=True)
def my_view(request):
    # ... your code ...
    print(f"Queries: {len(connection.queries)}")
    for query in connection.queries:
        print(f"Time: {query['time']}s - {query['sql'][:100]}")
```

---

## When to Add Indexes

Add an index when:
- ✅ Field is used in filter conditions
- ✅ Field is used in ordering
- ✅ Field is part of a JOIN
- ✅ Field is frequently searched

Don't add when:
- ❌ Field is rarely filtered
- ❌ Table is very small (<1000 rows)
- ❌ Field has low cardinality (few unique values)

---

## Quick Wins for Existing Code

### 1. Add to Existing View
```python
# Before
models = MyModel.objects.all()

# After
models = MyModel.objects.select_related('related').prefetch_related('many')
```

### 2. Add to Existing Admin
```python
# In get_queryset()
def get_queryset(self, request):
    qs = super().get_queryset(request)
    return qs.select_related('field').annotate(_count=Count('items'))
```

### 3. Add to Manager
```python
def optimized(self):
    return self.select_related('related').prefetch_related('many')

# Usage
models = MyModel.objects.optimized()
```

---

## Common Mistakes

| ❌ | ✅ |
|---|---|
| `for obj in objs: obj.rel.count()` | `objs.annotate(count=Count('rel'))` |
| `objs = MyModel.objects.all()` | `objs = MyModel.objects.select_related(...)` |
| Multiple `.get()` calls | One `.select_related()` |
| `.all().count()` | `.count()` |
| `if obj.rel.exists():` in loop | `.annotate()` then check value |
| Deep prefetch chains | Limit to 2-3 levels |

---

## Debug Commands

```bash
# Check for N+1 in test
python manage.py test --debug-sql

# SQL analysis
python manage.py shell
>>> from django.db import connection
>>> from django.test.utils import override_settings
>>> # run code
>>> print(len(connection.queries))
```

---

## Key Database Indexes

**Most Important:**
1. `idx_studentenrollment_year_term_active` - Dashboard filters
2. `idx_allocation_teacher_year_term` - Teacher dashboard
3. `idx_result_student_task` - Result lookups

---

## Related Resources

- Full guide: [DATABASE_OPTIMIZATION.md](DATABASE_OPTIMIZATION.md)
- Summary: [OPTIMIZATION_SUMMARY.md](OPTIMIZATION_SUMMARY.md)
- Django docs: https://docs.djangoproject.com/en/6.0/topics/db/optimization/

---

**Last Updated:** June 9, 2026  
**Version:** 1.0
