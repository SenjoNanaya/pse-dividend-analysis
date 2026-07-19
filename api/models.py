# api/models.py
from django.db import models

class Company(models.Model):
    symbol = models.TextField(unique=True)
    name = models.TextField(blank=True, null=True)
    sector = models.TextField(blank=True, null=True)
    subsector = models.TextField(blank=True, null=True)
    ticker = models.TextField(blank=True, null=True)
    market_cap = models.FloatField(blank=True, null=True)
    outstanding_shares = models.FloatField(blank=True, null=True)
    last_traded_price = models.FloatField(blank=True, null=True)
    pe_ratio = models.FloatField(blank=True, null=True)
    pb_ratio = models.FloatField(blank=True, null=True)
    roe = models.FloatField(blank=True, null=True)
    check_pass_count = models.IntegerField(blank=True, null=True)
    check_evaluable_total = models.IntegerField(blank=True, null=True)
    check_struct_pass = models.IntegerField(blank=True, null=True)
    check_struct_eval = models.IntegerField(blank=True, null=True)
    info_incomplete = models.IntegerField(blank=True, null=True)
    div_yield = models.FloatField(blank=True, null=True)
    roic = models.FloatField(blank=True, null=True)
    debt_to_equity = models.FloatField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.ticker or self.symbol} - {self.name}"

    class Meta:
        managed = False
        db_table = 'companies'


class Dividend(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, blank=True, null=True)
    ex_date = models.DateField(blank=True, null=True)
    record_date = models.DateField(blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)
    amount = models.FloatField(blank=True, null=True)
    type = models.TextField(blank=True, null=True)
    security = models.TextField(blank=True, null=True)
    is_common = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.company.symbol} - {self.ex_date}"

    class Meta:
        managed = False
        db_table = 'dividends'


class Financial(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, blank=True, null=True)
    fiscal_year = models.IntegerField(blank=True, null=True)
    revenue = models.FloatField(blank=True, null=True)
    net_income = models.FloatField(blank=True, null=True)
    eps = models.FloatField(blank=True, null=True)
    book_value = models.FloatField(blank=True, null=True)
    total_assets = models.FloatField(blank=True, null=True)
    total_liabilities = models.FloatField(blank=True, null=True)
    stockholders_equity = models.FloatField(blank=True, null=True)
    total_current_liabilities = models.FloatField(blank=True, null=True)
    cash_and_equivalents = models.FloatField(blank=True, null=True)
    operating_income = models.FloatField(blank=True, null=True)
    income_before_tax = models.FloatField(blank=True, null=True)
    income_tax_expense = models.FloatField(blank=True, null=True)
    gross_profit = models.FloatField(blank=True, null=True)
    ga_expense = models.FloatField(blank=True, null=True)
    cost_of_sales = models.FloatField(blank=True, null=True)
    interest_expense = models.FloatField(blank=True, null=True)
    other_expenses = models.FloatField(blank=True, null=True)
    total_loans = models.FloatField(blank=True, null=True)
    total_deposits = models.FloatField(blank=True, null=True)
    npl = models.FloatField(blank=True, null=True)
    net_interest_income = models.FloatField(blank=True, null=True)
    allowance_for_credit_losses = models.FloatField(blank=True, null=True)
    statement_scope = models.TextField(blank=True, null=True)
    current_ratio = models.FloatField(blank=True, null=True)
    quick_ratio = models.FloatField(blank=True, null=True)
    outstanding_shares = models.FloatField(blank=True, null=True)
    field_sources = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.company.symbol} - {self.fiscal_year}"

    class Meta:
        managed = False
        db_table = 'financials'


class ProcessingLog(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, blank=True, null=True)
    run_timestamp = models.DateTimeField(blank=True, null=True)
    status = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'processing_log'