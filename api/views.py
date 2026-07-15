from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.generics import ListAPIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Company
from .filters import CompanyFilter
from .serializers import CompanySerializer, CompanyDetailSerializer
from .screening import annotate_live_checks, thresholds_from_request
from rest_framework.views import APIView


class CompanyListView(ListAPIView):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CompanyFilter
    search_fields = ['symbol', 'name', 'ticker', 'subsector', 'sector']
    ordering_fields = [
        'symbol', 'name', 'sector', 'subsector', 'ticker',
        'check_pass_count', 'check_evaluable_total', 'live_check_pass', 'live_check_eval',
        'info_incomplete', 'market_cap', 'last_traded_price', 'div_yield',
    ]
    ordering = ['-live_check_pass', 'symbol']

    def get_queryset(self):
        qs = super().get_queryset()
        thresholds = thresholds_from_request(self.request)
        return annotate_live_checks(qs, thresholds)

    def filter_queryset(self, queryset):
        # Map legacy check_pass_count ordering to live annotation
        params = self.request.query_params.copy()
        ordering = params.get('ordering', '')
        remapped = False
        if ordering == 'check_pass_count':
            params['ordering'] = 'live_check_pass'
            remapped = True
        elif ordering == '-check_pass_count':
            params['ordering'] = '-live_check_pass'
            remapped = True
        elif ordering == 'check_evaluable_total':
            params['ordering'] = 'live_check_eval'
            remapped = True
        elif ordering == '-check_evaluable_total':
            params['ordering'] = '-live_check_eval'
            remapped = True
        if remapped:
            self.request._request.GET = params  # noqa: SLF001 — OrderingFilter reads query_params
        return super().filter_queryset(queryset)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['thresholds'] = thresholds_from_request(self.request)
        return ctx


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
            'threshold_defaults': {
                'pe_max': 22,
                'pb_max': 1,
                'roe_min': 0.10,
            },
            'threshold_inputs': {
                'pe_max': 'absolute',
                'pb_max': 'absolute',
                'roe_min': 'fraction (UI enters percent)',
                'yield_min': 'fraction (UI enters percent)',
            },
        })


class CompanyDetailView(APIView):
    def get(self, request, pk):
        thresholds = thresholds_from_request(request)
        queryset = annotate_live_checks(Company.objects.all(), thresholds)
        company = get_object_or_404(queryset, pk=pk)
        serializer = CompanyDetailSerializer(company, context={'request': request, 'thresholds': thresholds})
        return Response(serializer.data)
