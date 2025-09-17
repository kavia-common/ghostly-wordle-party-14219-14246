from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions
from rest_framework import serializers

from .models import Game, Guess, UserProfile, Word
from . import RESULT_ABSENT, RESULT_CORRECT, RESULT_PRESENT

User = get_user_model()


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField()


# PUBLIC_INTERFACE
class RegisterSerializer(serializers.ModelSerializer):
    """Create a new user and return basic info."""

    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")

    def validate_password(self, value):
        try:
            validate_password(value)
        except exceptions.ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email"),
            password=validated_data["password"],
        )


# PUBLIC_INTERFACE
class LoginSerializer(serializers.Serializer):
    """Login using username and password."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs.get("username"), password=attrs.get("password"))
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email")


class UserProfileSerializer(serializers.ModelSerializer):
    win_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            "games_played",
            "games_won",
            "current_streak",
            "max_streak",
            "fastest_solve_seconds",
            "best_attempt_count",
            "total_guess_count",
            "win_rate",
        )


class WordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Word
        fields = ("id", "text", "length")


class GuessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guess
        fields = ("id", "text", "result", "created_at")


class GameSerializer(serializers.ModelSerializer):
    target_word_length = serializers.SerializerMethodField()
    guesses = GuessSerializer(many=True, read_only=True)

    class Meta:
        model = Game
        fields = (
            "id",
            "created_at",
            "ended_at",
            "is_won",
            "attempts_used",
            "duration_seconds",
            "max_attempts",
            "target_word_length",
            "guesses",
        )

    def get_target_word_length(self, obj: Game) -> int:
        return obj.target_word.length


# PUBLIC_INTERFACE
class NewGameSerializer(serializers.Serializer):
    """Start a new game; max_attempts optional."""

    max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=10, default=6)


# PUBLIC_INTERFACE
class SubmitGuessSerializer(serializers.Serializer):
    """Submit a guess for a game."""

    guess = serializers.CharField(min_length=1, max_length=12)

    def validate_guess(self, value):
        return value.lower()


# PUBLIC_INTERFACE
class EffectTriggerSerializer(serializers.Serializer):
    """Trigger celebratory or failure effects on frontend."""

    effect = serializers.ChoiceField(choices=["party_popper", "disco", "ghost", "shake", "confetti"])
    context = serializers.DictField(child=serializers.CharField(), required=False)


# Helpers exposed for gameplay business logic reuse

# PUBLIC_INTERFACE
def score_guess(guess: str, target: str) -> list[str]:
    """
    Score a guess against the target word using Wordle rules.

    Returns a list of slot results where each item is
    - 'correct' if letter and position match,
    - 'present' if letter exists elsewhere in target,
    - 'absent' if letter not in target or already consumed.
    """
    guess = guess.lower()
    target = target.lower()
    n = len(target)
    result = [RESULT_ABSENT] * n
    target_counts = {}

    for i, ch in enumerate(target):
        target_counts[ch] = target_counts.get(ch, 0) + 1

    # First pass: mark exact matches
    for i, ch in enumerate(guess[:n]):
        if ch == target[i]:
            result[i] = RESULT_CORRECT
            target_counts[ch] -= 1

    # Second pass: mark present where counts remain
    for i, ch in enumerate(guess[:n]):
        if result[i] == RESULT_CORRECT:
            continue
        if target_counts.get(ch, 0) > 0:
            result[i] = RESULT_PRESENT
            target_counts[ch] -= 1
        else:
            result[i] = RESULT_ABSENT

    return result
