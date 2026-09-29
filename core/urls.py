from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .views import SignUpView

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='account_signup'),
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='core/login.html'),
        name='account_login',
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(next_page=reverse_lazy('account_login')),
        name='account_logout',
    ),
]
