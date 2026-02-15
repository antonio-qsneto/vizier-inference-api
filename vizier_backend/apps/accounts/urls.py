"""
URLs for accounts app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'categories', views.CategoriesViewSet, basename='category')

urlpatterns = [
    path('me/', views.UserViewSet.as_view({'get': 'me'}), name='user-me'),
    path('', include(router.urls)),
]
