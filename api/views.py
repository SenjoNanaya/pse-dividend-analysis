from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.generics import ListAPIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Company
from .filters import CompanyFilter
from .serializers import CompanySerializer, CompanyDetailSerializer
from rest_framework.views import APIView

class CompanyListView(ListAPIView):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CompanyFilter
    search_fields = ['symbol', 'name', 'ticker', 'subsector', 'sector']
    ordering_fields = [
        'symbol', 'name', 'sector', 'subsector', 'ticker',
        'check_pass_count', 'check_evaluable_total', 'info_incomplete',
        'market_cap', 'last_traded_price', 'div_yield',
    ]
    ordering = ['-check_pass_count', 'symbol']


class CompanyFacetsView(APIView):
    """Distinct sector / subsector values for registry filter dropdowns."""

    def get(self, request):
        sectors = (
            Company.objects.exclude(sector__isnull=True)
            .exclude(sector='')
            .values_list('sector', flat=True)
            .distinct()
            .order_by('sector')
        )
        subsectors = (
            Company.objects.exclude(subsector__isnull=True)
            .exclude(subsector='')
            .values_list('subsector', flat=True)
            .distinct()
            .order_by('subsector')
        )
        return Response({
            'sectors': list(sectors),
            'subsectors': list(subsectors),
            'cap_tiers': ['MICRO', 'SMALL', 'MID', 'LARGE'],
        })


class CompanyDetailView(APIView):
    def get(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        serializer = CompanyDetailSerializer(company, context={'request': request})
        return Response(serializer.data)
