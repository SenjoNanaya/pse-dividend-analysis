from django.urls import path
from .views import CompanyListView, CompanyDetailView, CompanyFacetsView

urlpatterns = [
    path('companies/', CompanyListView.as_view(), name='company-list'),
    path('companies/facets/', CompanyFacetsView.as_view(), name='company-facets'),
    path('companies/<int:pk>/', CompanyDetailView.as_view(), name='company-detail'),
]