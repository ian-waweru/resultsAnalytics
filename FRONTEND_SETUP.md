# Frontend Templates Setup Guide

## Overview
This guide documents the new Tailwind CSS-based frontend templates for the CBC School Analytics project.

## Files Created

### 1. **base.html** - Main Template Layout
**Location:** `school/templates/base.html`

The master template that all other templates extend. Features:
- Responsive navigation bar with user authentication dropdown
- Message/alert display system (success, error, warning, info)
- Footer with quick links and contact information
- Sticky header navigation
- Full page layout with container constraints

**Key Components:**
- Logo and branding
- Navigation links (Dashboard, Allocations, Tasks, Results)
- User dropdown menu with Profile, Change Password, Admin links
- Logout functionality
- Django messages framework integration
- Mobile-responsive design

**Template Tags Used:**
- `{% load static %}` - For CSS files
- `{% url %}` - URL reversing
- `{% if user.is_authenticated %}` - Conditional rendering
- `{{ user.get_full_name }}` - User information

---

### 2. **login.html** - User Login Page
**Location:** `school/templates/login.html`

Custom login form with modern design. Features:
- Centered login card
- Username/Password fields with icons
- Error message display for failed logins
- "Remember me" checkbox
- Password reset link (placeholder)
- Help section with contact information
- Feature highlights (Analytics, Collaboration, Reports)
- Smooth animations and transitions

**Form Features:**
- CSRF protection with Django forms
- Error field highlighting
- Inline validation feedback
- Focus states with visual feedback
- Mobile-responsive design

---

### 3. **style.css** - Custom Styles
**Location:** `school/static/css/style.css`

Custom Tailwind CSS extensions including:
- CSS variables for consistent colors
- Alert message styles (success, error, warning, info)
- Form element styling and focus states
- Button animations and states
- Badge component styles
- Card component styles
- Table styles with hover effects
- Statistics widget styles
- Animation keyframes (slideIn, fadeIn, pulse)
- Print styles for report generation
- Custom scrollbar styling

---

## Styling Framework

### Tailwind CSS
All templates use **Tailwind CSS v3** (via CDN):
```html
<script src="https://cdn.tailwindcss.com"></script>
```

