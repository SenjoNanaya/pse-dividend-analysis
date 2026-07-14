# api/admin.py
from django.contrib import admin
from .models import Company, Financial, Dividend

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    # This creates the exact literal HTML table layout with columns you want!
    list_display = ('id', 'symbol', 'name', 'sector', 'last_updated')
    
    # Adds a functional search bar to the top of the table
    search_fields = ('symbol', 'name')
    
    # Adds a visual filter sidebar on the right side
    list_filter = ('sector',)

# Optional: Register other models so you can see them too
admin.site.register(Financial)
admin.site.register(Dividend)