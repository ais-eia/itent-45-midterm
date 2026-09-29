from django.contrib import admin

from .models import CatalogModel


@admin.register(CatalogModel)
class CatalogModelAdmin(admin.ModelAdmin):
    list_display = (
        'display_name',
        'provider',
        'model_id',
        'tier',
        'input_credits_per_1k_tokens',
        'output_credits_per_1k_tokens',
        'is_active',
    )
    list_editable = ('is_active',)
    list_filter = ('provider', 'tier', 'is_active')
    search_fields = ('display_name', 'model_id')
