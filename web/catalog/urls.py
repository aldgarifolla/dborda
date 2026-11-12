from django.urls import path
from . import views
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('units/', views.unit_list, name='unit_list'),
    path('units/<str:code>/', views.unit_detail, name='unit_detail'),
    path('items/', views.items, name='items'),
    path('workbook/', views.workbook, name='workbook'),
    path('assistant/', views.assistant, name='assistant'),
    path('grants/', views.manage_grants, name='manage_grants'),
]
