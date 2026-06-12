from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views

urlpatterns = [
    # Authentication
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password-change/', views.UserPasswordChangeView.as_view(), name='password_change'),
    path('password-change/done/', views.UserPasswordChangeDoneView.as_view(), name='password_change_done'),
    path('profile/', views.profile, name='profile'),
    
    # Dashboard
    path('dashboard/', views.cbc_school_dashboard, name='dashboard'),
    path('allocations/', views.allocations, name='allocations'),
    path('allocations/<int:allocation_id>/', views.allocation_detail, name='allocation_detail'),
    path('tasks/', views.tasks, name='tasks'),
    path('top-students/', views.top_students, name='top_students'),
    path('streams/<int:stream_id>/results/', views.stream_results, name='stream_results'),
    path('', views.cbc_school_dashboard, name='cbc_dashboard'),
]