### Color Scheme
- **Primary:** Blue (#2563eb)
- **Secondary:** Indigo (#4f46e5)
- **Success:** Green (#10b981)
- **Warning:** Yellow (#f59e0b)
- **Danger:** Red (#ef4444)
- **Light Gray:** #f3f4f6
- **Dark Gray:** #1f2937

### Design Features
- Rounded corners (lg, xl)
- Soft shadows for depth
- Smooth transitions (200ms)
- Gradient backgrounds
- Hover states on interactive elements
- Mobile-first responsive design

---

## Configuration Updates

### Django Settings (`settings.py`)
```python
# Template directories
TEMPLATES = [{
    'DIRS': [BASE_DIR / 'school' / 'templates'],
    ...
}]

# Authentication URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Static files
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
```

### URL Configuration (`school/urls.py`)
```python
from django.contrib.auth.views import LoginView, LogoutView

urlpatterns = [
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('dashboard/', views.cbc_school_dashboard, name='dashboard'),
]
```

---

## Directory Structure

```
/workspaces/resultsAnalytics/
├── school/
│   ├── templates/
│   │   ├── base.html           # Master template
│   │   └── login.html          # Login page
│   ├── static/
│   │   └── css/
│   │       └── style.css       # Custom styles
│   ├── views.py                # Dashboard view
│   └── urls.py                 # URL routing
├── static/                     # Root static directory
├── resultsAnalytics/
│   ├── settings.py            # Updated with template/static config
│   ├── urls.py                # Updated with root redirect
│   └── wsgi.py
└── manage.py
```

---

## Usage

### Extending base.html
```django
{% extends 'base.html' %}
{% load static %}

{% block title %}Page Title{% endblock %}

{% block content %}
  <!-- Your page content here -->
{% endblock %}

{% block extra_css %}
  <!-- Additional CSS if needed -->
{% endblock %}

{% block extra_js %}
  <!-- Additional JavaScript if needed -->
{% endblock %}
```

### Using Messages Framework
```python
from django.contrib import messages

# In your view
messages.success(request, 'Action completed successfully!')
messages.error(request, 'An error occurred!')
messages.warning(request, 'Warning message')
messages.info(request, 'Informational message')
```

### Login Required Decorator
```python
from django.contrib.auth.decorators import login_required

@login_required
def dashboard(request):
    # Only authenticated users can access
    pass
```

---

## Features

### Navigation Bar
- Sticky to top (z-50)
- Responsive: Full menu on desktop, hamburger on mobile
- User dropdown with profile/password/admin links
- Logout via POST (CSRF protected)
- Active page highlighting ready

### Login Form
- Professional card design
- Icon indicators for fields
- Real-time validation feedback
- Error message display
- Remember me functionality
- Help section

### Messages System
- Success alerts (green)
- Error alerts (red)
- Warning alerts (yellow)
- Info alerts (blue)
- Auto-dismissible with icons
- ARIA-accessible

### Responsive Design
- Mobile-first approach
- Breakpoints: sm (640px), md (768px), lg (1024px)
- Touch-friendly interactive elements
- Optimized font sizes
- Flexible layouts

---

## Customization

### Changing Colors
Edit CSS variables in `style.css`:
```css
:root {
    --primary-color: #2563eb;
    --secondary-color: #4f46e5;
    /* ... etc */
}
```

### Adding Animations
New animations can be added to the `@keyframes` section in `style.css`.

### Creating New Components
Use the existing patterns:
- Cards: `.card` base class
- Badges: `.badge` with color modifiers
- Stats: `.stat-widget` with `.stat-value`, `.stat-label`

---

## Performance

### Optimization Features
- Tailwind CSS purges unused styles in production
- CSS is minified via CDN
- Static files are cached by browser
- Template inheritance reduces code duplication
- No JavaScript bloat (vanilla HTML/CSS)

### Production Setup
```bash
# Collect static files for deployment
python manage.py collectstatic

# This copies all static files from STATICFILES_DIRS
# and app static directories to STATIC_ROOT
```

---

## Accessibility Features

- Semantic HTML5 structure
- ARIA labels where needed
- Focus indicators on interactive elements
- Color-blind friendly alerts (use icons + color)
- Mobile keyboard navigation support
- Screen reader friendly

---

## Browser Support

- Chrome/Edge: Latest 2 versions
- Firefox: Latest 2 versions
- Safari: Latest 2 versions
- Mobile browsers: iOS Safari 12+, Android Chrome 80+

---

## Testing

### Test Login Flow
1. Navigate to `http://localhost:8000/school/login/`
2. Enter credentials
3. Should redirect to dashboard
4. Verify navigation bar shows username
5. Test logout button

### Test Responsive Design
Use browser DevTools (F12) and toggle device toolbar to test:
- Mobile (375px)
- Tablet (768px)
- Desktop (1024px+)

### Test Messages
Add test view:
```python
from django.contrib import messages

messages.success(request, 'Test success message')
```

---

## URLs Reference

| Path | Name | Template | Requires Auth |
|------|------|----------|---------------|
| `/school/login/` | `login` | `login.html` | No |
| `/school/logout/` | `logout` | N/A | Yes |
| `/school/dashboard/` | `dashboard` | `cbc_school_analytics_dashboard.html` | Yes |
| `/school/` | `cbc_dashboard` | `cbc_school_analytics_dashboard.html` | Yes |
| `/admin/` | N/A | Django admin | Yes (staff) |

---

## Troubleshooting

### Static Files Not Loading
1. Check `STATICFILES_DIRS` in settings.py
2. Verify `STATIC_URL` is correctly set
3. Run `python manage.py collectstatic`
4. Clear browser cache (Ctrl+Shift+Delete)

### CSS Not Applying
1. Verify Tailwind CDN is loading (check Network tab)
2. Check class names match Tailwind documentation
3. Ensure no CSS conflicts from other files
4. Restart development server

### Login Redirects Not Working
1. Verify `LOGIN_URL`, `LOGIN_REDIRECT_URL` in settings.py
2. Check URL patterns in `school/urls.py`
3. Verify `login_required` decorator is on views

### Static Files in Admin
If admin styles look broken:
1. Run `python manage.py collectstatic --noinput`
2. Verify `django.contrib.staticfiles` is in `INSTALLED_APPS`
3. Check `STATIC_ROOT` permissions

---

## Future Enhancements

- [ ] Dark mode toggle
- [ ] Internationalization (i18n)
- [ ] Notification bell with unread count
- [ ] User profile page
- [ ] Password reset via email
- [ ] Two-factor authentication
- [ ] Session timeout warning
- [ ] Loading states and skeletons
- [ ] Breadcrumb navigation
- [ ] Search functionality

---

## References

- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [Django Templates](https://docs.djangoproject.com/en/6.0/topics/templates/)
- [Django Authentication](https://docs.djangoproject.com/en/6.0/topics/auth/)
- [Django Static Files](https://docs.djangoproject.com/en/6.0/howto/static-files/)

---

**Last Updated:** June 9, 2026  
**Version:** 1.0
