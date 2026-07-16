from rest_framework import serializers
from .models import Company, Financial, Dividend


class CompanySerializer(serializers.ModelSerializer):
    passes_screen = serializers.SerializerMethodField()
    cap_tier = serializers.SerializerMethodField()
    check_pass_count = serializers.SerializerMethodField()
    check_evaluable_total = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'symbol', 'name', 'sector', 'subsector', 'ticker',
            'market_cap', 'outstanding_shares', 'last_traded_price',
            'pe_ratio', 'pb_ratio', 'roe', 'div_yield', 'roic', 'debt_to_equity',
            'last_updated',
            'check_pass_count', 'check_evaluable_total', 'info_incomplete',
            'check_struct_pass', 'check_struct_eval',
            'passes_screen', 'cap_tier',
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

    class Meta(CompanySerializer.Meta):
        fields = CompanySerializer.Meta.fields + ['financials', 'dividends']
