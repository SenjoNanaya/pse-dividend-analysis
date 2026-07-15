import django_filters
from django.db.models import Q

from .models import Company
from .screening import annotate_live_checks, thresholds_from_request

# Matches CompanySerializer.get_cap_tier / frontend marketCapTier
CAP_TIER_RANGES = {
    'MICRO': (None, 3_000_000_000),
    'SMALL': (3_000_000_000, 20_000_000_000),
    'MID': (20_000_000_000, 100_000_000_000),
    'LARGE': (100_000_000_000, None),
}


class CompanyFilter(django_filters.FilterSet):
    sector = django_filters.CharFilter(field_name='sector', lookup_expr='iexact')
    subsector = django_filters.CharFilter(field_name='subsector', lookup_expr='iexact')
    cap_tier = django_filters.CharFilter(method='filter_cap_tier')
    qualified = django_filters.BooleanFilter(method='filter_qualified')
    incomplete = django_filters.BooleanFilter(method='filter_incomplete')
    pe_max = django_filters.NumberFilter(method='filter_pe_max')
    pb_max = django_filters.NumberFilter(method='filter_pb_max')
    roe_min = django_filters.NumberFilter(method='filter_roe_min')
    yield_min = django_filters.NumberFilter(method='filter_yield_min')

    class Meta:
        model = Company
        fields = ['sector', 'subsector']

    def filter_cap_tier(self, queryset, name, value):
        key = str(value or '').strip().upper()
        bounds = CAP_TIER_RANGES.get(key)
        if not bounds:
            return queryset
        low, high = bounds
        qs = queryset.exclude(market_cap__isnull=True)
        if low is not None:
            qs = qs.filter(market_cap__gte=low)
        if high is not None:
            qs = qs.filter(market_cap__lt=high)
        return qs

    def filter_pe_max(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(
            pe_ratio__isnull=False,
            pe_ratio__gte=-1000,
            pe_ratio__lte=1000,
            pe_ratio__lt=value,
        )

    def filter_pb_max(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(
            pb_ratio__isnull=False,
            pb_ratio__gte=-1000,
            pb_ratio__lte=1000,
            pb_ratio__lt=value,
        )

    def filter_roe_min(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(roe__isnull=False, roe__gt=value)

    def filter_yield_min(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(div_yield__isnull=False, div_yield__gte=value)

    def filter_qualified(self, queryset, name, value):
        """Live score > 5 and not incomplete (requires live_check_pass annotation from the view)."""
        request = getattr(self, 'request', None)
        if 'live_check_pass' not in queryset.query.annotations:
            thresholds = thresholds_from_request(request) if request is not None else None
            queryset = annotate_live_checks(queryset, thresholds)

        complete = Q(info_incomplete__isnull=True) | Q(info_incomplete=0)
        if value is True:
            return queryset.filter(complete, live_check_pass__gt=5)
        if value is False:
            return queryset.filter(
                Q(live_check_pass__lte=5)
                | Q(info_incomplete=1)
            )
        return queryset

    def filter_incomplete(self, queryset, name, value):
        if value is True:
            return queryset.filter(info_incomplete=1)
        if value is False:
            return queryset.filter(
                Q(info_incomplete__isnull=True) | Q(info_incomplete=0)
            )
        return queryset
