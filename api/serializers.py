from rest_framework import serializers

from src.report_metrics import incomplete_reasons, no_share_dilution_pass
from src.utils import safe_float

from .models import Company, Financial, Dividend


def _financial_dicts(obj):
    cache = getattr(obj, '_prefetched_objects_cache', {}) or {}
    fins = cache.get('financial_set')
    if fins is None:
        fins = obj.financial_set.all()
    rows = []
    for f in fins:
        rows.append(
            {
                'fiscal_year': f.fiscal_year,
                'revenue': f.revenue,
                'net_income': f.net_income,
                'eps': f.eps,
                'book_value': f.book_value,
                'total_assets': f.total_assets,
                'total_liabilities': f.total_liabilities,
                'stockholders_equity': f.stockholders_equity,
                'outstanding_shares': f.outstanding_shares,
            }
        )
    return rows


class CompanySerializer(serializers.ModelSerializer):
    passes_screen = serializers.SerializerMethodField()
    cap_tier = serializers.SerializerMethodField()
    check_pass_count = serializers.SerializerMethodField()
    check_evaluable_total = serializers.SerializerMethodField()
    dilution_pass = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'symbol', 'name', 'sector', 'subsector', 'ticker',
            'market_cap', 'outstanding_shares', 'last_traded_price',
            'pe_ratio', 'pb_ratio', 'roe', 'div_yield', 'roic', 'debt_to_equity',
            'last_updated',
            'check_pass_count', 'check_evaluable_total', 'info_incomplete',
            'check_struct_pass', 'check_struct_eval',
            'passes_screen', 'cap_tier', 'dilution_pass',
        ]

    def _live_pass(self, obj):
        if hasattr(obj, 'live_check_pass') and obj.live_check_pass is not None:
            return int(obj.live_check_pass)
        return obj.check_pass_count

    def _live_eval(self, obj):
        if hasattr(obj, 'live_check_eval') and obj.live_check_eval is not None:
            return int(obj.live_check_eval)
        return obj.check_evaluable_total

    def get_check_pass_count(self, obj):
        return self._live_pass(obj)

    def get_check_evaluable_total(self, obj):
        return self._live_eval(obj)

    def get_passes_screen(self, obj):
        if obj.info_incomplete:
            return False
        passed = self._live_pass(obj)
        if passed is None:
            return False
        return passed > 5

    def get_cap_tier(self, obj):
        mcap = obj.market_cap
        if mcap is None:
            return None
        if mcap < 3_000_000_000:
            return 'MICRO'
        if mcap < 20_000_000_000:
            return 'SMALL'
        if mcap < 100_000_000_000:
            return 'MID'
        return 'LARGE'

    def get_dilution_pass(self, obj):
        """
        YoY share-count check using prefetched financials when available.
        Null when fewer than two years have outstanding_shares.
        """
        cache = getattr(obj, '_prefetched_objects_cache', {}) or {}
        fins = cache.get('financial_set')
        if fins is None:
            # Avoid N+1 on the full registry list
            if not self.context.get('compute_dilution'):
                return None
            fins = list(
                obj.financial_set.order_by('fiscal_year').only(
                    'fiscal_year', 'outstanding_shares'
                )
            )
        else:
            fins = sorted(fins, key=lambda f: f.fiscal_year or 0)

        with_shares = []
        for f in fins:
            shares = safe_float(f.outstanding_shares)
            if shares is not None and shares > 0:
                with_shares.append(
                    {
                        'fiscal_year': f.fiscal_year,
                        'outstanding_shares': shares,
                    }
                )
        if len(with_shares) < 2:
            return None
        latest = with_shares[-1]
        prev = with_shares[-2]
        return no_share_dilution_pass(latest, prev)


class FinancialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Financial
        fields = [
            'fiscal_year', 'revenue', 'net_income', 'eps',
            'book_value', 'total_assets', 'total_liabilities', 'stockholders_equity',
            'total_current_liabilities',
            'cash_and_equivalents', 'operating_income', 'income_before_tax',
            'income_tax_expense', 'gross_profit', 'ga_expense',
            'cost_of_sales', 'interest_expense', 'other_expenses', 'statement_scope',
            'current_ratio', 'quick_ratio', 'outstanding_shares',
        ]


class DividendSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dividend
        fields = [
            'ex_date', 'record_date', 'payment_date', 'amount',
            'type', 'security', 'is_common',
        ]


class CompanyDetailSerializer(CompanySerializer):
    financials = FinancialSerializer(many=True, source='financial_set')
    dividends = DividendSerializer(many=True, source='dividend_set')
    incomplete_reasons = serializers.SerializerMethodField()

    class Meta(CompanySerializer.Meta):
        fields = CompanySerializer.Meta.fields + [
            'financials',
            'dividends',
            'incomplete_reasons',
        ]

    def get_incomplete_reasons(self, obj):
        return incomplete_reasons(
            {'name': obj.name, 'ticker': obj.ticker},
            _financial_dicts(obj),
        )
