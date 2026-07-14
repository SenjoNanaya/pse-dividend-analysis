from rest_framework import serializers
from .models import Company, Financial, Dividend

# Change this back from HyperlinkedModelSerializer to ModelSerializer
class CompanySerializer(serializers.ModelSerializer):
    passes_screen = serializers.SerializerMethodField()
    cap_tier = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'symbol', 'name', 'sector', 'subsector', 'ticker',
            'market_cap', 'outstanding_shares', 'last_traded_price',
            'pe_ratio', 'pb_ratio', 'roe', 'div_yield', 'last_updated',
            'check_pass_count', 'check_evaluable_total', 'info_incomplete',
            'passes_screen', 'cap_tier',
        ]

    def get_passes_screen(self, obj):
        if obj.info_incomplete:
            return False
        if obj.check_pass_count is None:
            return False
        return obj.check_pass_count > 5

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
# ... Keep the rest of your serializers exactly the same ...
class FinancialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Financial
        fields = ['fiscal_year', 'revenue', 'net_income', 'eps', 
                  'book_value', 'total_assets', 'total_liabilities',
                  'current_ratio', 'quick_ratio', 'outstanding_shares']

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