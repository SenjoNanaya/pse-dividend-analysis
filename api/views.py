from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.generics import ListAPIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Company
from .serializers import CompanySerializer, CompanyDetailSerializer
from rest_framework.views import APIView

class CompanyListView(ListAPIView):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['symbol', 'name', 'ticker', 'subsector']
    ordering_fields = [
        'symbol', 'name', 'sector', 'subsector', 'ticker',
        'check_pass_count', 'check_evaluable_total', 'info_incomplete',
        'market_cap', 'last_traded_price', 'div_yield',
    ]
    ordering = ['-check_pass_count', 'symbol']

class CompanyDetailView(APIView):
    def get(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        serializer = CompanyDetailSerializer(company, context={'request': request})
        return Response(serializer.data)
