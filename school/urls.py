from django.urls import path
from . import views

urlpatterns = [
    path('', views.cbc_school_dashboard, name='cbc_dashboard'),
]