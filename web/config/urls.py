from django.contrib.auth import views as auth_views
from django.urls import path, include
from catalog.auth import ThrottledLoginView, StrictPasswordChangeForm
urlpatterns = [
    path('login/', ThrottledLoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('password/', auth_views.PasswordChangeView.as_view(template_name='registration/password_change.html',
                                                             form_class=StrictPasswordChangeForm),
         name='password_change'),
    path('password/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'),
         name='password_change_done'),
    path('', include('catalog.urls')),
]
