from rest_framework.filters import SearchFilter
from rest_framework.generics import ListAPIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Company
from .serializers import CompanySerializer, CompanyDetailSerializer
from rest_framework.views import APIView

class CompanyListView(ListAPIView):
    # DRF automatically names this "Company List" based on the class name
    queryset = Company.objects.all().order_by('symbol')
    serializer_class = CompanySerializer
    
    # Enable filtering and searching interfaces
    filter_backends = [DjangoFilterBackend, SearchFilter]
    
    # Define which fields can be searched and filtered
    # filterset_fields = ['sector']
    search_fields = ['symbol', 'name', 'ticker']

# Add a detail view so the links have a destination
class CompanyDetailView(APIView):
    def get(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        # Uses your detailed serializer for the individual company endpoint
        serializer = CompanyDetailSerializer(company, context={'request': request})
        return Response(serializer.data)