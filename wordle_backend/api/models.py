from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class TimeStampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Word(TimeStampedModel):
    """
    Stores eligible words for the game.

    Fields:
    - text: the target or allowable guess word (lowercase)
    - is_active: if True, can be selected for a game
    - length: denormalized length for faster queries
    """

    text = models.CharField(max_length=12, unique=True)
    is_active = models.BooleanField(default=True)
    length = models.PositiveSmallIntegerField(default=5)

    def save(self, *args, **kwargs):
        self.text = self.text.lower()
        self.length = len(self.text)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.text


RESULT_EXACT = "correct"        # green
RESULT_PRESENT = "present"      # yellow
RESULT_ABSENT = "absent"        # gray


class Game(TimeStampedModel):
    """
    Represents a single Wordle game instance for a user.

    Fields:
    - user: owner (nullable for anonymous future usage, but generally authenticated)
    - target_word: FK to Word
    - max_attempts: defaults to 6
    - ended_at: timestamp when game ended
    - is_won: True if user guessed correctly
    - attempts_used: denormalized to speed leaderboard queries
    - duration_seconds: seconds from creation to end
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="games")
    target_word = models.ForeignKey(Word, on_delete=models.PROTECT, related_name="games")
    max_attempts = models.PositiveSmallIntegerField(default=6)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_won = models.BooleanField(default=False)
    attempts_used = models.PositiveSmallIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def end_game(self, won: bool, attempts_used: int) -> None:
        now = timezone.now()
        self.ended_at = now
        self.is_won = won
        self.attempts_used = attempts_used
        total = int((now - self.created_at).total_seconds())
        self.duration_seconds = max(total, 0)
        self.save(update_fields=["ended_at", "is_won", "attempts_used", "duration_seconds", "updated_at"])

    def __str__(self) -> str:
        return f"Game({self.id}) user={self.user_id} won={self.is_won}"


class Guess(TimeStampedModel):
    """
    Stores a single guess in a game.

    Fields:
    - game: FK to Game
    - text: the guessed word (lowercase)
    - result: JSON array of slot results (correct/present/absent)
    """

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="guesses")
    text = models.CharField(max_length=12)
    result = models.JSONField(default=list)

    def save(self, *args, **kwargs):
        self.text = self.text.lower()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Guess({self.id}) {self.text} -> {self.result}"


class UserProfile(TimeStampedModel):
    """
    Denormalized user stats for leaderboards and profile display.

    Fields:
    - user: OneToOne to auth user
    - games_played
    - games_won
    - current_streak
    - max_streak
    - fastest_solve_seconds: minimal duration for wins
    - best_attempt_count: minimal attempts for a win
    - total_guess_count: total number of guesses across games
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    games_played = models.PositiveIntegerField(default=0)
    games_won = models.PositiveIntegerField(default=0)
    current_streak = models.PositiveIntegerField(default=0)
    max_streak = models.PositiveIntegerField(default=0)
    fastest_solve_seconds = models.PositiveIntegerField(null=True, blank=True)
    best_attempt_count = models.PositiveIntegerField(null=True, blank=True)
    total_guess_count = models.PositiveIntegerField(default=0)

    # Derived fields (not stored) can be exposed in serializers
    @property
    def win_rate(self) -> float:
        if self.games_played == 0:
            return 0.0
        return round((self.games_won / self.games_played) * 100.0, 2)

    def record_game(self, won: bool, attempts_used: int, duration_seconds: int) -> None:
        self.games_played += 1
        self.total_guess_count += attempts_used
        if won:
            self.games_won += 1
            self.current_streak += 1
            if self.fastest_solve_seconds is None or duration_seconds < self.fastest_solve_seconds:
                self.fastest_solve_seconds = duration_seconds
            if self.best_attempt_count is None or attempts_used < self.best_attempt_count:
                self.best_attempt_count = attempts_used
        else:
            self.current_streak = 0
        if self.current_streak > self.max_streak:
            self.max_streak = self.current_streak
        self.save()

    def __str__(self) -> str:
        return f"Profile({self.user_id})"


def ensure_user_profile(user: User) -> UserProfile:
    """Get or create a user profile for the given user."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile
