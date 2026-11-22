from django.urls import path
from . import views
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('districts/', views.district_list, name='district_list'),
    path('districts/<str:code>/', views.district_detail, name='district_detail'),
    path('districts/<str:code>/formations/<str:fcode>/', views.formation_detail, name='formation_detail'),
    path('districts/<str:code>/formations/<str:fcode>/units/<str:scode>/', views.subunit_detail, name='subunit_detail'),
    path('items/', views.items, name='items'),
    path('items/<path:sname>/', views.item_detail, name='item_detail'),
    path('assistant/', views.assistant, name='assistant'),
    path('assistant/c/<int:chat_id>/', views.assistant, name='assistant_chat'),
    path('assistant/c/<int:chat_id>/title/', views.assistant_title, name='assistant_title'),
    path('assistant/c/<int:chat_id>/rename/', views.assistant_rename, name='assistant_rename'),
    path('assistant/c/<int:chat_id>/delete/', views.assistant_delete, name='assistant_delete'),
    path('grants/', views.manage_grants, name='manage_grants'),
]
