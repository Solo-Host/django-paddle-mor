from django.urls import include, path

urlpatterns = [
    path("", include("django_paddle_mor.urls")),
]
