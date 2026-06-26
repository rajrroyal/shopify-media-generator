from django.contrib import admin

from .models import CreditTransaction, GeneratedImage, GeneratedPrompt, GenerationJob, ProductSnapshot, Shop

admin.site.register([Shop, ProductSnapshot, GenerationJob, GeneratedPrompt, GeneratedImage, CreditTransaction])
