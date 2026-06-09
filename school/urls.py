from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views

urlpatterns = [
    # Authentication
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    
    # Dashboard
    path('dashboard/', views.cbc_school_dashboard, name='dashboard'),
    path('top-students/', views.top_students, name='top_students'),
    path('', views.cbc_school_dashboard, name='cbc_dashboard'),
]