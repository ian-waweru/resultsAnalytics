from django.utils import timezone

def get_current_academic_context(request):
    """
    Central utility for academic year and term.
    Priority: URL params > Session > Current year
    """
    current_year = timezone.now().year

    year = request.GET.get('year') or request.session.get('academic_year')
    term = request.GET.get('term') or request.session.get('academic_term')

    try:
        academic_year = int(year) if year else current_year
    except (ValueError, TypeError):
        academic_year = current_year

    try:
        academic_term = int(term) if term else 1
        if academic_term not in [1, 2, 3]:
            academic_term = 1
    except (ValueError, TypeError):
        academic_term = 1

    # Attach to request for easy use in views
    request.academic_year = academic_year
    request.academic_term = academic_term

    # Save to session
    request.session['academic_year'] = academic_year
    request.session['academic_term'] = academic_term

    return {
        'academic_year': academic_year,
        'academic_term': academic_term,
    }