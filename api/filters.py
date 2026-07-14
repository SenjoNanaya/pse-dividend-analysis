import django_filters
from django.db.models import Q

from .models import Company

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

    def filter_qualified(self, queryset, name, value):
        """Same rule as passes_screen: check_pass_count > 5 and not incomplete."""
        if value is True:
            return queryset.filter(
                check_pass_count__gt=5,
            ).filter(
                Q(info_incomplete__isnull=True) | Q(info_incomplete=0)
            )
        if value is False:
            return queryset.filter(
                Q(check_pass_count__lte=5)
                | Q(check_pass_count__isnull=True)
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
