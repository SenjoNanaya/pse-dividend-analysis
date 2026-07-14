from rest_framework import serializers
from .models import Company, Financial, Dividend

# Change this back from HyperlinkedModelSerializer to ModelSerializer
class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            'id', 'symbol', 'name', 'sector', 'ticker',
            'market_cap', 'outstanding_shares', 'last_traded_price',
            'pe_ratio', 'pb_ratio', 'roe', 'last_updated',
        ]

# ... Keep the rest of your serializers exactly the same ...
class FinancialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Financial
        fields = ['fiscal_year', 'revenue', 'net_income', 'eps', 
                  'book_value', 'total_assets', 'total_liabilities']

class DividendSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dividend
        fields = ['ex_date', 'payment_date', 'amount', 'type']

class CompanyDetailSerializer(CompanySerializer):
    financials = FinancialSerializer(many=True, source='financial_set')
    dividends = DividendSerializer(many=True, source='dividend_set')

    class Meta(CompanySerializer.Meta):
        fields = CompanySerializer.Meta.fields + ['financials', 'dividends']