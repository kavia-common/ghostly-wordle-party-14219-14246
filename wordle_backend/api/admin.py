from django.contrib import admin
from .models import Word, Game, Guess, UserProfile


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("text", "is_active", "length", "created_at")
    search_fields = ("text",)
    list_filter = ("is_active", "length")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "target_word", "is_won", "attempts_used", "duration_seconds", "created_at", "ended_at")
    list_filter = ("is_won",)
    search_fields = ("user__username", "target_word__text")


@admin.register(Guess)
class GuessAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "text", "created_at")
    search_fields = ("text", "game__user__username")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "games_played", "games_won", "current_streak", "max_streak", "fastest_solve_seconds", "best_attempt_count")
    search_fields = ("user__username",)
